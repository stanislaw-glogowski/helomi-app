import asyncio
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_cli.main import _format_log, _parse_args, _run, main


def test_cli_parse_args_defaults():
    """Verify CLI argument parser defaults to say command with no target or profile."""
    with patch.object(sys, "argv", ["helomi-cli"]):
        args = _parse_args()
        assert args.command == "say"
        assert args.profile_id is None
        assert args.print_target is None
        assert not args.debug


def test_cli_parse_args_say():
    """Verify CLI argument parser recognizes say command and debug flags."""
    with patch.object(sys, "argv", ["helomi-cli", "say"]):
        args = _parse_args()
        assert args.command == "say"
        assert args.profile_id is None
        assert not args.debug

    with patch.object(sys, "argv", ["helomi-cli", "-d", "say", "custom_profile"]):
        args = _parse_args()
        assert args.command == "say"
        assert args.profile_id == "custom_profile"
        assert args.debug


def test_cli_parse_args_print():
    """Verify CLI argument parser parses print subcommands."""
    with patch.object(sys, "argv", ["helomi-cli", "print"]):
        args = _parse_args()
        assert args.command == "print"
        assert args.print_target is None
        assert args.profile_id is None

    with patch.object(sys, "argv", ["helomi-cli", "print", "settings"]):
        args = _parse_args()
        assert args.command == "print"
        assert args.print_target == "settings"

    with patch.object(sys, "argv", ["helomi-cli", "print", "profiles"]):
        args = _parse_args()
        assert args.command == "print"
        assert args.print_target == "profiles"
        assert args.profile_id is None

    with patch.object(sys, "argv", ["helomi-cli", "print", "profiles", "prof_1"]):
        args = _parse_args()
        assert args.command == "print"
        assert args.print_target == "profiles"
        assert args.profile_id == "prof_1"


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
async def test_cli_run_invokes_say_cmd():
    """Verify _run executes run_say_cmd when say subcommand is given."""
    with (
        patch("helomi_cli.main.Runtime"),
        patch("helomi_cli.main.run_say_cmd", new_callable=AsyncMock) as mock_say,
    ):
        args = MagicMock()
        args.command = "say"
        args.debug = False
        args.profile_id = "test_profile"
        await _run(args)
        assert mock_say.called
        assert mock_say.call_args.kwargs["profile_id"] == "test_profile"


@pytest.mark.asyncio
async def test_cli_run_invokes_print_cmd_targets():
    """Verify _run executes run_print_cmd with specific targets and fallback."""
    with (
        patch("helomi_cli.main.Runtime"),
        patch("helomi_cli.main.run_print_cmd") as mock_print,
    ):
        # 1. settings
        args = MagicMock()
        args.command = "print"
        args.print_target = "settings"
        args.profile_id = None
        args.debug = False
        await _run(args)
        assert mock_print.called
        assert mock_print.call_args.kwargs["target"] == "settings"

        # 2. profiles
        mock_print.reset_mock()
        args.print_target = "profiles"
        args.profile_id = "p1"
        await _run(args)
        assert mock_print.called
        assert mock_print.call_args.kwargs["target"] == "profiles"
        assert mock_print.call_args.kwargs["profile_id"] == "p1"

        # 3. None / bare print
        mock_print.reset_mock()
        args.print_target = None
        await _run(args)
        assert mock_print.called
        assert (
            "target" not in mock_print.call_args.kwargs
            or mock_print.call_args.kwargs.get("target") is None
        )


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
    mock_runtime = MagicMock()

    with (
        patch("helomi_cli.say.cmd.SpeechPipeline") as mock_pipe_cls,
        patch("helomi_cli.say.cmd.PromptSession"),
    ):
        mock_pipe = mock_pipe_cls.return_value
        mock_pipe.__aenter__.return_value = mock_pipe
        mock_pipe.__aexit__.return_value = None
        mock_pipe.activate_profile = AsyncMock()

        shutdown.set()
        await run_say_cmd(mock_runtime, spinner, shutdown, profile_id="test_profile")
        mock_pipe.activate_profile.assert_called_once_with("test_profile")
