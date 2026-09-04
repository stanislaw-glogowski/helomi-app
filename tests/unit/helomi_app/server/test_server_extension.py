import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_app.pipeline.domain import TranscriptionReady
from helomi_app.pipeline.service import PipelineService
from helomi_app.server.config import ServerSettings
from helomi_app.server.extension import ServerExtension
from helomi_app.server.session import SessionManager


@pytest.mark.asyncio
async def test_server_extension_properties_and_events() -> None:
    config = ServerSettings(host="127.0.0.1", port=9999)
    mock_pipeline = MagicMock(spec=PipelineService)

    async def fake_subscribe(_=None):
        yield TranscriptionReady(profile_id="p1", text="text")

    mock_pipeline.subscribe = fake_subscribe

    sessions = MagicMock(spec=SessionManager)
    sessions.dispatch = MagicMock()

    server = ServerExtension(
        config=config,
        pipeline=mock_pipeline,
        is_enabled=True,
        sessions=sessions,
    )

    assert server.url == "http://127.0.0.1:9999"
    assert "url=http://127.0.0.1:9999" in str(server)

    with patch.object(server._server, "startup", new=AsyncMock()):
        with patch.object(server._server, "shutdown", new=AsyncMock()):
            with patch.object(server._server, "main_loop", new=AsyncMock()):
                async with server:
                    await asyncio.sleep(0.05)

    sessions.dispatch.assert_called_once()
