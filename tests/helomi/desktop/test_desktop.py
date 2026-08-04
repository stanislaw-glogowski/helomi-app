import importlib
import runpy
import sys
from types import SimpleNamespace

import pytest

import helomi.desktop.runtime as runtime_module
from helomi.app import ProgressSnapshot
from helomi.desktop.runtime import DesktopRuntime
from helomi.desktop.state import DesktopMode, DesktopSnapshot


def test_desktop_imports_are_lazy() -> None:
    sys.modules.pop("rumps", None)
    import helomi.desktop
    import helomi.desktop.main

    importlib.reload(helomi.desktop)
    importlib.reload(helomi.desktop.main)
    assert "rumps" not in sys.modules


def test_desktop_parser_accepts_runtime_locale_and_profile_overrides() -> None:
    import helomi.desktop.main as main_module

    parsed = main_module.build_parser().parse_args(
        ["--language", "pl-PL", "--profile=henry"]
    )
    assert parsed.language == "pl-PL"
    assert parsed.profile == "henry"


def test_desktop_entrypoints_call_the_lazy_menu_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import helomi.desktop.main as main_module

    calls: list[bool] = []

    class App:
        def __init__(self, **_kwargs) -> None:
            pass

        def run(self) -> None:
            calls.append(True)

    import helomi.desktop.menu as menu_module

    monkeypatch.setattr(menu_module, "MenuBarApp", App)
    main_module.main([])
    assert calls == [True]

    monkeypatch.setattr(main_module, "main", lambda: calls.append(True))
    runpy.run_module("helomi.desktop.__main__", run_name="__main__")
    assert calls == [True, True]


def test_snapshot_projects_tray_titles_and_safe_actions() -> None:
    starting = DesktopSnapshot(DesktopMode.STARTING, "Agent")
    failed = DesktopSnapshot(DesktopMode.FAILED, "Agent", "agent")
    running = DesktopSnapshot(DesktopMode.RUNNING, "Agent", "agent")
    assert starting.tray_title == "⏳ Agent"
    assert failed.tray_title == "❌ Agent"
    assert failed.retry_enabled
    assert running.tray_title == "Agent"
    assert not running.retry_enabled


def test_runtime_coalesces_updates_and_waits_for_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(id="agent", name="Agent")

    class Progress:
        def subscribe(self, listener):
            self.listener = listener
            return lambda: None

    class FakeRuntime:
        def __init__(self, **_kwargs) -> None:
            import asyncio

            self.startup_profile = profile
            self.progress = Progress()
            self.stopped = asyncio.Event()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            pass

        async def start(self, profile_id: str) -> None:
            if profile_id == "broken":
                raise RuntimeError("startup failed")

        async def wait(self) -> None:
            await self.stopped.wait()

        async def shutdown(self) -> None:
            self.stopped.set()

    monkeypatch.setattr(runtime_module, "ApplicationRuntime", FakeRuntime)
    desktop = DesktopRuntime()
    desktop.start()
    first = desktop._updates.get(timeout=1)
    assert first.mode in {DesktopMode.STARTING, DesktopMode.RUNNING}
    running = desktop.drain() or first
    assert running.mode in {DesktopMode.STARTING, DesktopMode.RUNNING}
    snapshot = desktop.drain() or running
    assert snapshot.selected_profile_id == "agent"

    for index in range(3):
        desktop._publish(DesktopSnapshot(DesktopMode.READY, detail=str(index)))
    assert desktop.drain().detail == "2"

    shutdown = desktop.shutdown()
    assert shutdown is not None
    shutdown.result(timeout=1)
    desktop.join()
    assert desktop.terminated


def test_runtime_reports_startup_failure_and_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Progress:
        def subscribe(self, _listener):
            return lambda: None

    class Runtime:
        def __init__(self, **_kwargs) -> None:
            self.startup_profile = SimpleNamespace(id="agent", name="Agent")
            self.progress = Progress()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            pass

        async def start(self, _profile_id: str) -> None:
            raise RuntimeError("models failed")

        async def wait(self) -> None:
            return

        async def shutdown(self) -> None:
            pass

    monkeypatch.setattr(runtime_module, "ApplicationRuntime", Runtime)
    desktop = DesktopRuntime()
    desktop.start()
    assert desktop._updates.get(timeout=1).mode is DesktopMode.FAILED
    shutdown = desktop.shutdown()
    assert shutdown is not None
    shutdown.result(timeout=1)
    desktop.join()

    class BrokenRuntime:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            raise RuntimeError("settings missing")

        async def __aexit__(self, *_args) -> None:
            pass

    monkeypatch.setattr(runtime_module, "ApplicationRuntime", BrokenRuntime)
    broken = DesktopRuntime()
    broken.start()
    assert broken._updates.get(timeout=1).detail == "settings missing"
    shutdown = broken.shutdown()
    assert shutdown is not None
    shutdown.result(timeout=1)
    broken.join()


def test_runtime_guard_paths_and_internal_failure_projection() -> None:
    async def scenario() -> None:
        class FailingRuntime:
            async def wait(self) -> None:
                raise RuntimeError("worker failed")

            async def shutdown(self) -> None:
                pass

        desktop = DesktopRuntime()
        assert not desktop.terminated
        assert desktop.retry() is None
        assert desktop.shutdown() is None
        desktop._command_active = True
        desktop._loop = asyncio.get_running_loop()
        assert desktop.retry() is None
        desktop._command_active = False
        desktop._runtime = FailingRuntime()
        await desktop._watch_runtime("agent")
        assert desktop.drain().detail == "worker failed"

        class StoppedRuntime:
            async def wait(self) -> None:
                pass

        desktop._runtime = StoppedRuntime()
        desktop._shutdown_signal = asyncio.Event()
        await desktop._watch_runtime("agent")
        assert desktop._shutdown_signal.is_set()

        desktop._runtime = None
        await desktop._start_profile("agent")
        assert not desktop._command_active

        desktop._selected_profile_id = "agent"
        assert desktop._progress_mode() is DesktopMode.RUNNING
        desktop._command_active = True
        assert desktop._progress_mode() is DesktopMode.STARTING
        desktop._shutting_down = True
        assert desktop._progress_mode() is DesktopMode.SHUTTING_DOWN

        desktop._shutting_down = False
        desktop._loop = SimpleNamespace(
            call_soon_threadsafe=lambda callback, value: callback(value)
        )
        desktop._progress_changed(ProgressSnapshot())
        assert desktop.drain().mode is DesktopMode.STARTING
        desktop._loop = None
        desktop._progress_changed(ProgressSnapshot())

    import asyncio

    asyncio.run(scenario())


def test_menu_renders_status_retry_and_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Menu:
        def __init__(self) -> None:
            self.items = []

        def clear(self) -> None:
            self.items.clear()

        def update(self, items) -> None:
            self.items.extend(items)

    class MenuItem:
        def __init__(self, title, callback=None) -> None:
            self.title = title
            self.callback = callback
            self.state = False
            self.items = []

        def set_callback(self, callback) -> None:
            self.callback = callback

        def add(self, item) -> None:
            self.items.append(item)

    class App:
        def __init__(self, *_args, **_kwargs) -> None:
            self.menu = Menu()
            self.title = ""

        def run(self) -> None:
            pass

    class Timer:
        def __init__(self, *_args) -> None:
            pass

        def start(self) -> None:
            pass

    fake_rumps = SimpleNamespace(
        App=App,
        MenuItem=MenuItem,
        Timer=Timer,
        quit_application=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "rumps", fake_rumps)
    import helomi.desktop.menu as menu_module

    class Bridge:
        def __init__(self, **_kwargs) -> None:
            self.shutdowns = 0

        def retry(self) -> None:
            pass

        def shutdown(self) -> None:
            self.shutdowns += 1

    monkeypatch.setattr(menu_module, "DesktopRuntime", Bridge)
    app = menu_module.MenuBarApp()
    app._snapshot = DesktopSnapshot(
        DesktopMode.FAILED,
        profile_name="Agent",
        selected_profile_id="agent",
        detail="startup failed",
        progress=ProgressSnapshot(),
    )
    app._render()
    items = app._app.menu.items
    assert app._app.title == "❌ Agent"
    assert not any(getattr(item, "title", None) == "Profiles" for item in items)
    assert any(getattr(item, "title", None) == "Retry" for item in items)
    assert [getattr(item, "title", None) for item in items[-3:]] == [
        "Status: Failed",
        None,
        "Quit Helomi",
    ]
    app._quit(None)
    app._quit(None)
    assert app._runtime.shutdowns == 1

    app._snapshot = DesktopSnapshot(DesktopMode.READY)
    app._render()
    assert not any(
        getattr(item, "title", None) == "Retry" for item in app._app.menu.items
    )


def test_menu_run_drains_updates_and_quits_after_runtime_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Menu:
        def clear(self) -> None:
            pass

        def update(self, _items) -> None:
            pass

    class App:
        def __init__(self, *_args, **_kwargs) -> None:
            self.menu = Menu()

        def run(self) -> None:
            calls.append("app")

    class Timer:
        def __init__(self, *_args) -> None:
            pass

        def start(self) -> None:
            calls.append("timer")

    fake_rumps = SimpleNamespace(
        App=App,
        MenuItem=lambda *_args, **_kwargs: SimpleNamespace(
            set_callback=lambda _: None, add=lambda _: None
        ),
        Timer=Timer,
        quit_application=lambda: calls.append("quit"),
    )
    monkeypatch.setitem(sys.modules, "rumps", fake_rumps)
    import helomi.desktop.menu as menu_module

    class Bridge:
        terminated = True

        def __init__(self, **_kwargs) -> None:
            self.started = False
            self.joined = False

        def start(self) -> None:
            self.started = True

        def drain(self):
            return DesktopSnapshot(DesktopMode.RUNNING)

        def join(self) -> None:
            self.joined = True

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr(menu_module, "DesktopRuntime", Bridge)
    app = menu_module.MenuBarApp()
    monkeypatch.setattr(app, "_render", lambda: calls.append("render"))
    app.run()
    assert app._runtime.started
    assert calls == ["timer", "render", "app"]
    app._drain_updates(None)
    assert app._runtime.joined
    assert calls[-2:] == ["render", "quit"]

    monkeypatch.setattr(menu_module.threading, "current_thread", lambda: object())
    monkeypatch.setattr(menu_module.threading, "main_thread", lambda: object())
    with pytest.raises(RuntimeError, match="main thread"):
        app.run()
