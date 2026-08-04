import asyncio
import importlib
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import helomi.desktop.runtime as runtime_module
from helomi.app import ProgressItem, ProgressSnapshot, ProgressStatus
from helomi.conversation.events import (
    CancelReply,
    ReplyDraftUpdated,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyPhrase,
)
from helomi.desktop.runtime import DesktopRuntime
from helomi.desktop.state import (
    AgentActivity,
    DesktopMode,
    DesktopSnapshot,
)
from helomi.desktop.windows import DesktopWindows, _WindowContent
from helomi.speech.events import (
    InteractionTimingObserved,
    ReplyPhraseDelivered,
    ReplyPhrasePlaybackStarted,
    UserTurnCommitted,
    VADObserved,
    VoiceSessionMode,
    VoiceSessionModeChanged,
    WakeWordObserved,
)


class BlockingSubscription:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()

    def task_done(self) -> None:
        pass


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
    assert running.tray_title == "⚪ Agent"
    assert not running.retry_enabled
    assert not running.data_folder_enabled


def test_desktop_presentation_states_have_stable_emoji_and_labels() -> None:
    assert DesktopMode.READY.presentation == "🟡 Ready"
    assert DesktopMode.STARTING.presentation == "⏳ Starting"
    assert DesktopMode.RETRYING.presentation == "🔄 Retrying"
    assert DesktopMode.RUNNING.presentation == "🟢 Running"
    assert DesktopMode.FAILED.presentation == "❌ Failed"
    assert DesktopMode.SHUTTING_DOWN.presentation == "👋 Shutting down"
    assert AgentActivity.WAITING.presentation == "👂 Waiting for wake word"
    assert AgentActivity.LISTENING.presentation == "🎙️ Listening"
    assert AgentActivity.THINKING.presentation == "🤔 Thinking"
    assert AgentActivity.SPEAKING.presentation == "🔊 Speaking"
    assert AgentActivity.COMPLETED.presentation == "✅ Response complete"
    assert AgentActivity.INTERRUPTED.presentation == "🛑 Response interrupted"


def test_snapshot_enables_only_existing_data_folders(tmp_path: Path) -> None:
    snapshot = DesktopSnapshot(DesktopMode.RUNNING, data_path=tmp_path / "data")
    assert not snapshot.data_folder_enabled
    snapshot.data_path.mkdir()
    assert snapshot.data_folder_enabled


def test_runtime_reduces_live_history_and_system_events() -> None:
    desktop = DesktopRuntime()
    desktop._reduce_event(UserTurnCommitted(1, "Hello"))
    desktop._reduce_event(ReplyGenerationStarted(2))
    desktop._reduce_event(ReplyDraftUpdated(2, "Thinking"))
    desktop._reduce_event(ReplyPhrase(2, 3, "Done."))
    desktop._reduce_event(ReplyPhrasePlaybackStarted(2, 3))
    desktop._reduce_event(ReplyPhraseDelivered(2, 3))
    desktop._reduce_event(ReplyGenerationCompleted(2))
    desktop._reduce_event(VADObserved(0.8, True))
    desktop._reduce_event(WakeWordObserved(0.7, True))
    desktop._reduce_event(InteractionTimingObserved("reply_started", 120.0))
    desktop._reduce_event(VoiceSessionModeChanged(VoiceSessionMode.ACTIVE))

    snapshot = desktop.drain()
    assert snapshot is not None
    assert snapshot.conversation.messages[0].text == "Hello"
    reply = snapshot.conversation.messages[1]
    assert reply.phrases[0].state.name == "DELIVERED"
    assert snapshot.system_info.vad_detected
    assert snapshot.system_info.wakeword_detected
    assert snapshot.system_info.timings == (("reply_started", 120.0),)
    assert not snapshot.waiting_for_wakeword
    transcript = DesktopWindows._conversation_text_value(snapshot)
    system_info = DesktopWindows._system_text_value(snapshot)
    assert "✅ Delivered · Done." in transcript
    assert "Reply Started: 120 ms" in system_info
    assert snapshot.agent_activity is AgentActivity.LISTENING

    desktop._reduce_event(CancelReply(reply_id=2))
    interrupted = desktop.drain()
    assert interrupted.conversation.messages[1].interrupted
    assert "🛑 Reply interrupted" in DesktopWindows._conversation_text_value(
        interrupted
    )
    assert interrupted.agent_activity is AgentActivity.INTERRUPTED


def test_runtime_bounds_conversation_history() -> None:
    desktop = DesktopRuntime()
    for turn_id in range(201):
        desktop._reduce_event(UserTurnCommitted(turn_id, str(turn_id)))
    snapshot = desktop.drain()
    assert snapshot is not None
    assert len(snapshot.conversation.messages) == 200
    assert snapshot.conversation.messages[0].turn_id == 1


def test_native_window_text_projects_live_snapshot() -> None:
    snapshot = DesktopSnapshot(DesktopMode.RUNNING)
    assert "Waiting for" in DesktopWindows._conversation_text_value(snapshot)
    assert "Signals" in DesktopWindows._system_text_value(snapshot)


def test_windows_are_lazy_center_once_and_project_active_progress() -> None:
    class Window:
        def __init__(self) -> None:
            self.centered = 0
            self.opened = 0

        def center(self) -> None:
            self.centered += 1

        def makeKeyAndOrderFront_(self, _sender) -> None:
            self.opened += 1

    activated: list[bool] = []
    windows = DesktopWindows()
    snapshot = DesktopSnapshot(
        DesktopMode.STARTING,
        progress=ProgressSnapshot(
            (
                ProgressItem(
                    1, "Downloading model", 50, 100, "MB", ProgressStatus.ACTIVE
                ),
            )
        ),
    )
    windows.update(snapshot)
    assert windows._appkit is None
    assert "Downloading model · 50 MB · 50%" in windows._system_text_value(snapshot)

    window = Window()
    windows._appkit = SimpleNamespace(
        NSApp=SimpleNamespace(
            activateIgnoringOtherApps_=lambda _value: activated.append(True)
        )
    )
    content = _WindowContent(window, None, None, None)
    windows._show(content)
    windows._show(content)
    assert window.centered == 1
    assert window.opened == 2
    assert activated == [True, True]


def test_runtime_coalesces_updates_and_waits_for_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(id="agent", name="Agent", data_path=Path("/missing"))

    class Progress:
        def subscribe(self, listener):
            self.listener = listener
            return lambda: None

    class FakeRuntime:
        def __init__(self, **_kwargs) -> None:
            import asyncio

            self.startup_profile = profile
            self.settings = object()
            self.progress = Progress()
            self.stopped = asyncio.Event()
            self.subscribed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            pass

        async def start(self, profile_id: str) -> None:
            assert self.subscribed
            if profile_id == "broken":
                raise RuntimeError("startup failed")

        async def wait(self) -> None:
            await self.stopped.wait()

        async def shutdown(self) -> None:
            self.stopped.set()

        def subscribe(self, *_types):
            self.subscribed = True
            return BlockingSubscription()

    monkeypatch.setattr(runtime_module, "ApplicationRuntime", FakeRuntime)
    monkeypatch.setattr(
        runtime_module.SystemInfo,
        "from_runtime",
        classmethod(lambda cls, profile, _settings: cls(profile_name=profile.name)),
    )
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
            self.startup_profile = SimpleNamespace(
                id="agent", name="Agent", data_path=Path("/missing")
            )
            self.progress = Progress()
            self.settings = object()

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

        def subscribe(self, *_types):
            return BlockingSubscription()

    monkeypatch.setattr(runtime_module, "ApplicationRuntime", Runtime)
    monkeypatch.setattr(
        runtime_module.SystemInfo,
        "from_runtime",
        classmethod(lambda cls, profile, _settings: cls(profile_name=profile.name)),
    )
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
    tmp_path: Path,
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

    class Windows:
        def __init__(self) -> None:
            self.snapshots = []

        def update(self, snapshot) -> None:
            self.snapshots.append(snapshot)

        def show_conversation(self) -> None:
            pass

        def show_system_info(self) -> None:
            pass

    class Bridge:
        def __init__(self, **_kwargs) -> None:
            self.shutdowns = 0

        def retry(self) -> None:
            pass

        def shutdown(self) -> None:
            self.shutdowns += 1

    monkeypatch.setattr(menu_module, "DesktopRuntime", Bridge)
    monkeypatch.setattr(menu_module, "DesktopWindows", Windows)
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
    assert [getattr(item, "title", None) for item in items[-4:]] == [
        "App: ❌ Failed",
        "Agent: ⚪ Offline",
        None,
        "Quit Helomi",
    ]
    assert [getattr(item, "title", None) for item in items[:4]] == [
        "Open Profile Data Folder",
        "Conversation History…",
        "System Info…",
        None,
    ]
    assert items[0].callback is None
    app._quit(None)
    app._quit(None)
    assert app._runtime.shutdowns == 1

    app._snapshot = DesktopSnapshot(DesktopMode.READY)
    app._render()
    assert not any(
        getattr(item, "title", None) == "Retry" for item in app._app.menu.items
    )

    data_path = tmp_path / "data"
    data_path.mkdir()
    opened: list[str] = []
    app._snapshot = DesktopSnapshot(DesktopMode.RUNNING, data_path=data_path)
    app._render()
    assert app._app.menu.items[0].callback is not None
    monkeypatch.setattr(
        menu_module,
        "import_module",
        lambda name: (
            SimpleNamespace(
                NSWorkspace=SimpleNamespace(
                    sharedWorkspace=lambda: SimpleNamespace(
                        openURL_=lambda url: opened.append(url)
                    )
                )
            )
            if name == "AppKit"
            else SimpleNamespace(
                NSURL=SimpleNamespace(fileURLWithPath_=lambda path: path)
            )
        ),
    )
    app._open_data_folder(None)
    assert opened == [str(data_path)]
    data_path.rmdir()
    app._open_data_folder(None)
    assert opened == [str(data_path)]
    assert app._app.menu.items[0].callback is None


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

    monkeypatch.setattr(
        menu_module,
        "DesktopWindows",
        lambda: SimpleNamespace(
            update=lambda _snapshot: None,
            show_conversation=lambda: None,
            show_system_info=lambda: None,
        ),
    )

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
