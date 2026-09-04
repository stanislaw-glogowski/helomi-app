import argparse
import asyncio
import signal

from helomi_app import Runtime
from helomi_cli.commands import run_install_cmd, run_parrot_cmd, run_serve_cmd
from helomi_cli.widgets import Spinner
from helomi_common import LogLevel, configure_logger

_DEFAULT_CMD = "install"


def main():
    args = _parse_args()
    configure_logger(LogLevel.DEBUG if args.debug else LogLevel.INFO)
    asyncio.run(_run(args))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="helomi-cli",
        description="Helomi CLI",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    # Top-level commands
    cmd_parsers = parser.add_subparsers(
        dest="command",
        required=False,
        help="Supported commands:",
    )

    # cli install
    cmd_parsers.add_parser(
        "install",
        help="(TODO: add description)",
    )

    # cli parrot
    cmd_parsers.add_parser(
        "parrot",
        help="Live speech-to-text with hybrid voice/text input",
    ).add_argument(
        "profile_id",
        nargs="?",
        default=None,
        help="Optional profile ID to activate",
    )

    # cli serve
    cmd_parsers.add_parser(
        "serve",
        aliases=["server"],
        help="Start local FastAPI server for speech pipeline",
    )

    parser.set_defaults(
        command=_DEFAULT_CMD,
        profile_id=None,
    )

    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    runtime = Runtime()
    spinner = Spinner(args.debug)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    profile_id = args.profile_id if isinstance(args.profile_id, str) else None

    async with runtime:
        match args.command:
            case "install":
                await run_install_cmd(runtime, spinner)
            case "parrot":
                await run_parrot_cmd(runtime, shutdown, profile_id, spinner)
            case "serve" | "server":
                await run_serve_cmd(runtime, shutdown, spinner)


if __name__ == "__main__":
    main()
