import asyncio
import importlib
import os
import runpy
import signal
from types import SimpleNamespace

import pytest
from loguru import logger

import helomi.cli.main as main_module
from helomi.common.events import EventBus, ShutdownEvent
from helomi.conversation.events import (
    ConversationActivated,
    GenerateReply,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyPhrase,
    UserTurn,
)
from helomi.resources import ProfileEntry, Settings
from helomi.speech.events import WakeWordObserved


def test_cli_suppresses_unused_pytorch_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRANSFORMERS_NO_ADVISORY_WARNINGS", raising=False)
    importlib.reload(main_module)
    assert os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] == "1"


def test_configure_shutdown_registers_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    loop = SimpleNamespace(add_signal_handler=lambda *args: calls.append(args))
    monkeypatch.setattr(main_module.asyncio, "get_running_loop", lambda: loop)
    bus = EventBus()
    main_module.configure_shutdown(bus)
    assert [item[0] for item in calls] == [signal.SIGINT, signal.SIGTERM]
    assert all(item[1] == bus.publish for item in calls)
    assert all(isinstance(item[2], ShutdownEvent) for item in calls)


def test_event_logger_reports_conversation_events() -> None:
    from helomi.cli.events import run_event_logger

    async def scenario() -> None:
        bus = EventBus()
        messages: list[str] = []
        handler = logger.add(messages.append, format="{message}")
        try:
            task = asyncio.create_task(run_event_logger(bus))
            await asyncio.sleep(0)
            bus.publish(
                WakeWordObserved(score=0.9, detected=True),
                GenerateReply(ConversationActivated()),
                GenerateReply(UserTurn("Question")),
                ReplyGenerationStarted(1),
                ReplyPhrase(1, 1, "Answer"),
                ReplyGenerationCompleted(1),
                ShutdownEvent(),
            )
            await asyncio.wait_for(task, 1)
        finally:
            logger.remove(handler)
        output = "\n".join(messages)
        assert "Wake word detected" in output
        assert "Wake word activated" in output
        assert "Helomi: Answer" in output

    asyncio.run(scenario())


def test_run_uses_the_application_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        calls: list[str] = []
        event_bus = EventBus()
        profile = SimpleNamespace(id="agent", name="Agent")

        class Runtime:
            profiles = (ProfileEntry("agent", "Agent", profile),)
            settings = Settings()
            progress = object()
            default_profile_id = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args) -> None:
                pass

            async def start(self, profile_id: str) -> None:
                calls.append(f"start:{profile_id}")

            async def wait(self) -> None:
                return

            async def shutdown(self) -> None:
                calls.append("shutdown")
                event_bus.publish(ShutdownEvent())

        Runtime.event_bus = event_bus

        class App:
            def __init__(self, *_args) -> None:
                self.exited = asyncio.Event()

            async def run_async(self) -> None:
                await self.exited.wait()

            async def wait_mounted(self) -> None:
                pass

            async def select_profile(self):
                return profile

            def configure_runtime(self, *_args) -> None:
                calls.append("configure")

            async def show_startup(self) -> None:
                calls.append("show")

            async def finish_startup(self) -> None:
                calls.append("finish")

            async def wait_quit_requested(self) -> None:
                return

            def exit(self) -> None:
                self.exited.set()

        class Bridge:
            async def wait_ready(self) -> None:
                pass

            async def run(self, bus: EventBus) -> None:
                with bus.subscribe(ShutdownEvent) as events:
                    event = await events.__anext__()
                    events.task_done()
                    assert isinstance(event, ShutdownEvent)

        async def logger_task(_bus: EventBus) -> None:
            return

        monkeypatch.setattr(main_module, "ApplicationRuntime", Runtime)
        monkeypatch.setattr(main_module, "TerminalApp", App)
        monkeypatch.setattr(main_module, "UiEventBridge", Bridge)
        monkeypatch.setattr(main_module, "run_event_logger", logger_task)
        monkeypatch.setattr(main_module, "configure_ui_logger", lambda _: None)
        monkeypatch.setattr(main_module, "configure_shutdown", lambda _: None)
        await main_module.run()
        assert calls[:4] == ["configure", "show", "start:agent", "finish"]
        assert "shutdown" in calls

    asyncio.run(scenario())


def test_run_uses_selected_profile_without_opening_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        calls: list[str] = []
        event_bus = EventBus()
        profile = SimpleNamespace(id="agent", name="Agent")

        class Runtime:
            profiles = (ProfileEntry("agent", "Agent", profile),)
            settings = Settings.model_validate({"selected_profile": "agent"})
            progress = object()
            default_profile_id = None
            selected_profile = profile

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args) -> None:
                pass

            async def start(self, profile_id: str) -> None:
                calls.append(f"start:{profile_id}")

            async def wait(self) -> None:
                return

            async def shutdown(self) -> None:
                calls.append("shutdown")
                event_bus.publish(ShutdownEvent())

        Runtime.event_bus = event_bus

        class App:
            def __init__(self, *_args) -> None:
                self.exited = asyncio.Event()

            async def run_async(self) -> None:
                await self.exited.wait()

            async def wait_mounted(self) -> None:
                pass

            async def select_profile(self):
                raise AssertionError("selected profile must bypass the picker")

            def configure_runtime(self, selected, _settings) -> None:
                assert selected is profile
                calls.append("configure")

            async def show_startup(self) -> None:
                calls.append("show")

            async def finish_startup(self) -> None:
                calls.append("finish")

            async def wait_quit_requested(self) -> None:
                return

            def exit(self) -> None:
                self.exited.set()

        class Bridge:
            async def wait_ready(self) -> None:
                pass

            async def run(self, bus: EventBus) -> None:
                with bus.subscribe(ShutdownEvent) as events:
                    await events.__anext__()
                    events.task_done()

        monkeypatch.setattr(main_module, "ApplicationRuntime", Runtime)
        monkeypatch.setattr(main_module, "TerminalApp", App)
        monkeypatch.setattr(main_module, "UiEventBridge", Bridge)
        monkeypatch.setattr(
            main_module, "run_event_logger", lambda _bus: asyncio.sleep(0)
        )
        monkeypatch.setattr(main_module, "configure_ui_logger", lambda _: None)
        monkeypatch.setattr(main_module, "configure_shutdown", lambda _: None)
        await main_module.run()
        assert calls[:4] == ["configure", "show", "start:agent", "finish"]

    asyncio.run(scenario())


def test_main_runs_async_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    def fake_run(coroutine) -> None:
        captured.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(main_module.asyncio, "run", fake_run)
    main_module.main()
    assert len(captured) == 1


def test_module_entrypoint_calls_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(main_module, "main", lambda: calls.append(True))
    runpy.run_module("helomi.cli.__main__", run_name="__main__")
    assert calls == [True]
