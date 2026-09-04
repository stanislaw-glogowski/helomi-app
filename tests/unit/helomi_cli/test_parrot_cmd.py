import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.pipeline import ProfileActivated, ProfileDeactivated, TranscriptionReady
from helomi_cli.commands.parrot import run_parrot_cmd
from helomi_cli.widgets import Spinner


@pytest.mark.asyncio
async def test_run_parrot_cmd_lifecycle():
    """Verify run_parrot_cmd starts extension, activates profile, monitors events."""
    mock_profile = MagicMock()
    mock_profile.id = "test_profile"
    mock_profile.name = "Test Profile"
    mock_profile.wakeword.adapter = "openwakeword"
    mock_profile.stt.adapter = "parakeet"
    mock_profile.tts.adapter = "voxcpm2"

    mock_profiles = MagicMock()
    mock_profiles.get.return_value = mock_profile

    mock_pipeline = MagicMock()
    mock_pipeline.activate_profile = AsyncMock()

    async def mock_events():
        yield ProfileActivated(profile_id="test_profile")
        yield TranscriptionReady(profile_id="test_profile", text="Hello world")
        yield ProfileDeactivated(profile_id="test_profile")

    mock_pipeline.subscribe = mock_events

    mock_runtime = MagicMock()
    mock_runtime.profiles = mock_profiles
    mock_runtime.get_parrot_extension = AsyncMock()
    mock_runtime.get_pipeline_service = AsyncMock(return_value=mock_pipeline)

    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.05)
        shutdown.set()

    task = asyncio.create_task(trigger_shutdown())
    await run_parrot_cmd(mock_runtime, shutdown, "test_profile", spinner)
    await task

    mock_runtime.get_parrot_extension.assert_called_once()
    mock_runtime.get_pipeline_service.assert_called_once()
    mock_pipeline.activate_profile.assert_called_once_with("test_profile")


@pytest.mark.asyncio
async def test_run_parrot_cmd_no_profile():
    """Verify run_parrot_cmd without profile_id does not call activate_profile."""
    mock_profile = MagicMock()
    mock_profile.id = "default"
    mock_profile.name = "Default Profile"
    mock_profile.wakeword.adapter = "openwakeword"
    mock_profile.stt.adapter = "parakeet"
    mock_profile.tts.adapter = "voxcpm2"

    mock_profiles = MagicMock()
    mock_profiles.get.return_value = mock_profile

    mock_pipeline = MagicMock()
    mock_pipeline.activate_profile = AsyncMock()

    async def empty_events():
        if False:
            yield None

    mock_pipeline.subscribe = empty_events

    mock_runtime = MagicMock()
    mock_runtime.profiles = mock_profiles
    mock_runtime.get_parrot_extension = AsyncMock()
    mock_runtime.get_pipeline_service = AsyncMock(return_value=mock_pipeline)

    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()
    shutdown.set()

    await run_parrot_cmd(mock_runtime, shutdown, None, spinner)

    mock_pipeline.activate_profile.assert_not_called()
