import argparse
import asyncio
import warnings

from helomi_common import LogLevel, configure_logger
from helomi_core import Runtime
from helomi_tray.app import TrayApp

warnings.filterwarnings(
    "ignore",
    message=r".*leaked semaphore objects.*",
    category=UserWarning,
    module=r".*resource_tracker.*",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="helomi-tray",
        description="Helomi System Tray App",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    return parser.parse_args()


async def run(_: argparse.Namespace) -> None:
    runtime = Runtime()
    app = TrayApp(runtime=runtime)
    app.run()


def main() -> None:
    args = parse_args()
    configure_logger(
        LogLevel.TRACE if args.debug else LogLevel.INFO,
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
