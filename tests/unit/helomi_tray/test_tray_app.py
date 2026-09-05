import asyncio
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    ProfileDeactivated,
)
from helomi_core.server import ServerExtension
from helomi_tray.app import TrayApp, TrayState, TrayStatus, TryIcon
from helomi_tray.main import main, parse_args, run


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()

    mock_profile1 = MagicMock()
    mock_profile1.id = "default"
    mock_profile1.name = "Default Assistant"

    mock_profile2 = MagicMock()
    mock_profile2.id = "gizmo"
    mock_profile2.name = "Gizmo"

    profiles = MagicMock()
    profiles.__iter__.return_value = [mock_profile1, mock_profile2]

    def _get_profile(pid: str | None):
        return mock_profile1 if pid == "default" else mock_profile2

    profiles.get.side_effect = _get_profile

    runtime.profiles = profiles
    return runtime


def test_tray_app_initialization(mock_runtime):
    """Verify TrayApp initializes menus, default state, and title."""
    app = TrayApp(runtime=mock_runtime)

    assert app.title == f"{TryIcon.START} Helomi"
    assert app._state.status == TrayStatus.STARTING
    assert app._state.profile_id is None
    assert app._state.extension_key is ServerExtension
    assert app._state.server_url is None

    assert "default" in app._menu_profiles
    assert "gizmo" in app._menu_profiles
    assert ServerExtension in app._menu_extensions
    assert ParrotExtension in app._menu_extensions


def test_tray_app_render_title():
    """Verify _render_title formats icons and labels correctly."""
    assert TrayApp._render_title() == f"{TryIcon.START} Helomi"
    title = TrayApp._render_title("Custom", TryIcon.PARROT)
    assert title == f"{TryIcon.PARROT} Custom"


def test_tray_app_sync_ui_running(mock_runtime):
    """Verify _sync_ui updates menus, title, and extension states when running."""
    app = TrayApp(runtime=mock_runtime)

    # Transition from STARTING to RUNNING with SERVER extension and active profile
    app._state = TrayState(
        status=TrayStatus.RUNNING,
        profile_id="default",
        extension_key=ServerExtension,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_ui(None)

    assert app.title == f"{TryIcon.ROBOT} Default Assistant"
    assert app._menu_profiles["default"].state == 1
    assert app._menu_profiles["gizmo"].state == 0
    assert app._menu_extensions[ServerExtension].state == 1
    assert app._menu_extensions[ParrotExtension].state == 0
    assert "http://127.0.0.1:8181" in app._menu_extensions[ServerExtension].title

    # Switch profile to None (idle)
    app._state = TrayState(
        status=TrayStatus.RUNNING,
        profile_id=None,
        extension_key=ParrotExtension,
        server_url="http://127.0.0.1:8181",
    )
    app._sync_ui(None)

    assert app.title == f"{TryIcon.PARROT} Helomi"
    assert app._menu_profiles["default"].state == 0
    assert app._menu_extensions[ServerExtension].state == 0
    assert app._menu_extensions[ParrotExtension].state == 1


def test_tray_app_sync_ui_quiting(mock_runtime):
    """Verify _sync_ui sets EXIT icon and clears callbacks on quiting."""
    app = TrayApp(runtime=mock_runtime)
    app._last_state = TrayState(status=TrayStatus.RUNNING)
    app._state = TrayState(status=TrayStatus.QUITING)

    app._sync_ui(None)

    assert app.title == f"{TryIcon.EXIT} Helomi"


def test_tray_app_handle_toggle_profile(mock_runtime):
    """Verify clicking profile menu items activates or deactivates profiles."""
    app = TrayApp(runtime=mock_runtime)
    app._pipeline_execute_command = MagicMock()

    # If item is currently active (state == 1), clicking deactivates
    item = app._menu_profiles["default"]
    item.state = 1
    app._handle_toggle_profile(item)
    app._pipeline_execute_command.assert_called_once()
    assert isinstance(app._pipeline_execute_command.call_args[0][0], DeactivateProfile)

    # If item is inactive (state == 0), clicking activates
    item.state = 0
    app._pipeline_execute_command.reset_mock()
    app._handle_toggle_profile(item)
    app._pipeline_execute_command.assert_called_once()
    cmd = app._pipeline_execute_command.call_args[0][0]
    assert isinstance(cmd, ActivateProfile)
    assert cmd.profile_id == "default"


def test_tray_app_handle_toggle_extension(mock_runtime):
    """Verify clicking extension menu item dispatches extension selection."""
    app = TrayApp(runtime=mock_runtime)
    app._loop = MagicMock()
    app._pipeline_set_activate_extension = MagicMock()

    parrot_item = app._menu_extensions[ParrotExtension]
    app._handle_toggle_extension(parrot_item)

    app._pipeline_set_activate_extension.assert_called_once_with(ParrotExtension)
    assert app._state.extension_key is ParrotExtension

    # Without loop, does nothing
    app._loop = None
    app._pipeline_set_activate_extension.reset_mock()
    app._handle_toggle_extension(parrot_item)
    app._pipeline_set_activate_extension.assert_not_called()


def test_tray_app_pipeline_set_activate_extension(mock_runtime):
    """Verify _pipeline_set_activate_extension runs on event loop."""
    app = TrayApp(runtime=mock_runtime)
    app._pipeline = MagicMock()
    mock_loop = MagicMock()
    app._loop = mock_loop

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        app._pipeline_set_activate_extension(ParrotExtension)
        mock_run_coro.assert_called_once()

    # Without pipeline or loop, does nothing
    app._pipeline = None
    app._pipeline_set_activate_extension(ParrotExtension)


def test_tray_app_pipeline_execute_command(mock_runtime):
    """Verify _pipeline_execute_command runs pipeline command on event loop."""
    app = TrayApp(runtime=mock_runtime)
    app._pipeline = MagicMock()
    mock_loop = MagicMock()
    app._loop = mock_loop

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        cmd = DeactivateProfile()
        app._pipeline_execute_command(cmd)
        mock_run_coro.assert_called_once()

    # Without pipeline or loop, does nothing
    app._pipeline = None
    app._pipeline_execute_command(cmd)


def test_tray_app_handle_quit_and_exit(mock_runtime):
    """Verify quit flow signals shutdown and exits cleanly."""
    app = TrayApp(runtime=mock_runtime)
    mock_timer_item = MagicMock()

    with patch("rumps.Timer") as mock_timer_cls:
        app._handle_quit(mock_timer_item)
        assert app._state.status == TrayStatus.QUITING
        assert mock_timer_cls.called

    # Test _handle_exit
    timer = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    app._loop = mock_loop
    app._shutdown_signal = MagicMock()
    app._thread = MagicMock()
    app._thread.is_alive.return_value = True

    with (
        patch("joblib.externals.loky.get_reusable_executor") as mock_executor,
        patch("atexit._run_exitfuncs") as mock_exitfuncs,
        patch("rumps.quit_application") as mock_quit_app,
    ):
        app._handle_exit(timer)
        timer.stop.assert_called_once()
        mock_loop.call_soon_threadsafe.assert_called_once_with(app._shutdown_signal.set)
        app._thread.join.assert_called_once_with(timeout=5.0)
        mock_executor.return_value.shutdown.assert_called_once()
        mock_exitfuncs.assert_called_once()
        mock_quit_app.assert_called_once()


@pytest.mark.asyncio
async def test_tray_app_pipeline_loop(mock_runtime):
    """Verify _pipeline_loop listens to pipeline events and updates state."""
    app = TrayApp(runtime=mock_runtime)

    mock_pipeline = MagicMock()

    async def mock_subscribe():
        yield ProfileActivated(profile_id="gizmo")
        yield ProfileDeactivated(profile_id="gizmo")

    mock_pipeline.subscribe_event = mock_subscribe
    app._pipeline = mock_pipeline

    await app._pipeline_loop()

    assert app._state.profile_id is None


@pytest.mark.asyncio
async def test_tray_app_runtime_loop(mock_runtime):
    """Verify _runtime_loop initializes components and awaits shutdown."""
    app = TrayApp(runtime=mock_runtime)

    mock_pipeline = MagicMock()
    mock_pipeline.active_profile = None

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
    assert app._state.status == TrayStatus.RUNNING
    assert app._state.server_url == "http://localhost:8181"

    app._shutdown_signal.set()
    await loop_task


def test_tray_app_thread_worker(mock_runtime):
    """Verify _thread_worker initializes event loop and executes runtime loop."""
    app = TrayApp(runtime=mock_runtime)
    with patch.object(app, "_runtime_loop", new_callable=AsyncMock) as mock_r_loop:
        app._thread_worker()
        assert app._loop is not None
        mock_r_loop.assert_called_once()


def test_tray_app_run(mock_runtime):
    """Verify run starts worker thread and calls rumps.App.run."""
    app = TrayApp(runtime=mock_runtime)
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
        patch("asyncio.run") as mock_asyncio_run,
        patch("helomi_tray.main.configure_logger") as mock_conf,
        patch.object(sys, "argv", ["helomi-tray"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        main()
        mock_conf.assert_called_once()
        mock_asyncio_run.assert_called_once()


@pytest.mark.asyncio
async def test_tray_run_function():
    """Verify _run instantiates Runtime and TrayApp."""
    with (
        patch("helomi_tray.main.Runtime") as mock_runtime_cls,
        patch("helomi_tray.main.TrayApp") as mock_tray_cls,
    ):
        mock_app = mock_tray_cls.return_value
        args = MagicMock()
        args.debug = False
        await run(args)
        mock_runtime_cls.assert_called_once()
        mock_tray_cls.assert_called_once_with(runtime=mock_runtime_cls.return_value)
        mock_app.run.assert_called_once()


def test_tray_package_main_execution():
    """Verify running helomi_tray __main__."""
    with (
        patch("asyncio.run") as mock_asyncio_run,
        patch.object(sys, "argv", ["helomi-tray"]),
    ):
        mock_asyncio_run.side_effect = lambda coro: coro.close()
        runpy.run_module("helomi_tray", run_name="__main__")
