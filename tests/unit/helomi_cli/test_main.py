import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_cli.main import _parse_args, _run, main


def test_cli_parse_args_defaults():
    """Verify CLI argument parser defaults to install command with no profile."""
    with patch.object(sys, "argv", ["helomi-cli"]):
        args = _parse_args()
        assert args.command == "install"
        assert args.profile_id is None
        assert not args.debug


def test_cli_parse_args_commands():
    """Verify CLI argument parser parses all supported commands and options."""
    # 1. install
    with patch.object(sys, "argv", ["helomi-cli", "install"]):
        args = _parse_args()
        assert args.command == "install"

    # 2. parrot
    with patch.object(sys, "argv", ["helomi-cli", "parrot"]):
        args = _parse_args()
        assert args.command == "parrot"
        assert args.profile_id is None

    with patch.object(sys, "argv", ["helomi-cli", "-d", "parrot", "custom_profile"]):
        args = _parse_args()
        assert args.command == "parrot"
        assert args.profile_id == "custom_profile"
        assert args.debug

    # 3. serve & server alias
    with patch.object(sys, "argv", ["helomi-cli", "serve"]):
        args = _parse_args()
        assert args.command == "serve"

    with patch.object(sys, "argv", ["helomi-cli", "server"]):
        args = _parse_args()
        assert args.command == "server"


@pytest.mark.asyncio
async def test_cli_run_invokes_commands():
    """Verify _run dispatches commands to respective handlers within runtime context."""
    with (
        patch("helomi_cli.main.Runtime") as mock_runtime_cls,
        patch("helomi_cli.main.run_install_cmd", new_callable=AsyncMock) as mock_inst,
        patch("helomi_cli.main.run_parrot_cmd", new_callable=AsyncMock) as mock_parrot,
        patch("helomi_cli.main.run_serve_cmd", new_callable=AsyncMock) as mock_serve,
    ):
        mock_runtime = mock_runtime_cls.return_value
        mock_runtime.__aenter__.return_value = mock_runtime
        mock_runtime.__aexit__.return_value = None

        # 1. install
        args = MagicMock()
        args.command = "install"
        args.debug = False
        args.profile_id = None
        await _run(args)
        assert mock_inst.called

        # 2. parrot
        args.command = "parrot"
        args.profile_id = "p1"
        await _run(args)
        assert mock_parrot.called
        assert mock_parrot.call_args.args[2] == "p1"

        # 3. serve
        args.command = "serve"
        await _run(args)
        assert mock_serve.called

        # 4. server alias
        args.command = "server"
        await _run(args)
        assert mock_serve.call_count == 2


def test_cli_main_entrypoint():
    """Verify main entrypoint calls configure_logger and asyncio.run."""
    with (
        patch("asyncio.run") as mock_asyncio_run,
        patch("helomi_cli.main.configure_logger") as mock_configure,
        patch.object(sys, "argv", ["helomi-cli", "parrot"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        main()
        assert mock_configure.called
        assert mock_asyncio_run.called


def test_cli_package_main_execution():
    """Verify importing and running __main__."""
    with (
        patch("asyncio.run") as mock_asyncio_run,
        patch.object(sys, "argv", ["helomi-cli", "parrot"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        runpy.run_module("helomi_cli", run_name="__main__")
