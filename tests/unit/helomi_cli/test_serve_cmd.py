import asyncio
from unittest.mock import MagicMock, patch

import pytest

from helomi_cli.serve.cmd import run_serve_cmd
from helomi_cli.widgets import Spinner
from helomi_core.resources import LocalCatalog


@pytest.mark.asyncio
async def test_run_serve_cmd() -> None:
    catalog = MagicMock(spec=LocalCatalog)
    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()

    with patch("helomi_cli.serve.cmd.Runtime") as mock_runtime_cls:
        mock_runtime = mock_runtime_cls.return_value
        mock_server = MagicMock()
        mock_server.host = "127.0.0.1"
        mock_server.port = 4356
        mock_server.__aenter__.return_value = mock_server
        mock_server.__aexit__.return_value = None
        mock_runtime.get_server.return_value = mock_server

        shutdown.set()

        await run_serve_cmd(
            local_catalog=catalog,
            spinner=spinner,
            shutdown=shutdown,
        )

        mock_runtime.get_server.assert_called_once()
        mock_server.__aenter__.assert_called_once()
        mock_server.__aexit__.assert_called_once()
