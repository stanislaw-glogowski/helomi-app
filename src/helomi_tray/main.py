import argparse
import asyncio
import warnings

from helomi_app import Runtime
from helomi_common import LogLevel, configure_logger
from helomi_tray.app import TrayApp

warnings.filterwarnings(
    "ignore",
    message=r".*leaked semaphore objects.*",
    category=UserWarning,
    module=r".*resource_tracker.*",
)


def main() -> None:
    args = _parse_args()
    configure_logger(
        LogLevel.DEBUG if args.debug else LogLevel.INFO,
    )
    asyncio.run(_run(args))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="helomi-tray",
        description="helomi System Tray App",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    return parser.parse_args()


async def _run(_: argparse.Namespace) -> None:

    runtime = Runtime()

    app = TrayApp(runtime=runtime)
    app.run()


if __name__ == "__main__":
    main()
