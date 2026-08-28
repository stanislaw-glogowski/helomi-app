import argparse
import asyncio
import signal

import loguru

from helomi_cli.install import run_install_cmd
from helomi_cli.profiles import run_profiles_cmd
from helomi_cli.say import run_say_cmd
from helomi_cli.settings import run_settings_cmd
from helomi_cli.widgets import Spinner
from helomi_common import LogLevel, configure_logger
from helomi_core.resources import LocalStore

_DEFAULT_CMD = "install"


def main():
    args = _parse_args()
    configure_logger(_format_log, LogLevel.DEBUG if args.debug else LogLevel.INFO)
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

    # cli say
    cmd_parsers.add_parser(
        "say",
        help="Live speech-to-text with hybrid voice/text input",
    ).add_argument(
        "profile_id",
        nargs="?",
        default=None,
        help="Optional profile ID to activate",
    )

    # cli profiles
    cmd_parsers.add_parser(
        "profiles",
        help="Print profile(s)",
    ).add_argument(
        "profile_id",
        nargs="?",
        default=None,
        help="Optional profile ID to print",
    )

    # cli settings
    cmd_parsers.add_parser(
        "settings",
        help="Print settings",
    )

    parser.set_defaults(
        command=_DEFAULT_CMD,
        print_target=None,
        profile_id=None,
    )

    return parser.parse_args()


def _format_log(record: loguru.Record) -> str:
    extra = record["extra"]
    path: list[str] = []

    if (comp := extra.get("component")) and isinstance(comp, str) and comp:
        path.append(comp)

    match extra.get("context"):
        case str(ctx) if ctx:
            path.append(ctx)
        case list(items):
            path.extend(c for c in items if isinstance(c, str) and c)

    parts = filter(
        None,
        [
            "<level>{level: <8}</level>",
            f"<cyan>{'.'.join(path)}</cyan>" if path else None,
            "<level>{message}</level>",
        ],
    )
    return " | ".join(parts)


async def _run(args: argparse.Namespace) -> None:
    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    local_store = LocalStore()
    spinner = Spinner(args.debug)

    match args.command:
        case "install":
            await run_install_cmd(
                local_catalog=local_store,
                spinner=spinner,
            )
        case "say":
            await run_say_cmd(
                local_catalog=local_store,
                spinner=spinner,
                shutdown=shutdown,
                profile_id=args.profile_id,
            )
        case "profiles":
            run_profiles_cmd(
                local_catalog=local_store,
                profile_id=args.profile_id,
            )
        case "settings":
            run_settings_cmd(
                local_catalog=local_store,
            )


if __name__ == "__main__":
    main()
