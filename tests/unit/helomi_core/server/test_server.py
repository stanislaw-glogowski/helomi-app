import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_core import Runtime
from helomi_core.server import Server, ServerSettings
from helomi_core.speech import (
    ProfileActivated,
    SayText,
    TranscriptionReady,
)


@pytest.fixture
def mock_runtime() -> MagicMock:
    runtime = MagicMock(spec=Runtime)
    runtime.profiles = {
        "prof1": MagicMock(id="prof1", name="Profile 1"),
        "prof2": MagicMock(id="prof2", name="Profile 2"),
    }
    runtime.settings = MagicMock()
    runtime.settings.server = ServerSettings(host="127.0.0.1", port=4356)
    return runtime


@pytest.mark.asyncio
async def test_server_lifecycle_and_methods(mock_runtime) -> None:
    with patch("helomi_core.speech.SpeechPipeline") as mock_pipeline_cls:
        mock_pipe = mock_pipeline_cls.return_value
        mock_pipe.__aenter__.return_value = mock_pipe
        mock_pipe.__aexit__.return_value = None
        mock_pipe.activate_profile = AsyncMock(return_value=True)
        mock_pipe.deactivate_profile = AsyncMock(return_value=True)
        mock_pipe.say_text = AsyncMock(return_value=True)
        mock_pipe.publish = AsyncMock(return_value=True)
        mock_pipe.active_profile = None

        mock_runtime.get_speech_pipeline.return_value = mock_pipe

        config = ServerSettings(host="127.0.0.1", port=8991)
        server = Server(
            runtime=mock_runtime,
            config=config,
            auto_server=False,
        )

        assert server.runtime is mock_runtime
        assert server.config is config
        assert server.host == "127.0.0.1"
        assert server.port == 8991
        assert server.session_manager is not None
        assert server.active_profile is None

        received_events = []

        def sync_listener(evt):
            received_events.append(evt)

        async def async_listener(evt):
            received_events.append(evt)

        server.add_listener(sync_listener)
        server.add_listener(async_listener)

        async def fake_subscribe():
            yield ProfileActivated(profile_id="prof1")
            yield TranscriptionReady(profile_id="prof1", text="Hello service")

        mock_pipe.subscribe = fake_subscribe

        async with server:
            assert await server.activate_profile("prof1")
            mock_pipe.activate_profile.assert_called_with("prof1", None)

            assert await server.deactivate_profile()
            mock_pipe.deactivate_profile.assert_called_with(None)

            assert await server.say_text("test say", "prof1")
            mock_pipe.say_text.assert_called_with("test say", "prof1", None)

            assert await server.publish(SayText(text="cmd say", profile_id="prof1"))
            mock_pipe.publish.assert_called()

            # Allow event loop to process dispatched events
            await asyncio.sleep(0.05)

    assert len(received_events) >= 2
    server.remove_listener(sync_listener)
    server.remove_listener(async_listener)
    # Removing not present listener should be safe
    server.remove_listener(sync_listener)
