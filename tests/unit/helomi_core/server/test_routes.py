from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from helomi_core import Runtime
from helomi_core.server.app import ServerContext, create_app
from helomi_core.server.config import ServerSettings
from helomi_core.server.server import UvicornServerThread
from helomi_core.server.session import SessionManager
from helomi_core.speech import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    SayText,
    TranscriptionReady,
)


@pytest.fixture
def mock_runtime() -> MagicMock:
    runtime = MagicMock(spec=Runtime)
    runtime.profiles = {
        "prof_test": MagicMock(),
        "prof_other": MagicMock(),
    }
    return runtime


@pytest.fixture
def server_setup(mock_runtime: MagicMock):
    session_manager = SessionManager()
    publish_mock = AsyncMock(return_value=True)
    context = ServerContext(
        runtime=mock_runtime,
        session_manager=session_manager,
        publish_command=publish_mock,
    )
    app = create_app(context)
    return app, session_manager, publish_mock


@pytest.mark.asyncio
async def test_health_check(server_setup) -> None:
    app, _, _ = server_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["active_sessions"] == 0


@pytest.mark.asyncio
async def test_get_speech_profile_not_found(server_setup) -> None:
    app, _, _ = server_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/speech", params={"profile_id": "nonexistent"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_speech_stream_and_profile_lock(server_setup) -> None:
    app, session_manager, _ = server_setup
    config = ServerSettings(host="127.0.0.1", port=8987)
    server_thread = UvicornServerThread(app=app, config=config)
    server_thread.start()

    try:
        async with (
            httpx.AsyncClient(base_url="http://127.0.0.1:8987") as client1,
            httpx.AsyncClient(base_url="http://127.0.0.1:8987") as client2,
        ):
            # 1. Connect first client to prof_test
            async with client1.stream(
                "GET", "/api/v1/speech", params={"profile_id": "prof_test"}
            ) as response:
                assert response.status_code == 200
                session_id_header = response.headers.get("X-Session-ID")
                assert session_id_header is not None

                chunks = response.aiter_bytes()
                chunk1 = await anext(chunks)
                assert b"event: session" in chunk1
                assert b"session_id" in chunk1

                # 2. Try to connect second client to the same profile
                # (should fail with 409 Conflict)
                resp_conflict = await client2.get(
                    "/api/v1/speech", params={"profile_id": "prof_test"}
                )
                assert resp_conflict.status_code == 409
                assert "already locked" in resp_conflict.json()["detail"]

                # 3. Dispatch an event to the session
                session = session_manager.get(session_id_header)
                assert session is not None
                session_manager.dispatch_event(
                    TranscriptionReady(profile_id="prof_test", text="Testing STT")
                )

                chunk2 = await anext(chunks)
                assert b"event: transcription_ready" in chunk2
                assert b"Testing STT" in chunk2

                # Dispatch ProfileActivated
                session_manager.dispatch_event(ProfileActivated(profile_id="prof_test"))
                chunk3 = await anext(chunks)
                assert b"event: profile_activated" in chunk3

                # 4. Close the session to end stream
                await session_manager.release(session_id_header)
                await response.aclose()

        # After disconnecting, profile should be unlocked
        assert session_manager.active_sessions_count == 0
    finally:
        server_thread.stop()


@pytest.mark.asyncio
async def test_post_speech_cmd_validation_and_execution(server_setup) -> None:
    app, session_manager, publish_mock = server_setup
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing header
        resp = await client.post(
            "/api/v1/speech",
            json={"type": "say_text", "text": "Hi"},
        )
        assert resp.status_code == 422

        # 2. Invalid session ID
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": "invalid-session-uuid"},
            json={"type": "say_text", "text": "Hi"},
        )
        assert resp.status_code == 401

        # Create active session
        session = await session_manager.acquire("prof_test")
        session_id = session.id

        # 3. Post say_text without profile_id (defaults to session profile)
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": session_id},
            json={"type": "say_text", "text": "Hello world"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "success": True}
        publish_mock.assert_called_with(
            SayText(text="Hello world", profile_id="prof_test")
        )

        # 4. Post say_text with mismatched profile_id (should fail with 403)
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": session_id},
            json={"type": "say_text", "text": "Hello", "profile_id": "other_profile"},
        )
        assert resp.status_code == 403

        # 5. Post activate_profile matching session profile
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": session_id},
            json={"type": "activate_profile", "profile_id": "prof_test"},
        )
        assert resp.status_code == 200
        publish_mock.assert_called_with(ActivateProfile(profile_id="prof_test"))

        # 6. Post activate_profile with mismatched profile
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": session_id},
            json={"type": "activate_profile", "profile_id": "mismatched"},
        )
        assert resp.status_code == 403

        # 7. Post deactivate_profile
        resp = await client.post(
            "/api/v1/speech",
            headers={"X-Session-ID": session_id},
            json={"type": "deactivate_profile"},
        )
        assert resp.status_code == 200
        publish_mock.assert_called_with(DeactivateProfile())

        await session_manager.release(session_id)
