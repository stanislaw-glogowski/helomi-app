import argparse
import signal
import warnings

from dotenv import load_dotenv

from helomi_app import Runtime, __version__
from helomi_app.common import LogLevel, configure_logger
from helomi_tray import App

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

    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    configure_logger(
        LogLevel.DEBUG if args.debug else LogLevel.INFO,
    )
    runtime = Runtime()
    app = App(runtime=runtime)

    def _signal_handler(_sig: int, _frame: object) -> None:
        app.quit()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()


def main() -> None:
    load_dotenv()
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
