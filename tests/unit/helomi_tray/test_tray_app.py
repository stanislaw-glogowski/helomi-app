import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import rumps

from helomi_core.server import ServerSettings
from helomi_core.speech import ProfileActivated, ProfileDeactivated, TranscriptionReady
from helomi_tray.app import HelomiTrayApp
from helomi_tray.main import main


@pytest.fixture(autouse=True)
def mock_pipeline_cls():
    with patch("helomi_core.speech.SpeechPipeline") as mock_cls:
        mock_pipe = mock_cls.return_value
        mock_pipe.__aenter__.return_value = mock_pipe
        mock_pipe.__aexit__.return_value = None
        mock_pipe.activate_profile = AsyncMock(return_value=True)
        mock_pipe.deactivate_profile = AsyncMock(return_value=True)
        mock_pipe.say_text = AsyncMock(return_value=True)
        mock_pipe.publish = AsyncMock(return_value=True)
        mock_pipe.active_profile = None

        async def empty_subscribe():
            if False:
                yield None

        mock_pipe.subscribe = empty_subscribe
        yield mock_cls


def test_tray_app_initialization(mock_catalog) -> None:
    custom_config = ServerSettings(host="192.168.1.5", port=8181)
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        config=custom_config,
        start_service=False,
    )
    assert app.title == "⏳ Helomi"
    assert app.config is custom_config
    assert app.config.host == "192.168.1.5"
    assert app.config.port == 8181
    assert not app.parrot_mode
    assert not app.interactive_menu_enabled
    assert app.active_profile_id is None
    assert app.service is not None
    assert app.server is not None

    # Check menu items
    menu_keys = list(app.menu.keys())
    assert "Profiles" in menu_keys
    assert "🦜 Parrot Mode" in menu_keys
    assert "Quit" in menu_keys
    assert "🌐 API: http://192.168.1.5:8181" in menu_keys


def test_tray_app_profile_events_and_title(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )

    # 0. Service ready signal enables menu and updates title
    app._handle_event(None)
    assert app.interactive_menu_enabled
    assert app.title == "👂 Helomi"

    # 1. ProfileActivated
    app._handle_event(ProfileActivated(profile_id="default"))
    assert app.active_profile_id == "default"
    assert app.title == "🟢 Default"
    assert app._profile_items["default"].state == 1

    # 2. ProfileDeactivated
    app._handle_event(ProfileDeactivated(profile_id="default"))
    assert app.active_profile_id is None
    assert app.title == "👂 Helomi"
    assert app._profile_items["default"].state == 0


def test_tray_app_parrot_mode_toggle_and_transcription(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )

    loop = asyncio.new_event_loop()
    app._loop = loop
    app._service.say_text = AsyncMock()

    try:
        parrot_item = app._parrot_item
        # Toggle on
        app.on_toggle_parrot_mode(parrot_item)
        assert app.parrot_mode
        assert parrot_item.state == 1
        assert app.title == "🦜 Helomi"

        # Activate profile while parrot mode is ON
        app._handle_event(ProfileActivated(profile_id="default"))
        assert app.title == "🦜 Default"
        assert app._profile_items["default"].state == 1
        assert app._deactivate_item.state == 0

        # Transcription event should trigger say_text
        app._handle_event(TranscriptionReady(profile_id="default", text="Echo me"))
        loop.run_until_complete(asyncio.sleep(0.01))
        app._service.say_text.assert_called_with("Echo me", "default")

        # ProfileDeactivated while parrot mode is on deactivates cleanly
        app._handle_event(ProfileDeactivated(profile_id="default"))
        assert app.title == "🦜 Helomi"
        assert app._profile_items["default"].state == 0
        assert app._deactivate_item.state == 1

        # Toggle off
        app.on_toggle_parrot_mode(parrot_item)
        assert not app.parrot_mode
        assert parrot_item.state == 0
        assert app.title == "👂 Helomi"
    finally:
        loop.close()


def test_tray_app_select_and_deactivate_profile(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )

    loop = asyncio.new_event_loop()
    app._loop = loop
    app._service.activate_profile = AsyncMock()
    app._service.deactivate_profile = AsyncMock()

    try:
        # Select profile
        item = app._profile_items["default"]
        app.on_select_profile(item)
        loop.run_until_complete(asyncio.sleep(0.01))
        app._service.activate_profile.assert_called_with("default")

        # Deactivate profile
        app.on_deactivate_profile(MagicMock(spec=rumps.MenuItem))
        loop.run_until_complete(asyncio.sleep(0.01))
        app._service.deactivate_profile.assert_called_with()
    finally:
        loop.close()


def test_tray_app_timer_tick(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )

    app._on_service_event(ProfileActivated(profile_id="default"))
    assert not app._ui_queue.empty()

    app._on_timer_tick()
    assert app._ui_queue.empty()
    assert app.active_profile_id == "default"


def test_tray_app_quit(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )

    with patch("rumps.quit_application") as mock_quit:
        app.on_quit()
        assert app.title == "⏳ Quitting..."
        assert mock_quit.called


def test_tray_app_service_loop(mock_catalog) -> None:
    with patch("rumps.quit_application"):
        app = HelomiTrayApp(
            local_catalog=mock_catalog,
            start_service=False,
        )
        app._service.__aenter__ = AsyncMock(return_value=app._service)
        app._service.__aexit__ = AsyncMock(return_value=None)
        app._service.add_listener = MagicMock()

        app._start_service_thread()
        app._service_ready.wait(timeout=2.0)
        app._on_service_event(TranscriptionReady(profile_id="default", text="hi"))
        app._on_timer_tick()
        app.on_quit()


def test_tray_main_entrypoint(mock_catalog) -> None:
    with (
        patch("helomi_tray.main.LocalStore", return_value=mock_catalog),
        patch("helomi_tray.main.configure_logger") as mock_conf,
        patch("helomi_tray.main.HelomiTrayApp") as mock_app_cls,
        patch.object(
            sys,
            "argv",
            ["helomi-tray", "-d"],
        ),
    ):
        mock_app = mock_app_cls.return_value
        main()
        assert mock_conf.called
        log_fmt = mock_conf.call_args[0][0]
        formatted = log_fmt({"level": "INFO", "message": "hello"})
        assert "INFO" in formatted
        assert "hello" in formatted

        mock_app_cls.assert_called_with(local_catalog=mock_catalog)
        assert mock_app.run.called


def test_cleanup_external_resources() -> None:
    from helomi_tray.app import _cleanup_external_resources

    # Normal cleanup
    _cleanup_external_resources()

    # Cleanup with error
    with (
        patch(
            "joblib.externals.loky.get_reusable_executor",
            side_effect=RuntimeError("loky error"),
        ),
        patch(
            "atexit._run_exitfuncs",
            side_effect=RuntimeError("atexit error"),
        ),
    ):
        _cleanup_external_resources()


def test_tray_app_disable_enable_menu_items_none(mock_catalog) -> None:
    app = HelomiTrayApp(
        local_catalog=mock_catalog,
        start_service=False,
    )
    app._deactivate_item = None
    app._parrot_item = None
    app._disable_interactive_menu_items()
    assert not app.interactive_menu_enabled
    app._enable_interactive_menu_items()
    assert app.interactive_menu_enabled
