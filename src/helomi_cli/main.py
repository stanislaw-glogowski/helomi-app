import argparse
import asyncio
import signal
from contextlib import suppress

from helomi_cli import Spinner, run_install_cmd, run_parrot_cmd, run_serve_cmd
from helomi_common import LogLevel, configure_logger
from helomi_core import Runtime, __version__


def parse_args(default_cmd="install") -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="helomi-cli",
        description="Helomi CLI",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit",
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
        help="Installs models and dependencies",
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
        command=default_cmd,
        profile_id=None,
    )

    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    debug = args.debug

    logger = configure_logger(LogLevel.DEBUG if debug else LogLevel.INFO)
    runtime = Runtime()
    spinner = Spinner(debug)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    try:
        with suppress(asyncio.exceptions.CancelledError, TimeoutError):
            profile_id = args.profile_id if isinstance(args.profile_id, str) else None

            async with runtime:
                match args.command:
                    case "install":
                        await run_install_cmd(runtime, spinner)
                    case "parrot":
                        await run_parrot_cmd(runtime, shutdown, profile_id, spinner)
                    case "serve" | "server":
                        await run_serve_cmd(runtime, shutdown, spinner)
    except Exception as err:
        if debug:
            raise err
        else:
            logger.exception(err)


def main():
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
