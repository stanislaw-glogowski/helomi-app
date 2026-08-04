import asyncio
from types import SimpleNamespace

import pytest

import helomi.app.runtime as runtime_module
from helomi.app import ApplicationRuntime, ProgressStore
from helomi.common.events import ShutdownEvent
from helomi.conversation import (
    ConversationActivated,
    ConversationReady,
    GenerateReply,
    QuitRequested,
)
from helomi.resources import ProfileEntry, Settings
from helomi.speech.events import ReplyPhraseDelivered, SpeechReady
from tests.helomi.cli.test_state import profile as make_profile


def test_runtime_validates_profiles_and_retries_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        profile = make_profile()
        store = SimpleNamespace(
            load_settings=lambda: Settings(),
            inspect_profiles=lambda: [
                ProfileEntry("agent", "Agent", profile),
                ProfileEntry("broken", "Broken", error="bad profile"),
            ],
        )
        attempts = 0

        async def workers(bus, *_args) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("models failed")
            with bus.subscribe(runtime_module.ShutdownEvent) as events:
                bus.publish(ConversationReady(), SpeechReady())
                await _args[-1].wait()
                await events.__anext__()
                events.task_done()

        monkeypatch.setattr(runtime_module, "_run_workers", workers)
        async with ApplicationRuntime(store) as runtime:
            assert runtime.profiles[0].profile is profile
            assert runtime.profiles[1].profile is None
            with pytest.raises(RuntimeError, match="models failed"):
                await runtime.start("agent")
            await runtime.start("agent")
            with pytest.raises(RuntimeError, match="already running"):
                await runtime.start("agent")
            await runtime.shutdown()
            with pytest.raises(ValueError, match="bad profile"):
                await runtime.start("broken")
            with pytest.raises(ValueError, match="does not exist"):
                await runtime.start("missing")
        assert attempts == 2

    asyncio.run(scenario())


def test_runtime_wait_propagates_backend_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        store = SimpleNamespace(
            load_settings=lambda: Settings(),
            inspect_profiles=lambda: [ProfileEntry("agent", "Agent", make_profile())],
        )

        async def workers(bus, *_args) -> None:
            with bus.subscribe(runtime_module.ShutdownEvent):
                bus.publish(ConversationReady(), SpeechReady())
                await _args[-1].wait()
            raise RuntimeError("worker stopped")

        monkeypatch.setattr(runtime_module, "_run_workers", workers)
        async with ApplicationRuntime(store) as runtime:
            await runtime.start("agent")
            with pytest.raises(RuntimeError, match="worker stopped"):
                await runtime.wait()
            await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_exposes_only_open_lifecycle_contracts() -> None:
    async def scenario() -> None:
        store = SimpleNamespace(
            load_settings=lambda: Settings(), inspect_profiles=lambda: []
        )
        runtime = ApplicationRuntime(store)
        with pytest.raises(RuntimeError, match="not open"):
            _ = runtime.profiles
        await runtime.__aenter__()
        with pytest.raises(RuntimeError, match="already open"):
            await runtime.__aenter__()
        with pytest.raises(FileNotFoundError, match="No valid profiles"):
            _ = runtime.startup_profile
        with runtime.subscribe(ShutdownEvent) as events:
            runtime.event_bus.publish(ShutdownEvent())
            event = await events.__anext__()
            events.task_done()
            assert isinstance(event, ShutdownEvent)
        await runtime.shutdown()
        await runtime.__aexit__(None, None, None)
        with pytest.raises(RuntimeError, match="not open"):
            await runtime.wait()

    asyncio.run(scenario())


def test_worker_composition_and_shutdown_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        calls: list[str] = []
        bus = runtime_module.EventBus()
        start = asyncio.Event()
        start.set()

        async def conversation(*_args) -> None:
            calls.append("conversation")

        async def speech(*_args) -> None:
            calls.append("speech")

        monkeypatch.setattr(runtime_module, "run_conversation_worker", conversation)
        monkeypatch.setattr(runtime_module, "run_speech_worker", speech)
        await runtime_module._run_workers(
            bus, make_profile(), Settings(), object(), start
        )
        assert calls == ["conversation", "speech"]

        with bus.subscribe(ShutdownEvent) as events:
            waiting = asyncio.create_task(runtime_module._wait_until_ready(events))
            bus.publish(ShutdownEvent())
            with pytest.raises(asyncio.CancelledError):
                await waiting

    asyncio.run(scenario())


def test_always_listening_profile_starts_with_welcome_reaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        bus = runtime_module.EventBus()
        profile = make_profile(wakeword=None)

        async def workers(*_args) -> None:
            event_bus, _profile, _settings, _store, start_event = _args
            with event_bus.subscribe(GenerateReply, ShutdownEvent) as events:
                event_bus.publish(ConversationReady(), SpeechReady())
                await start_event.wait()
                event = await events.__anext__()
                events.task_done()
                assert event == GenerateReply(ConversationActivated())

        monkeypatch.setattr(runtime_module, "_run_workers", workers)
        backend = await runtime_module._start_runtime(
            bus, profile, Settings(), object()
        )
        await asyncio.wait_for(backend, 1)

    asyncio.run(scenario())


def test_quit_coordinator_accepts_goodbye_delivered_before_quit_request() -> None:
    async def scenario() -> None:
        bus = runtime_module.EventBus()
        ready = asyncio.Event()
        with bus.subscribe(ShutdownEvent) as shutdowns:
            coordinator = asyncio.create_task(
                runtime_module._shutdown_after_quit(bus, ready)
            )
            await ready.wait()
            bus.publish(ReplyPhraseDelivered(reply_id=3, phrase_id=2))
            bus.publish(QuitRequested(reply_id=3, final_phrase_id=2))
            event = await asyncio.wait_for(shutdowns.__anext__(), 1)
            shutdowns.task_done()
            assert isinstance(event, ShutdownEvent)
            await asyncio.wait_for(coordinator, 1)

    asyncio.run(scenario())


def test_runtime_profiles_progress_and_adapter_validation() -> None:
    async def scenario() -> None:
        settings = Settings.model_validate({"profiles": {"default": "agent"}})
        runtime = ApplicationRuntime(
            SimpleNamespace(
                load_settings=lambda: settings,
                inspect_profiles=lambda: [
                    ProfileEntry("agent", "Agent", make_profile())
                ],
            )
        )
        async with runtime:
            assert runtime.default_profile_id == "agent"
            assert runtime.selected_profile is None
            assert runtime.startup_profile is runtime.profiles[0].profile
            assert isinstance(runtime.progress, ProgressStore)
            with pytest.raises(RuntimeError, match="not running"):
                await runtime.wait()

    asyncio.run(scenario())


def test_runtime_resolves_explicit_selected_profile_without_fallback() -> None:
    async def scenario() -> None:
        agent = make_profile()
        other = make_profile()
        other = other.model_copy(update={"id": "other"})
        runtime = ApplicationRuntime(
            SimpleNamespace(
                load_settings=lambda: Settings.model_validate(
                    {"profiles": {"default": "agent", "selected": "other"}}
                ),
                inspect_profiles=lambda: [
                    ProfileEntry("agent", "Agent", agent),
                    ProfileEntry("other", "Other", other),
                    ProfileEntry("broken", "Broken", error="bad profile"),
                ],
            )
        )
        async with runtime:
            assert runtime.selected_profile is other
            assert runtime.startup_profile is other

        missing = ApplicationRuntime(
            SimpleNamespace(
                load_settings=lambda: Settings.model_validate(
                    {"profiles": {"selected": "missing"}}
                ),
                inspect_profiles=lambda: [ProfileEntry("agent", "Agent", agent)],
            )
        )
        async with missing:
            with pytest.raises(
                ValueError, match="Selected profile does not exist: missing"
            ):
                _ = missing.startup_profile

        fallback = ApplicationRuntime(
            SimpleNamespace(
                load_settings=lambda: Settings.model_validate(
                    {"profiles": {"default": "missing"}}
                ),
                inspect_profiles=lambda: [ProfileEntry("agent", "Agent", agent)],
            )
        )
        async with fallback:
            assert fallback.startup_profile is agent

    asyncio.run(scenario())

    for adapter, value in (
        ("mlx:qwen3-asr", make_profile(stt={"model_id": "qwen"})),
        ("mlx:whisper", make_profile(stt={"model_id": "whisper"})),
    ):
        runtime_module._validate_runtime_profile(
            value,
            Settings.model_validate(
                {
                    "conversation": {"language_model": {"adapter": "mlx"}},
                    "speech": {"stt": {"adapter": adapter}},
                }
            ),
        )
    runtime_module._validate_runtime_profile(
        make_profile(tts={"model_id": "chatterbox"}),
        Settings.model_validate(
            {
                "conversation": {"language_model": {"adapter": "mlx"}},
                "speech": {"tts": {"adapter": "mlx:chatterbox"}},
            }
        ),
    )


def test_progress_subscriptions_are_thread_safe_snapshots() -> None:
    store = ProgressStore()
    received = []
    unsubscribe = store.subscribe(received.append)
    item = store.begin("weights", 0, 10, "B")
    store.update(item, completed=5)
    unsubscribe()
    store.complete(item, 10, 10)
    assert [snapshot.items[0].completed for snapshot in received] == [0, 5]
