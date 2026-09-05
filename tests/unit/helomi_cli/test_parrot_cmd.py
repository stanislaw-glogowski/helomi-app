import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_cli.commands.parrot import run_parrot_cmd
from helomi_cli.widgets import Spinner
from helomi_core.pipeline import (
    ProfileActivated,
    ProfileDeactivated,
    TranscriptionReady,
)


@pytest.fixture
def mock_runtime():
    mock_profile = MagicMock()
    mock_profile.id = "test_profile"
    mock_profile.name = "Test Profile"

    mock_profiles = MagicMock()
    mock_profiles.get.return_value = mock_profile
    mock_profiles.__iter__.return_value = iter([mock_profile])

    settings = MagicMock()
    settings.audio.adapter = "avfaudio"
    settings.wakeword.adapter = "openwakeword"
    settings.vad.adapter = "silero_vad"
    settings.turn.adapter = "smart_turn"
    settings.stt.adapter = "parakeet"
    settings.tts.adapter = "voxcpm2"

    mock_pipeline = MagicMock()
    mock_pipeline.set_active_profile = AsyncMock(return_value=True)

    runtime = MagicMock()
    runtime.profiles = mock_profiles
    runtime.settings = settings
    runtime.get_parrot_extension = AsyncMock()
    runtime.get_pipeline_service = AsyncMock(return_value=mock_pipeline)
    return runtime, mock_pipeline


@pytest.mark.asyncio
async def test_run_parrot_cmd_lifecycle(mock_runtime):
    """Verify run_parrot_cmd starts extension, activates profile, monitors events."""
    runtime, mock_pipeline = mock_runtime

    async def mock_events():
        yield ProfileActivated(profile_id="test_profile")
        yield TranscriptionReady(profile_id="test_profile", text="Hello world")
        yield ProfileDeactivated(profile_id="test_profile")

    mock_pipeline.subscribe_event = mock_events

    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.05)
        shutdown.set()

    task = asyncio.create_task(trigger_shutdown())
    await run_parrot_cmd(runtime, shutdown, "test_profile", spinner)
    await task

    runtime.get_parrot_extension.assert_called_once()
    runtime.get_pipeline_service.assert_called_once()
    mock_pipeline.set_active_profile.assert_called_once_with("test_profile")


@pytest.mark.asyncio
async def test_run_parrot_cmd_no_profile(mock_runtime):
    """Verify run_parrot_cmd without profile_id does not call set_active_profile."""
    runtime, mock_pipeline = mock_runtime

    async def empty_events():
        if False:
            yield None

    mock_pipeline.subscribe_event = empty_events

    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()
    shutdown.set()

    await run_parrot_cmd(runtime, shutdown, None, spinner)

    mock_pipeline.set_active_profile.assert_not_called()
