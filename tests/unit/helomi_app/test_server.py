import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from helomi_app import (
    ActivationSource,
    CommandResult,
    ProfileActivatedEvent,
    ResponseMode,
)
from helomi_app.config import ServerSettings
from helomi_app.server.api import (
    create_api,
    get_profile,
    get_profile_stream,
    get_profiles,
)
from helomi_app.server.component import ServerModule
from helomi_app.server.session import Session, SessionManager


def _application(*, mode: ResponseMode = ResponseMode.API):
    profile = MagicMock()
    profile.id = "alexa"
    profile.to_public_dict.side_effect = lambda require_prompt=None, active_id=None: (
        {}
        if require_prompt == "missing"
        else {
            "id": "alexa",
            "name": "Alexa",
            "is_active": active_id == "alexa",
        }
    )
    profiles = MagicMock()
    profiles.__iter__.return_value = iter([profile])
    profiles.get.side_effect = lambda value: profile if value == "alexa" else None
    application = MagicMock()
    application.profiles = profiles
    application.active_profile = profile
    application.response_mode = mode
    application.execute_command = AsyncMock(return_value=CommandResult.ok())
    return application, profile


@pytest.mark.asyncio
async def test_api_metadata_profiles_and_errors():
    application, profile = _application()
    sessions = SessionManager()
    api = create_api(application, sessions)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://test",
    ) as client:
        assert (await client.get("/")).json()["version"] == "0.8.0"
        assert (await client.get("/health")).json() == {"status": "OK"}
        profiles = (await client.get("/api/v1/profile")).json()
        assert profiles == [{"id": "alexa", "name": "Alexa", "is_active": True}]
        assert "is_default" not in profiles[0]
        assert (await client.get("/api/v1/profile/alexa")).status_code == 200
        assert (await client.get("/api/v1/profile/missing")).status_code == 404
        assert (
            await client.get(
                "/api/v1/profile/alexa", params={"require_prompt": "missing"}
            )
        ).status_code == 404
    assert profile.to_public_dict.called


@pytest.mark.asyncio
async def test_command_endpoint_session_and_mode_guards():
    application, _ = _application(mode=ResponseMode.PARROT)
    sessions = SessionManager()
    api = create_api(application, sessions)
    session = await sessions.acquire("alexa")
    assert session is not None
    headers = {"x-session-id": session.id}
    say = {"type": "say_text", "text": "Hello", "mode": "api"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        assert (
            await client.post("/api/v1/command", json=say, headers={})
        ).status_code == 422
        assert (
            await client.post(
                "/api/v1/command",
                json=say,
                headers={"x-session-id": "invalid"},
            )
        ).status_code == 401
        assert (
            await client.post("/api/v1/command", json=say, headers=headers)
        ).status_code == 409

        application.response_mode = ResponseMode.API
        for payload in (
            say,
            {"type": "say_reaction", "reaction": "greeting", "mode": "api"},
            {"type": "end_conversation", "play_farewell": False},
        ):
            response = await client.post(
                "/api/v1/command", json=payload, headers=headers
            )
            assert response.status_code == 200
            assert response.json()["accepted"] is True
    assert application.execute_command.await_count == 3
    assert application.execute_command.await_args_list[0].args[0].profile_id == "alexa"


@pytest.mark.asyncio
async def test_profile_functions_and_sse_lifecycle():
    application, _ = _application()
    sessions = SessionManager()
    assert await get_profiles(application) == [
        {"id": "alexa", "name": "Alexa", "is_active": True}
    ]
    assert (await get_profile("alexa", application))["id"] == "alexa"
    with pytest.raises(HTTPException) as missing:
        await get_profile("missing", application)
    assert missing.value.status_code == 404

    response = await get_profile_stream("alexa", application, sessions)
    assert response.headers["x-session-id"]
    with pytest.raises(HTTPException) as busy:
        await get_profile_stream("alexa", application, sessions)
    assert busy.value.status_code == 409

    iterator = response.body_iterator
    started = await anext(iterator)
    assert "session_started" in started
    await iterator.aclose()
    assert sessions.get(response.headers["x-session-id"]) is None

    with pytest.raises(HTTPException) as unknown:
        await get_profile_stream("missing", application, sessions)
    assert unknown.value.status_code == 404


@pytest.mark.asyncio
async def test_sessions_dispatch_release_and_cleanup():
    manager = SessionManager()
    async with manager:
        session = await manager.acquire("alexa")
        assert session is not None
        assert await manager.acquire("alexa") is None
        event = ProfileActivatedEvent(profile_id="alexa", source=ActivationSource.CLI)
        manager.dispatch(event)
        assert await anext(session.subscribe()) == event
        manager.dispatch(MagicMock(profile_id=None))
        await manager.release(session)
        await manager.release(session)
        assert manager.get(session.id) is None

        second = await manager.acquire("alexa")
        assert second is not None
    assert manager.get(second.id) is None

    standalone = Session("alexa")
    standalone.close()
    assert [event async for event in standalone.subscribe()] == []


@pytest.mark.asyncio
async def test_server_component_lifecycle():
    application, _ = _application()
    fake_server = MagicMock()
    fake_server.should_exit = False
    fake_server.serve = AsyncMock()
    with patch("helomi_app.server.component.uvicorn.Server", return_value=fake_server):
        server = ServerModule(ServerSettings(host="127.0.0.1", port=4567), application)
        assert server.url == "http://127.0.0.1:4567"
        assert server.docs_url.endswith("/docs")
        await server.__aenter__()
        await asyncio.sleep(0)
        await server.__aexit__(None, None, None)
    fake_server.serve.assert_awaited_once()
    assert fake_server.should_exit is True
