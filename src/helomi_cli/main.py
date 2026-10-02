import argparse
import asyncio
import signal
import sys
from contextlib import suppress

from dotenv import load_dotenv

from helomi_app import (
    Application,
    LogLevel,
    ResponseMode,
    __version__,
    configure_logger,
)
from helomi_cli import Spinner, run_install_cmd, run_parrot_cmd, run_serve_cmd


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

    cmd_parsers = parser.add_subparsers(
        dest="command",
        required=False,
        help="Supported commands:",
    )

    cmd_parsers.add_parser(
        "install",
        help="Installs models and dependencies",
    )

    cmd_parsers.add_parser(
        "parrot",
        help="Live speech-to-text with hybrid voice/text input",
    ).add_argument(
        "profile_id",
        nargs="?",
        default=None,
        help="Optional profile ID to activate",
    )

    cmd_parsers.add_parser(
        "serve",
        aliases=["server"],
        help="Start the local FastAPI application server",
    )

    parser.set_defaults(
        command=default_cmd,
        profile_id=None,
    )

    return parser.parse_args()


async def run(args: argparse.Namespace):
    logger = configure_logger(LogLevel.DEBUG if args.debug else LogLevel.INFO)
    spinner = Spinner(args.debug)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    try:
        with suppress(asyncio.exceptions.CancelledError, TimeoutError):
            profile_id = args.profile_id if isinstance(args.profile_id, str) else None

            match args.command:
                case "install":
                    await run_install_cmd(Application(), spinner)
                case "parrot":
                    async with Application(response_mode=ResponseMode.PARROT) as app:
                        await run_parrot_cmd(app, shutdown, profile_id, spinner)
                case "serve" | "server":
                    async with Application(
                        serve_api=True,
                        response_mode=ResponseMode.API,
                    ) as app:
                        await run_serve_cmd(app, shutdown, spinner)
    except Exception as error:
        if args.debug:
            raise error
        else:
            logger.exception(error)
            sys.exit(1)


def main():
    load_dotenv(dotenv_path=".env")
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
