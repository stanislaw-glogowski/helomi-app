import asyncio
import runpy
import sys
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    SynthesisReady,
)
from helomi_core.server import ServerExtension
from helomi_tray.app import (
    App,
    AppIcon,
    AppMode,
    AppState,
    AppStatus,
)
from helomi_tray.main import main, parse_args, run


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()

    mock_profile1 = MagicMock()
    mock_profile1.id = "alexa"
    mock_profile1.name = "Alexa"
    mock_profile1.emoji = "👩🏻"

    mock_profile2 = MagicMock()
    mock_profile2.id = "gizmo"
    mock_profile2.name = "Gizmo"
    mock_profile2.emoji = None

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
    assert app._state.room_voice is True
    assert app._state.wake_word is True

    assert "alexa" in app._menu_profiles
    assert "gizmo" in app._menu_profiles
    assert app._menu_profiles["alexa"].key == "0"
    assert app._menu_profiles["gizmo"].key == "1"

    assert app._menu_settings.title == "Settings"
    assert app._menu_room_voice.title == "Room Voice"
    assert app._menu_wake_word.title == "Wake Word"
    assert app._menu_room_voice.state == 0
    assert app._menu_wake_word.state == 0

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
    )
    app._sync_state(None)

    assert app.title == "👩🏻 Alexa"
    assert app._menu_profiles["alexa"].state == 1
    assert app._menu_profiles["gizmo"].state == 0
    assert app._menu_server.title == "API: http://127.0.0.1:8181"
    assert app._menu_parrot.state == 0
    assert app._menu_tts.callback == app._handle_tts_open
    assert app._menu_room_voice.state == 1
    assert app._menu_wake_word.state == 1
    assert app._menu_room_voice.callback == app._handle_room_voice_toggle
    assert app._menu_wake_word.callback == app._handle_wake_word_toggle

    # Calling again with identical state does nothing
    with patch.object(app, "_runtime") as mock_rt:
        app._sync_state(None)
        mock_rt.profiles.get.assert_not_called()

    # 2. Transition with gizmo profile (emoji is None -> fallback to PROFILE icon)
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id="gizmo",
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.PROFILE} Gizmo"
    assert app._menu_profiles["alexa"].state == 0
    assert app._menu_profiles["gizmo"].state == 1

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
    assert app._menu_parrot.state == 1

    # 4. Switch profile to None in Parrot mode
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.PARROT,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.PARROT} Helomi"
    assert app._menu_profiles["alexa"].state == 0
    assert app._menu_profiles["gizmo"].state == 0
    assert app._menu_parrot.state == 1

    # 5. Switch to TTS mode (Settings items disabled and states reset to 0)
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.TTS,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.TTS} Helomi"
    assert app._menu_server.title == "API Disabled"
    assert app._menu_parrot.state == 0
    assert app._menu_room_voice.state == 0
    assert app._menu_wake_word.state == 0
    assert app._menu_room_voice.callback is None
    assert app._menu_wake_word.callback is None

    # 6. Idle in SERVER mode with no profile
    app._state = AppState(
        status=AppStatus.RUNNING,
        profile_id=None,
        mode=AppMode.SERVER,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_state(None)
    assert app.title == f"{AppIcon.EAR} Helomi"


def test_tray_app_sync_state_quiting(mock_runtime):
    """Verify _sync_state sets EXIT icon and clears callbacks on quiting."""
    app = App(runtime=mock_runtime)
    app._last_state = AppState(status=AppStatus.RUNNING)
    app._state = AppState(status=AppStatus.QUITING)

    app._sync_state(None)

    assert app.title == f"{AppIcon.QUITING} Helomi"
    assert app._menu_server.title == "Stopping Server"
    assert app._menu_parrot.state == 0
    assert app._menu_parrot.callback is None
    assert app._menu_tts.callback is None

    for menu_item in app._menu_profiles.values():
        assert menu_item.state == 0
        assert menu_item.callback is None


def test_tray_app_handle_profile_toggle(mock_runtime):
    """Verify clicking profile menu items activates or deactivates profiles."""
    app = App(runtime=mock_runtime)
    app._pipeline_execute_command = MagicMock()

    # If item is currently active (state == 1), clicking deactivates
    item = app._menu_profiles["alexa"]
    item.state = 1
    app._handle_profile_toggle(item)
    app._pipeline_execute_command.assert_called_once()
    assert isinstance(app._pipeline_execute_command.call_args[0][0], DeactivateProfile)

    # If item is inactive (state == 0), clicking activates
    item.state = 0
    app._pipeline_execute_command.reset_mock()
    app._handle_profile_toggle(item)
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, ActivateProfile)
    assert cmd.profile_id == "alexa"


def test_tray_app_handle_parrot_toggle(mock_runtime):
    """Verify clicking parrot menu item toggles mode and closes active window."""
    app = App(runtime=mock_runtime)
    app._set_mode = MagicMock()

    mock_win = MagicMock()
    app._current_window = mock_win

    # When state is 0, switches to PARROT and closes open window
    app._menu_parrot.state = 0
    app._handle_parrot_toggle(app._menu_parrot)
    mock_win.close.assert_called_once()
    assert app._current_window is None
    app._set_mode.assert_called_once_with(AppMode.PARROT)

    # When state is 1, switches back to SERVER
    app._set_mode.reset_mock()
    app._menu_parrot.state = 1
    app._handle_parrot_toggle(app._menu_parrot)
    app._set_mode.assert_called_once_with(AppMode.SERVER)


def test_tray_app_handle_settings_toggles(mock_runtime):
    """Verify clicking Room Voice and Wake Word toggles options and calls pipeline."""
    app = App(runtime=mock_runtime)
    app._pipeline_set_option = MagicMock()

    # 1. Toggle Room Voice off (from state 1 -> 0)
    app._menu_room_voice.state = 1
    app._handle_room_voice_toggle(app._menu_room_voice)
    assert app._state.room_voice is False
    app._pipeline_set_option.assert_called_once_with("room_voice", False)

    # 2. Toggle Room Voice on (from state 0 -> 1)
    app._pipeline_set_option.reset_mock()
    app._menu_room_voice.state = 0
    app._handle_room_voice_toggle(app._menu_room_voice)
    assert app._state.room_voice is True
    app._pipeline_set_option.assert_called_once_with("room_voice", True)

    # 3. Toggle Wake Word off (from state 1 -> 0)
    app._pipeline_set_option.reset_mock()
    app._menu_wake_word.state = 1
    app._handle_wake_word_toggle(app._menu_wake_word)
    assert app._state.wake_word is False
    app._pipeline_set_option.assert_called_once_with("wake_word", False)

    # 4. Toggle Wake Word on (from state 0 -> 1)
    app._pipeline_set_option.reset_mock()
    app._menu_wake_word.state = 0
    app._handle_wake_word_toggle(app._menu_wake_word)
    assert app._state.wake_word is True
    app._pipeline_set_option.assert_called_once_with("wake_word", True)


def test_tray_app_pipeline_set_option(mock_runtime):
    """Verify _pipeline_set_option schedules coroutine on loop thread-safely."""
    app = App(runtime=mock_runtime)
    app._pipeline = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    app._loop = mock_loop

    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        app._pipeline_set_option("room_voice", False)
        mock_rcts.assert_called_once()
        app._pipeline.set_option.assert_called_once_with("room_voice", False)

    # When pipeline or loop is closed, does nothing
    mock_loop.is_closed.return_value = True
    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        app._pipeline_set_option("room_voice", True)
        mock_rcts.assert_not_called()


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
        app._pipeline.set_active_extension.assert_called_once_with(ParrotExtension)

    app._pipeline.set_active_extension.reset_mock()
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.SERVER)
        assert app._state.mode == AppMode.SERVER
        mock_run_coro.assert_called_once()
        app._pipeline.set_active_extension.assert_called_once_with(ServerExtension)

    app._pipeline.set_active_extension.reset_mock()
    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._set_mode(AppMode.TTS)
        assert app._state.mode == AppMode.TTS
        mock_run_coro.assert_called_once()
        app._pipeline.set_active_extension.assert_called_once_with(None)

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
    """Verify _open_window and _handle_tts_open manage window lifecycle."""
    from helomi_tray.app.windows import TTSWindow

    app = App(runtime=mock_runtime)
    app._state = replace(app._state, mode=AppMode.SERVER)

    def _mock_set_mode(mode: AppMode) -> None:
        app._state = replace(app._state, mode=mode)

    app._set_mode = MagicMock(side_effect=_mock_set_mode)

    mock_win1 = MagicMock(spec=TTSWindow)
    mock_win2 = MagicMock()

    # 1. Open mock_win1 in TTS mode
    app._open_window(mock_win1, AppMode.TTS)
    assert app._previous_mode == AppMode.SERVER
    assert app._current_window is mock_win1
    app._set_mode.assert_called_once_with(AppMode.TTS)
    mock_win1.show.assert_called_once()

    # 2. Re-opening the same window in the same mode does not close or re-set mode
    app._set_mode.reset_mock()
    mock_win1.show.reset_mock()
    app._open_window(mock_win1, AppMode.TTS)
    mock_win1.close.assert_not_called()
    app._set_mode.assert_not_called()
    mock_win1.show.assert_called_once()

    # 3. Opening another window closes previous window
    app._open_window(mock_win2, AppMode.TTS)
    mock_win1.close.assert_called_once()
    assert app._current_window is mock_win2

    # 4. _handle_tts_close restores previous mode
    app._set_mode.reset_mock()
    app._handle_tts_close()
    assert app._current_window is None
    app._set_mode.assert_called_once_with(AppMode.SERVER)

    # 5. _handle_tts_open creates TTSWindow
    with patch.object(TTSWindow, "show") as mock_show:
        app._handle_tts_open(None)
        assert isinstance(app._current_window, TTSWindow)
        mock_show.assert_called_once()

        # Calling again when current_window is already TTSWindow activates it
        with patch.object(app._current_window, "activate") as mock_activate:
            app._handle_tts_open(None)
            mock_activate.assert_called_once()


def test_tray_app_handle_tts_send(mock_runtime):
    """Verify _handle_tts_send executes SayText pipeline command with active profile."""
    app = App(runtime=mock_runtime)
    app._state = replace(app._state, profile_id="test_pid")
    app._pipeline_execute_command = MagicMock()

    app._handle_tts_send("Hello from TTS")
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, SayText)
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
        cmd = DeactivateProfile()
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
    app._current_window = mock_win

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
        assert app._current_window is None
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
    app._current_window = mock_win

    mock_pipeline = MagicMock()
    synthesis_event = SynthesisReady(profile_id="gizmo", text="hello", audio=None)

    async def mock_subscribe():
        yield ProfileActivated(profile_id="gizmo")
        yield synthesis_event
        yield ProfileDeactivated(profile_id="gizmo")

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
    assert app._menu_profiles["prof_0"].key == "0"
    assert app._menu_profiles["prof_8"].key == "8"
    assert not app._menu_profiles["prof_9"].key
    assert not app._menu_profiles["prof_10"].key


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
