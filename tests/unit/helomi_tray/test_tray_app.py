import asyncio
import runpy
import sys
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayTextCmd,
    SetOptionsCmd,
    SynthesisReadyEvent,
)
from helomi_core.server import ServerExtension
from helomi_tray.app import (
    App,
    AppIcon,
    AppMode,
    AppState,
    AppStatus,
)
from helomi_tray.app.menu import MenuAction
from helomi_tray.main import main, parse_args, run


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()

    mock_profile1 = MagicMock()
    mock_profile1.id = "alexa"
    mock_profile1.name = "Alexa"
    mock_profile1.emoji = "👩🏻"
    mock_profile1.audio.room_voice_path = None

    mock_profile2 = MagicMock()
    mock_profile2.id = "gizmo"
    mock_profile2.name = "Gizmo"
    mock_profile2.emoji = None
    mock_profile2.audio.room_voice_path = None

    profiles = MagicMock()
    profiles.__iter__.return_value = [mock_profile1, mock_profile2]

    def _get_profile(pid: str | None):
        return mock_profile1 if pid in ("alexa", None) else mock_profile2

    profiles.get.side_effect = _get_profile

    runtime.profiles = profiles
    return runtime


def test_tray_app_initialization(mock_runtime):
    """Verify App initializes menus, default state, and title."""
    app = App(runtime=mock_runtime)

    assert app.title == "Helomi"
    assert app._state.status == AppStatus.STARTING
    assert app._state.profile_id is None
    assert app._state.mode == AppMode.SERVER
    assert app._state.server_url is None
    assert app._state.room_voice_enabled is None
    assert app._state.wakeword_enabled is None
    assert app._state.greeting_enabled is None

    assert app._menu_profiles.get_action("alexa").key == "0"
    assert app._menu_profiles.get_action("gizmo").key == "1"

    assert app._menu_settings.title == "Settings"
    assert app._menu_settings.get_action("room_voice_enabled").title == "Room Voice"
    assert app._menu_settings.get_action("wakeword_enabled").title == "Wake Word"
    assert app._menu_settings.get_action("greeting_enabled").title == "Greeting"
    assert app._menu_settings.get_action("room_voice_enabled").state == 0
    assert app._menu_settings.get_action("wakeword_enabled").state == 0

    assert app._menu_server.title == "Starting Server"
    assert app._menu_parrot.title == "Parrot Mode"
    assert app._menu_parrot.key == "p"
    assert app._menu_tts.title == "Text-to-Speech"
    assert app._menu_tts.key == "t"


def test_tray_app_icon_start():
    """Verify AppIcon.Start cycles through spinner states correctly."""
    start = AppIcon.Start()
    assert iter(start) is start
    assert str(start) == "⠋"
    assert str(start) == "⠙"

    # Cycle through remaining states
    cycle = [str(start) for _ in range(8)]
    assert cycle == ["⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    # Cycles back to the beginning
    assert str(start) == "⠋"


def test_tray_app_animate_start_icon(mock_runtime):
    """Verify _animate_start_icon updates title and stops timer when not starting."""
    app = App(runtime=mock_runtime)
    assert app.title == "Helomi"

    app._animate_start_icon(None)
    assert app.title == "⠋ Helomi"

    app._animate_start_icon(None)
    assert app.title == "⠙ Helomi"

    # When status is no longer STARTING, stops timer
    mock_timer = MagicMock()
    app._state = replace(app._state, status=AppStatus.RUNNING)
    app._animate_start_icon(mock_timer)
    mock_timer.stop.assert_called_once()


def test_tray_app_sync_state_running(mock_runtime):
    """Verify _sync_state updates menus, title, and extension states when running."""
    app = App(runtime=mock_runtime)

    # 1. Transition from STARTING to RUNNING with SERVER mode and alexa profile
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id="alexa",
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
        room_voice_enabled=True,
        wakeword_enabled=True,
        greeting_enabled=True,
    )
    app._sync_state(None)

    assert app.title == "👩🏻 Alexa"
    assert app._menu_profiles.get_action("alexa").checked is True
    assert app._menu_profiles.get_action("gizmo").checked is False
    assert app._menu_server.title == "API: http://127.0.0.1:8181"
    assert app._menu_parrot.checked is False
    assert app._menu_tts.enabled is True
    assert app._menu_settings.get_action("room_voice_enabled").checked is True
    assert app._menu_settings.get_action("wakeword_enabled").checked is True
    assert app._menu_settings.get_action("greeting_enabled").checked is True

    # 2. Transition with gizmo profile (emoji is None -> fallback to PROFILE icon)
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id="gizmo",
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.PROFILE} Gizmo"
    assert app._menu_profiles.get_action("alexa").checked is False
    assert app._menu_profiles.get_action("gizmo").checked is True

    # 3. Transition with active profile and Parrot mode
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id="alexa",
        mode=AppMode.PARROT,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.PARROT} Alexa"
    assert app._menu_server.title == "API Disabled"
    assert app._menu_parrot.checked is True

    # 4. Switch profile to None in Parrot mode
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.PARROT,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.PARROT} Helomi"
    assert app._menu_profiles.get_action("alexa").checked is False
    assert app._menu_profiles.get_action("gizmo").checked is False
    assert app._menu_parrot.checked is True

    # 5. Switch to TTS mode (Settings items remain enabled)
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.TTS,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.TTS} Helomi"
    assert app._menu_server.title == "API Disabled"
    assert app._menu_parrot.checked is False
    assert app._menu_settings.get_action("room_voice_enabled").enabled is True
    assert app._menu_settings.get_action("wakeword_enabled").enabled is True

    # 6. Idle in SERVER mode with wakeword_enabled=True and no profile
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
        wakeword_enabled=True,
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.LISTEN} Helomi"

    # 7. Idle in SERVER mode with wakeword_enabled=False and no profile
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
        wakeword_enabled=False,
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.IDLE} Helomi"


def test_tray_app_sync_state_quiting(mock_runtime):
    """Verify _sync_state sets EXIT icon and clears callbacks on quiting."""
    app = App(runtime=mock_runtime)
    app._last_state = AppState(status=AppStatus.RUNNING)
    app._state = AppState(status=AppStatus.QUITING)

    app._sync_state(None)

    assert app.title == f"{AppIcon.QUITING} Helomi"
    assert app._menu_server.title == "Stopping Server"
    assert app._menu_parrot.enabled is False
    assert app._menu_tts.enabled is False
    for action in app._menu_profiles._actions.values():
        assert action.enabled is False


def test_tray_app_handle_profile_toggle(mock_runtime):
    """Verify clicking profile menu items activates or deactivates profiles."""
    app = App(runtime=mock_runtime)
    app._pipeline_execute_command = MagicMock()

    # If item is currently active, clicking deactivates
    item = app._menu_profiles.get_action("alexa")
    item.set_checked(True)
    app._handle_toggle_profile(item)
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, DeactivateProfileCmd)

    # If item is inactive, clicking activates
    item.set_checked(False)
    app._pipeline_execute_command.reset_mock()
    app._handle_toggle_profile(item)
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, ActivateProfileCmd)
    assert cmd.profile_id == "alexa"


def test_tray_app_handle_parrot_toggle(mock_runtime):
    """Verify clicking parrot menu item toggles mode and closes active window."""
    app = App(runtime=mock_runtime)
    app._set_mode = MagicMock()

    mock_win = MagicMock()
    app._window = mock_win

    # When checked is False, switches to PARROT and closes open window
    app._menu_parrot.set_checked(False)
    app._handle_toggle_parrot(app._menu_parrot)
    mock_win.close.assert_called_once()
    assert app._window is None
    app._set_mode.assert_called_once_with(AppMode.PARROT)

    # When checked is True, switches back to SERVER
    app._set_mode.reset_mock()
    app._menu_parrot.set_checked(True)
    app._handle_toggle_parrot(app._menu_parrot)
    app._set_mode.assert_called_once_with(AppMode.SERVER)


def test_tray_app_handle_settings_toggles(mock_runtime):
    """Verify clicking Settings items executes SetOptionsCmd."""
    app = App(runtime=mock_runtime)
    app._pipeline_execute_command = MagicMock()

    # Toggle Room Voice off (from checked True -> False)
    room_voice = app._menu_settings.get_action("room_voice_enabled")
    room_voice.set_checked(True)
    app._handle_toggle_setting(room_voice)
    app._pipeline_execute_command.assert_called_once_with(
        SetOptionsCmd(room_voice_enabled=False)
    )

    # Toggle Room Voice on (from checked False -> True)
    app._pipeline_execute_command.reset_mock()
    room_voice.set_checked(False)
    app._handle_toggle_setting(room_voice)
    app._pipeline_execute_command.assert_called_once_with(
        SetOptionsCmd(room_voice_enabled=True)
    )

    # Toggle Wake Word
    wakeword = app._menu_settings.get_action("wakeword_enabled")
    app._pipeline_execute_command.reset_mock()
    wakeword.set_checked(True)
    app._handle_toggle_setting(wakeword)
    app._pipeline_execute_command.assert_called_once_with(
        SetOptionsCmd(wakeword_enabled=False)
    )

    # Toggle Greeting
    greeting = app._menu_settings.get_action("greeting_enabled")
    app._pipeline_execute_command.reset_mock()
    greeting.set_checked(False)
    app._handle_toggle_setting(greeting)
    app._pipeline_execute_command.assert_called_once_with(
        SetOptionsCmd(greeting_enabled=True)
    )


def test_tray_app_set_mode(mock_runtime):
    """Verify _set_mode sets appropriate extension and dispatches to pipeline."""
    app = App(runtime=mock_runtime)
    app._pipeline = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    app._loop = mock_loop

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.PARROT)
        assert app._state.mode == AppMode.PARROT
        mock_run_coro.assert_called_once()
        app._pipeline.activate_extension.assert_called_once_with(ParrotExtension)

    app._pipeline.activate_extension.reset_mock()
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.SERVER)
        assert app._state.mode == AppMode.SERVER
        mock_run_coro.assert_called_once()
        app._pipeline.activate_extension.assert_called_once_with(ServerExtension)

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.TTS)
        assert app._state.mode == AppMode.TTS
        mock_run_coro.assert_called_once()
        app._pipeline.deactivate_extension.assert_called_once()

    # Without pipeline or loop, does nothing
    app._pipeline = None
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.SERVER)
        mock_run_coro.assert_not_called()

    # When loop is closed, does nothing
    app._pipeline = MagicMock()
    mock_loop.is_closed.return_value = True
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.PARROT)
        mock_run_coro.assert_not_called()


def test_tray_app_handle_window_lifecycle(mock_runtime):
    """Verify _handle_open_window and _handle_close_window manage window lifecycle."""
    from helomi_tray.app.windows import TTSWindow

    app = App(runtime=mock_runtime)
    app._state = replace(app._state, mode=AppMode.SERVER)

    def _mock_set_mode(mode: AppMode) -> None:
        app._state = replace(app._state, mode=mode)

    app._set_mode = MagicMock(side_effect=_mock_set_mode)

    action = app._menu_tts

    with (
        patch.object(TTSWindow, "__init__", return_value=None) as mock_init,
        patch.object(TTSWindow, "show") as mock_show,
        patch.object(TTSWindow, "activate") as mock_activate,
        patch.object(TTSWindow, "close") as mock_close,
    ):
        # 1. Open TTS window
        app._handle_open_window(action)
        assert isinstance(app._window, TTSWindow)
        app._set_mode.assert_called_once_with(AppMode.TTS)
        mock_init.assert_called_once()
        mock_show.assert_called_once()

        # 2. Re-opening already open window activates it
        app._handle_open_window(action)
        mock_activate.assert_called_once()

        # 3. Non-matching sender action does nothing
        dummy_action = MenuAction(
            id="unknown", title="Unknown", callback=lambda _: None
        )
        app._handle_open_window(dummy_action)

        # 4. Closing window restores mode
        app._handle_close_window(AppMode.SERVER)
        assert app._window is None
        mock_close.assert_called_once()
        app._set_mode.assert_called_with(AppMode.SERVER)

        # 5. Closing when no window is open does nothing
        app._handle_close_window()


def test_tray_app_handle_tts_send(mock_runtime):
    """Verify _handle_tts_send executes SayText pipeline command with active profile."""
    app = App(runtime=mock_runtime)
    app._state = replace(app._state, profile_id="test_pid")
    app._pipeline_execute_command = MagicMock()

    app._handle_tts_send("Hello from TTS")
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, SayTextCmd)
    assert cmd.text == "Hello from TTS"
    assert cmd.profile_id == "test_pid"


def test_tray_app_pipeline_execute_command(mock_runtime):
    """Verify _pipeline_execute_command runs pipeline command on event loop."""
    app = App(runtime=mock_runtime)
    app._pipeline = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    app._loop = mock_loop

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        cmd = DeactivateProfileCmd()
        app._pipeline_execute_command(cmd)
        mock_run_coro.assert_called_once()

    # Without pipeline or loop, does nothing
    app._pipeline = None
    app._pipeline_execute_command(cmd)

    # When loop is closed, does nothing
    app._pipeline = MagicMock()
    mock_loop.is_closed.return_value = True
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._pipeline_execute_command(cmd)
        mock_run_coro.assert_not_called()


def test_tray_app_handle_quit_and_exit(mock_runtime):
    """Verify quit flow signals shutdown, closes window, and exits cleanly."""
    app = App(runtime=mock_runtime)
    mock_timer_item = MagicMock()

    with patch("rumps.Timer") as mock_timer_cls:
        app._handle_quit(mock_timer_item)
        assert app._state.status == AppStatus.QUITING
        assert mock_timer_cls.called

    # Test _handle_exit
    mock_win = MagicMock()
    app._window = mock_win

    timer = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    app._loop = mock_loop
    app._shutdown_signal = MagicMock()
    app._thread = MagicMock()
    app._thread.is_alive.return_value = True

    with patch("rumps.quit_application") as mock_quit_app:
        app._handle_exit(timer)
        timer.stop.assert_called_once()
        mock_win.close.assert_called_once()
        assert app._window is None
        mock_loop.call_soon_threadsafe.assert_called_once_with(app._shutdown_signal.set)
        app._thread.join.assert_called_once_with(timeout=5.0)
        mock_quit_app.assert_called_once()


def test_tray_app_update_state(mock_runtime):
    """Verify _update_state updates state fields and handles options."""
    app = App(runtime=mock_runtime)

    app._update_state(server_url="http://new-url")
    assert app._state.server_url == "http://new-url"

    # force_sync calls _sync_state
    with patch.object(app, "_sync_state") as mock_sync:
        app._update_state(force_sync=True)
        mock_sync.assert_called_once_with(None)

    # When status is QUITING, updates are ignored
    app._state = replace(app._state, status=AppStatus.QUITING)
    app._update_state(server_url="http://ignored-url")
    assert app._state.server_url == "http://new-url"


@pytest.mark.asyncio
async def test_tray_app_pipeline_loop(mock_runtime):
    """Verify _pipeline_loop listens to pipeline events and forwards to window."""
    app = App(runtime=mock_runtime)
    mock_win = MagicMock()
    app._window = mock_win

    mock_pipeline = MagicMock()
    synthesis_event = SynthesisReadyEvent(profile_id="gizmo", text="hello", audio=None)

    async def mock_subscribe():
        yield ProfileActivatedEvent(profile_id="gizmo")
        yield synthesis_event
        yield ProfileDeactivatedEvent(profile_id="gizmo")

    mock_pipeline.subscribe_event = mock_subscribe
    app._pipeline = mock_pipeline

    await app._pipeline_loop()

    assert app._state.profile_id is None
    assert mock_win.handle_event.call_count == 3
    mock_win.handle_event.assert_any_call(synthesis_event)

    # Without pipeline, returns early
    app._pipeline = None
    await app._pipeline_loop()


@pytest.mark.asyncio
async def test_tray_app_runtime_loop(mock_runtime):
    """Verify _runtime_loop initializes components and awaits shutdown."""
    app = App(runtime=mock_runtime)

    mock_pipeline = MagicMock()
    mock_profile = MagicMock(id="prof1")
    mock_pipeline.active_profile = mock_profile

    async def empty_events():
        if False:
            yield None

    mock_pipeline.subscribe_event = empty_events

    mock_server_ext = MagicMock()
    mock_server_ext.url = "http://localhost:8181"
    mock_parrot_ext = MagicMock()

    mock_runtime.__aenter__.return_value = mock_runtime
    mock_runtime.__aexit__.return_value = None
    mock_runtime.get_pipeline_service = AsyncMock(return_value=mock_pipeline)
    mock_runtime.get_parrot_extension = AsyncMock(return_value=mock_parrot_ext)
    mock_runtime.get_server_extension = AsyncMock(return_value=mock_server_ext)

    loop_task = asyncio.create_task(app._runtime_loop())
    await asyncio.sleep(0.05)

    assert app._pipeline is mock_pipeline
    assert app._state.status == AppStatus.RUNNING
    assert app._state.server_url == "http://localhost:8181"
    assert app._state.profile_id == "prof1"

    app._shutdown_signal.set()
    await loop_task


def test_tray_app_thread_worker(mock_runtime):
    """Verify _thread_worker initializes event loop and executes runtime loop."""
    app = App(runtime=mock_runtime)
    with patch.object(app, "_runtime_loop", new_callable=AsyncMock) as mock_r_loop:
        app._thread_worker()
        assert app._loop is not None
        mock_r_loop.assert_called_once()


def test_tray_app_thread_worker_exception(mock_runtime):
    """Verify _thread_worker logs exception when runtime loop fails."""
    app = App(runtime=mock_runtime)
    with (
        patch.object(app, "_runtime_loop", side_effect=RuntimeError("boom")),
        patch.object(app._logger, "exception") as mock_log,
    ):
        app._thread_worker()
        mock_log.assert_called_once()


def test_tray_app_thread_worker_cancelled(mock_runtime):
    """Verify _thread_worker cleanly suppresses CancelledError and KeyboardInterrupt."""
    app = App(runtime=mock_runtime)
    with patch.object(app, "_runtime_loop", side_effect=asyncio.CancelledError):
        app._thread_worker()

    with patch.object(app, "_runtime_loop", side_effect=KeyboardInterrupt):
        app._thread_worker()


def test_tray_app_many_profiles_keys():
    """Verify profiles with index >= 9 do not receive a single-digit shortcut."""
    runtime = MagicMock()
    mock_profiles = [
        MagicMock(id=f"prof_{i}", name=f"Profile {i}", emoji=None) for i in range(12)
    ]
    profiles = MagicMock()
    profiles.__iter__.return_value = mock_profiles
    profiles.get.return_value = mock_profiles[0]
    runtime.profiles = profiles

    app = App(runtime=runtime)
    assert app._menu_profiles.get_action("prof_0").key == "0"
    assert app._menu_profiles.get_action("prof_8").key == "8"
    assert not app._menu_profiles.get_action("prof_9").key
    assert not app._menu_profiles.get_action("prof_10").key


def test_tray_app_run(mock_runtime):
    """Verify run starts worker thread and calls rumps.App.run."""
    app = App(runtime=mock_runtime)
    with (
        patch.object(app, "_before_run") as mock_before_run,
        patch("rumps.App.run") as mock_super_run,
    ):
        app.run()
        mock_before_run.assert_called_once()
        mock_super_run.assert_called_once()


def test_tray_main_and_run():
    """Verify helomi_tray.main entrypoints."""
    with patch.object(sys, "argv", ["helomi-tray"]):
        args = parse_args()
        assert not args.debug

    with patch.object(sys, "argv", ["helomi-tray", "-d"]):
        args = parse_args()
        assert args.debug

    with (
        patch("helomi_tray.main.run") as mock_run,
        patch("helomi_tray.main.configure_logger") as mock_conf,
        patch.object(sys, "argv", ["helomi-tray"]),
    ):
        main()
        mock_conf.assert_called_once()
        mock_run.assert_called_once()


def test_tray_run_function():
    """Verify run instantiates Runtime and App and handles signals."""
    with (
        patch("helomi_tray.main.Runtime") as mock_runtime_cls,
        patch("helomi_tray.main.App") as mock_tray_cls,
        patch("signal.signal") as mock_signal,
    ):
        mock_app = mock_tray_cls.return_value
        args = MagicMock()
        args.debug = False
        run(args)
        mock_runtime_cls.assert_called_once()
        mock_tray_cls.assert_called_once_with(runtime=mock_runtime_cls.return_value)
        mock_app.run.assert_called_once()
        assert mock_signal.call_count == 2

        # Test signal handler
        handler = mock_signal.call_args_list[0][0][1]
        handler(2, None)
        mock_app.quit.assert_called_once()

    # Test KeyboardInterrupt
    with (
        patch("helomi_tray.main.Runtime"),
        patch("helomi_tray.main.App") as mock_tray_cls,
        patch("signal.signal"),
    ):
        mock_app = mock_tray_cls.return_value
        mock_app.run.side_effect = KeyboardInterrupt
        args = MagicMock()
        run(args)
        mock_app.quit.assert_called_once()


def test_tray_quit_calls_handle_quit(mock_runtime):
    """Verify app.quit delegates to _handle_quit."""
    app = App(runtime=mock_runtime)
    with patch.object(app, "_handle_quit") as mock_handle:
        app.quit()
        mock_handle.assert_called_once_with(None)


def test_tray_package_main_execution():
    """Verify running helomi_tray __main__."""
    with (
        patch("helomi_tray.main.run") as mock_run,
        patch.object(sys, "argv", ["helomi-tray"]),
    ):
        runpy.run_module("helomi_tray", run_name="__main__")
        mock_run.assert_called_once()
