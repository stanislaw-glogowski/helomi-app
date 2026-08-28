import asyncio
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_cli.main import _format_log, _parse_args, _run, main
from helomi_core.resources import LocalCatalog


def test_cli_parse_args_defaults():
    """Verify CLI argument parser defaults to install command with no profile."""
    with patch.object(sys, "argv", ["helomi-cli"]):
        args = _parse_args()
        assert args.command == "install"
        assert args.profile_id is None
        assert not args.debug


def test_cli_parse_args_commands():
    """Verify CLI argument parser parses all supported commands."""
    # 1. install
    with patch.object(sys, "argv", ["helomi-cli", "install"]):
        args = _parse_args()
        assert args.command == "install"

    # 2. say
    with patch.object(sys, "argv", ["helomi-cli", "say"]):
        args = _parse_args()
        assert args.command == "say"
        assert args.profile_id is None

    with patch.object(sys, "argv", ["helomi-cli", "-d", "say", "custom_profile"]):
        args = _parse_args()
        assert args.command == "say"
        assert args.profile_id == "custom_profile"
        assert args.debug

    # 3. serve
    with patch.object(sys, "argv", ["helomi-cli", "serve"]):
        args = _parse_args()
        assert args.command == "serve"

    # 4. profiles
    with patch.object(sys, "argv", ["helomi-cli", "profiles"]):
        args = _parse_args()
        assert args.command == "profiles"
        assert args.profile_id is None

    with patch.object(sys, "argv", ["helomi-cli", "profiles", "prof_1"]):
        args = _parse_args()
        assert args.command == "profiles"
        assert args.profile_id == "prof_1"

    # 5. settings
    with patch.object(sys, "argv", ["helomi-cli", "settings"]):
        args = _parse_args()
        assert args.command == "settings"


def test_format_log_variations():
    """Verify _format_log handles various loguru record extra fields."""
    rec1 = {
        "extra": {"component": "Audio", "context": "Input"},
    }
    fmt1 = _format_log(rec1)  # type: ignore
    assert "Audio.Input" in fmt1
    assert "{message}" in fmt1

    rec2 = {
        "extra": {"component": "Core", "context": ["sub1", "sub2"]},
    }
    fmt2 = _format_log(rec2)  # type: ignore
    assert "Core.sub1.sub2" in fmt2

    rec3 = {
        "extra": {},
    }
    fmt3 = _format_log(rec3)  # type: ignore
    assert "<cyan>" not in fmt3
    assert "{message}" in fmt3


@pytest.mark.asyncio
async def test_cli_run_invokes_commands():
    """Verify _run dispatches commands to respective handlers."""
    with (
        patch("helomi_cli.main.LocalStore"),
        patch("helomi_cli.main.run_install_cmd", new_callable=AsyncMock) as mock_inst,
        patch("helomi_cli.main.run_say_cmd", new_callable=AsyncMock) as mock_say,
        patch("helomi_cli.main.run_serve_cmd", new_callable=AsyncMock) as mock_serve,
        patch("helomi_cli.main.run_profiles_cmd") as mock_prof,
        patch("helomi_cli.main.run_settings_cmd") as mock_sett,
    ):
        # 1. install
        args = MagicMock()
        args.command = "install"
        args.debug = False
        await _run(args)
        assert mock_inst.called

        # 2. say
        args.command = "say"
        args.profile_id = "p1"
        await _run(args)
        assert mock_say.called
        assert mock_say.call_args.kwargs["profile_id"] == "p1"

        # 3. serve
        args.command = "serve"
        await _run(args)
        assert mock_serve.called

        # 4. profiles
        args.command = "profiles"
        args.profile_id = "p2"
        await _run(args)
        assert mock_prof.called
        assert mock_prof.call_args.kwargs["profile_id"] == "p2"

        # 5. settings
        args.command = "settings"
        await _run(args)
        assert mock_sett.called


def test_cli_main_entrypoint():
    """Verify main entrypoint calls configure_logger and asyncio.run."""
    with (
        patch("asyncio.run") as mock_asyncio_run,
        patch("helomi_cli.main.configure_logger") as mock_configure,
        patch.object(sys, "argv", ["helomi-cli", "say"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        main()
        assert mock_configure.called
        assert mock_asyncio_run.called


def test_cli_package_main_execution():
    """Verify importing and running __main__."""
    with (
        patch("asyncio.run") as mock_asyncio_run,
        patch.object(sys, "argv", ["helomi-cli", "say"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        runpy.run_module("helomi_cli", run_name="__main__")


@pytest.mark.asyncio
async def test_run_say_cmd():
    """Verify run_say_cmd manages spinner, tasks, activate_profile and loops."""
    from helomi_cli.say.cmd import run_say_cmd
    from helomi_cli.widgets import Spinner

    spinner = Spinner(disabled=True)
    shutdown = asyncio.Event()
    catalog = MagicMock(spec=LocalCatalog)

    with (
        patch("helomi_cli.say.cmd.Runtime") as mock_runtime_cls,
        patch("helomi_cli.say.cmd.PromptSession"),
    ):
        mock_runtime = mock_runtime_cls.return_value
        mock_pipe = MagicMock()
        mock_pipe.__aenter__.return_value = mock_pipe
        mock_pipe.__aexit__.return_value = None
        mock_pipe.activate_profile = AsyncMock()
        mock_runtime.get_speech_pipeline.return_value = mock_pipe

        shutdown.set()
        await run_say_cmd(catalog, spinner, shutdown, profile_id="test_profile")
        mock_pipe.activate_profile.assert_called_once_with("test_profile")
