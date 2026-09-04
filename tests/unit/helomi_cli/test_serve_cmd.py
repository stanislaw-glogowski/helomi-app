import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app import Runtime
from helomi_app.server.extension import ServerExtension
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

    runtime = MagicMock(spec=Runtime)
    runtime.profiles = MagicMock()
    runtime.profiles.__iter__ = MagicMock(return_value=iter([prof]))
    runtime.profiles.get = MagicMock(return_value=prof)

    server = MagicMock(spec=ServerExtension)
    server.url = "http://127.0.0.1:8000"
    runtime.get_server_extension = AsyncMock(return_value=server)

    shutdown = asyncio.Event()
    shutdown.set()

    await run_serve_cmd(runtime, shutdown, spinner)

    runtime.get_server_extension.assert_called_once()
    assert spinner.start.call_count >= 2
    assert spinner.stop.call_count >= 2
