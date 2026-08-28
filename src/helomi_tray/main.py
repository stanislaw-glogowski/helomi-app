import argparse
import warnings

from helomi_common import LogLevel, configure_logger
from helomi_core.resources import LocalStore

from .app import HelomiTrayApp

warnings.filterwarnings(
    "ignore",
    message=r".*leaked semaphore objects.*",
    category=UserWarning,
    module=r".*resource_tracker.*",
)


def main() -> None:
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
    args = parser.parse_args()

    def _log_format(record) -> str:
        level = f"<level>{record['level']: <8}</level>"
        msg = f"<level>{record['message']}</level>"
        return f"{level} | {msg}"

    configure_logger(
        _log_format,
        LogLevel.DEBUG if args.debug else LogLevel.INFO,
    )

    app = HelomiTrayApp(local_catalog=LocalStore())
    app.run()


if __name__ == "__main__":
    main()
