import argparse
import asyncio
import signal

import loguru

from helomi_cli.print import run_print_cmd
from helomi_cli.say import run_say_cmd
from helomi_cli.widgets import Spinner
from helomi_common import LogLevel, configure_logger
from helomi_core import Runtime

_DEFAULT_CMD = "say"


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

    # Top-level commands (live, print)
    cmd_parsers = parser.add_subparsers(
        dest="command",
        required=False,
        help="Supported commands:",
    )

    # 1. cli live
    cmd_parsers.add_parser(
        "say",
        help="Live speech-to-text with hybrid voice/text input",
    ).add_argument(
        "profile_id",
        nargs="?",  # Optional positional argument
        default=None,
        help="Optional profile ID to activate",
    )

    # 2. cli print ...
    print_parser = cmd_parsers.add_parser(
        "print",
        help="Print configuration, settings, or profiles",
    )

    # Nested subparsers under 'print' (settings, profiles)
    print_subparsers = print_parser.add_subparsers(
        dest="print_target",
        required=False,  # Allows running bare `cli print`
        help="Print specific section:",
    )

    # 2a. cli print settings
    print_subparsers.add_parser(
        "settings",
        help="Print settings only",
    )

    # 2b. cli print profiles [profile_id]
    profiles_parser = print_subparsers.add_parser(
        "profiles",
        help="Print profiles",
    )
    profiles_parser.add_argument(
        "profile_id",
        nargs="?",  # Optional positional argument
        default=None,
        help="Optional profile ID to print a specific profile",
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

    runtime = Runtime()
    spinner = Spinner(args.debug)

    match args.command:
        case "say":
            await run_say_cmd(
                runtime=runtime,
                spinner=spinner,
                shutdown=shutdown,
                profile_id=args.profile_id,
            )
        case "print":
            match target := args.print_target:
                case "settings" | "profiles":
                    run_print_cmd(
                        runtime=runtime,
                        target=target,
                        profile_id=args.profile_id,
                    )
                case _:
                    run_print_cmd(runtime)


if __name__ == "__main__":
    main()
