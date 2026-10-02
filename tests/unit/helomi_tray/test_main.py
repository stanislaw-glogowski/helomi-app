import runpy
import sys
from unittest.mock import MagicMock, patch

from helomi_foundation import LogLevel
from helomi_tray.main import main, parse_args, run


def test_parse_args_and_run():
    with patch.object(sys, "argv", ["helomi-tray", "--debug"]):
        args = parse_args()
    assert args.debug

    app = MagicMock()
    with (
        patch("helomi_tray.main.configure_logger") as configure,
        patch("helomi_tray.main.Application") as application,
        patch("helomi_tray.main.TrayApplication", return_value=app) as app_class,
        patch("helomi_tray.main.signal.signal") as register_signal,
    ):
        run(args)
    configure.assert_called_once_with(LogLevel.DEBUG)
    application.assert_called_once_with(serve_api=True)
    app_class.assert_called_once_with(application=application.return_value)
    assert register_signal.call_count == 2
    app.run.assert_called_once()


def test_run_handles_keyboard_interrupt_and_main():
    args = MagicMock(debug=False)
    app = MagicMock()
    app.run.side_effect = KeyboardInterrupt
    with (
        patch("helomi_tray.main.configure_logger") as configure,
        patch("helomi_tray.main.Application"),
        patch("helomi_tray.main.TrayApplication", return_value=app),
        patch("helomi_tray.main.signal.signal"),
    ):
        run(args)
    configure.assert_called_once_with(LogLevel.INFO)
    app.quit.assert_called_once()

    with (
        patch("helomi_tray.main.load_dotenv") as load,
        patch("helomi_tray.main.parse_args", return_value=args),
        patch("helomi_tray.main.run") as run_app,
    ):
        main()
    load.assert_called_once()
    run_app.assert_called_once_with(args)


def test_package_main_entrypoint():
    with (
        patch("helomi_tray.main.main") as entry,
        patch.object(sys, "argv", ["helomi-tray"]),
    ):
        runpy.run_module("helomi_tray", run_name="__main__")
    entry.assert_called_once()
