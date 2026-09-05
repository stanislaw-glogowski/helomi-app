from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from helomi_core.config.profile import Profile
from helomi_core.pipeline.extension import PipelineExtension
from helomi_core.server.api.app import create_api
from helomi_core.server.session import SessionManager


@pytest.fixture
def mock_api_setup():
    mock_pipeline = MagicMock(spec=PipelineExtension)
    mock_pipeline.execute_command = AsyncMock(return_value=True)

    prof1 = MagicMock(spec=Profile)
    prof1.id = "p1"
    prof1.name = "Profile 1"

    mock_pipeline.profiles = MagicMock()
    mock_pipeline.profiles.__iter__ = MagicMock(return_value=iter([prof1]))
    mock_pipeline.profiles.get = MagicMock(
        side_effect=lambda k, throw_on_not_found=True: prof1 if k == "p1" else None
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
        assert resp.json() == [{"id": "p1", "name": "Profile 1", "is_active": True}]

        resp_single = await client.get("/api/v1/profile/p1")
        assert resp_single.status_code == 200
        assert resp_single.json() == {
            "id": "p1",
            "name": "Profile 1",
            "is_active": True,
        }

        resp_404 = await client.get("/api/v1/profile/unknown")
        assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_speech_sse_and_post_cmd(mock_api_setup) -> None:
    app, mock_pipeline, sessions = mock_api_setup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 404 for unknown profile
        resp_404 = await client.get("/api/v1/speech", params={"profile_id": "unknown"})
        assert resp_404.status_code == 404

        # Acquire session directly to test POST
        session = await sessions.acquire("p1")
        assert session is not None

        # POST with unknown session
        resp_unauth = await client.post(
            "/api/v1/speech",
            json={"type": "say_text", "text": "hello"},
            headers={"x-session-id": "bad_id"},
        )
        assert resp_unauth.status_code == 401

        # POST with valid session
        resp_ok = await client.post(
            "/api/v1/speech",
            json={"type": "say_text", "text": "hello", "profile_id": "p1"},
            headers={"x-session-id": session.id},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"success": True}
        mock_pipeline.execute_command.assert_called_once()

        # POST with mismatching profile_id
        resp_forbidden = await client.post(
            "/api/v1/speech",
            json={"type": "say_text", "text": "hello", "profile_id": "other"},
            headers={"x-session-id": session.id},
        )
        assert resp_forbidden.status_code == 403

        # 409 if profile already in use for SSE
        resp_conflict = await client.get("/api/v1/speech", params={"profile_id": "p1"})
        assert resp_conflict.status_code == 409
