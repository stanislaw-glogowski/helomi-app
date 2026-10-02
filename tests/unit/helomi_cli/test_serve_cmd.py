import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app import Application
from helomi_cli.commands.serve import run_serve_cmd
from helomi_cli.widgets import Spinner


@pytest.mark.asyncio
async def test_run_serve_cmd() -> None:
    spinner = MagicMock(spec=Spinner)
    spinner.start = AsyncMock()
    spinner.stop = AsyncMock()

    prof = MagicMock()
    prof.id = "default"
    prof.name = "Default Profile"

    settings = MagicMock()
    settings.audio.drivers = ["avfaudio"]
    settings.detection.wakeword.adapter = "openwakeword"
    settings.detection.vad.adapter = "silero_vad"
    settings.detection.turn.adapter = "smart_turn"
    settings.transcription.adapter = "parakeet"
    settings.synthesis.adapter = "voxcpm2"

    application = MagicMock(spec=Application)
    application.settings = settings
    application.profiles = MagicMock()
    application.profiles.__iter__ = MagicMock(return_value=iter([prof]))

    server = MagicMock()
    server.url = "http://127.0.0.1:8000"
    application.server = server

    shutdown = asyncio.Event()
    shutdown.set()

    await run_serve_cmd(application, shutdown, spinner)

    assert spinner.start.call_count == 2
    assert spinner.stop.call_count == 2
