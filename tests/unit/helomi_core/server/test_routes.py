from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from helomi_core.pipeline.extension import PipelineExtension
from helomi_core.profile import Profile
from helomi_core.server.api.app import create_api
from helomi_core.server.session import SessionManager


@pytest.fixture
def mock_api_setup():
    mock_pipeline = MagicMock(spec=PipelineExtension)
    mock_pipeline.execute_command = AsyncMock(return_value=True)

    prof1 = MagicMock(spec=Profile)
    prof1.id = "p1"
    prof1.name = "Profile 1"

    def mock_dump(require_prompt=None, active_id=None, default_id=None):
        if require_prompt == "not_found":
            return {}
        return {
            "id": "p1",
            "name": "Profile 1",
            "is_active": active_id == "p1",
            "prompt": "Hello" if require_prompt else None,
        }

    prof1.dump = MagicMock(side_effect=mock_dump)

    mock_pipeline.profiles = MagicMock()
    mock_pipeline.profiles.__iter__ = MagicMock(side_effect=lambda: iter([prof1]))
    mock_pipeline.profiles.get = MagicMock(
        side_effect=lambda k, throw_on_not_found=True: (
            prof1 if k == "p1" or k is None else None
        )
    )
    mock_pipeline.active_profile = prof1

    sessions = SessionManager()
    app = create_api(pipeline=mock_pipeline, sessions=sessions)
    return app, mock_pipeline, sessions


@pytest.mark.asyncio
async def test_health_endpoint(mock_api_setup) -> None:
    app, _, _ = mock_api_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "OK"}


@pytest.mark.asyncio
async def test_profiles_endpoints(mock_api_setup) -> None:
    app, _, _ = mock_api_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 200
        assert resp.json() == [
            {"id": "p1", "name": "Profile 1", "is_active": True, "prompt": None}
        ]

        resp_prompt = await client.get("/api/v1/profile?require_prompt=demo")
        assert resp_prompt.status_code == 200
        assert resp_prompt.json() == [
            {"id": "p1", "name": "Profile 1", "is_active": True, "prompt": "Hello"}
        ]

        resp_single = await client.get("/api/v1/profile/p1")
        assert resp_single.status_code == 200
        assert resp_single.json() == {
            "id": "p1",
            "name": "Profile 1",
            "is_active": True,
            "prompt": None,
        }

        resp_single_prompt = await client.get("/api/v1/profile/p1?require_prompt=demo")
        assert resp_single_prompt.status_code == 200
        assert resp_single_prompt.json() == {
            "id": "p1",
            "name": "Profile 1",
            "is_active": True,
            "prompt": "Hello",
        }

        resp_single_not_found = await client.get(
            "/api/v1/profile/p1?require_prompt=not_found"
        )
        assert resp_single_not_found.status_code == 404

        resp_404 = await client.get("/api/v1/profile/unknown")
        assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_root_index_endpoint(mock_api_setup) -> None:
    app, _, _ = mock_api_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Helomi API"


@pytest.mark.asyncio
async def test_speech_sse_and_post_cmd(mock_api_setup) -> None:
    app, mock_pipeline, sessions = mock_api_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 404 for unknown profile stream
        resp_404 = await client.get("/api/v1/profile/unknown/stream")
        assert resp_404.status_code == 404

        # Acquire session directly to test POST
        session = await sessions.acquire("p1")
        assert session is not None

        # POST with unknown session
        resp_unauth = await client.post(
            "/api/v1/command",
            json={"type": "say_text", "text": "hello"},
            headers={"x-session-id": "bad_id"},
        )
        assert resp_unauth.status_code == 401

        # POST with valid session (say_text)
        resp_ok = await client.post(
            "/api/v1/command",
            json={"type": "say_text", "text": "hello", "profile_id": "p1"},
            headers={"x-session-id": session.id},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"success": True}
        assert mock_pipeline.execute_command.call_count == 1

        # POST activate_profile
        resp_act = await client.post(
            "/api/v1/command",
            json={"type": "activate_profile", "profile_id": "p1"},
            headers={"x-session-id": session.id},
        )
        assert resp_act.status_code == 200
        assert resp_act.json() == {"success": True}

        # POST deactivate_profile (no profile_id)
        resp_deact = await client.post(
            "/api/v1/command",
            json={"type": "deactivate_profile"},
            headers={"x-session-id": session.id},
        )
        assert resp_deact.status_code == 200
        assert resp_deact.json() == {"success": True}

        # POST with mismatching profile_id
        resp_forbidden = await client.post(
            "/api/v1/command",
            json={"type": "say_text", "text": "hello", "profile_id": "other"},
            headers={"x-session-id": session.id},
        )
        assert resp_forbidden.status_code == 403

        # 409 if profile already in use for SSE
        resp_conflict = await client.get("/api/v1/profile/p1/stream")
        assert resp_conflict.status_code == 409


@pytest.mark.asyncio
async def test_profile_sse_stream_events(mock_api_setup) -> None:
    from helomi_core.pipeline.domain import ProfileActivatedEvent
    from helomi_core.server.api.routes import create_router

    _, mock_pipeline, sessions = mock_api_setup
    router = create_router()
    route = next(
        r
        for r in router.routes
        if getattr(r, "path", "") == "/profile/{profile_id}/stream"
    )

    streaming_resp = await route.endpoint(
        profile_id="p1",
        pipeline=mock_pipeline,
        sessions=sessions,
    )
    assert streaming_resp.status_code == 200
    session_id = streaming_resp.headers["X-Session-ID"]
    session = sessions.get(session_id)
    assert session is not None

    gen = streaming_resp.body_iterator
    first = await anext(gen)
    assert "event: session" in first

    session.dispatch_event(ProfileActivatedEvent(profile_id="p1"))
    second = await anext(gen)
    assert "event: profile_activated" in second

    session.close()
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    assert sessions.get(session_id) is None
