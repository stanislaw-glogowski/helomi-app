import asyncio
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from helomi_app.messages import (
    ActivateProfileCommand,
    ActivationSource,
    CallStartedEvent,
    CommandRejectionCode,
    ConversationState,
    EndConversationCommand,
    ProcessingFailedEvent,
    ResponseMode,
    SayReactionCommand,
    SayTextCommand,
    SynthesisReadyEvent,
)
from helomi_runtime.audio import (
    AudioFormat,
    ConnectedEvent,
    DisconnectedEvent,
    RawAudio,
)
from helomi_runtime.detection import DetectionMode, UtteranceStartedEvent
from helomi_runtime.reaction import ReactionKind
from helomi_runtime.synthesis import SynthesisChunk
from tests.unit.helomi_app.test_conversation_service import create_service, raw_audio


async def activate(service):
    assert (
        await service.execute_command(
            ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
        )
    ).accepted


async def drain(service):
    await asyncio.wait_for(service._speech_queue.join(), 3)
    await asyncio.wait_for(service._playback_queue.join(), 3)


async def test_stream_starts_before_generation_finishes_and_preserves_full_audio(
    tmp_path: Path,
):
    service, router, _ = create_service(tmp_path, response_mode=ResponseMode.API)
    generated = RawAudio(
        AudioFormat.MONO_48, np.arange(9600, dtype=np.float32).tobytes()
    )
    first_play = asyncio.Event()
    finish_generation = asyncio.Event()
    texts = []
    original_play = router.play

    async def play(audio, **kwargs):
        result = await original_play(audio, **kwargs)
        first_play.set()
        return result

    class StreamingWorker:
        async def synthesize(self, request):
            texts.append(request.text)
            yield SynthesisChunk(RawAudio(generated.format, generated.data[:19200]))
            await finish_generation.wait()
            yield SynthesisChunk(RawAudio(generated.format, generated.data[19200:]))

    router.play = play
    service._synthesis_worker = StreamingWorker()
    events = []
    async with router, service:
        await activate(service)

        async def collect():
            async for event in service.subscribe_events():
                events.append(event)
                if isinstance(event, SynthesisReadyEvent):
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        text = "First sentence.\nSecond sentence with complete context."
        assert (
            await service.execute_command(
                SayTextCommand(text=text, mode=ResponseMode.API)
            )
        ).accepted
        await asyncio.wait_for(first_play.wait(), 1)
        assert not finish_generation.is_set()
        assert service.state == ConversationState.SPEAKING
        assert not any(isinstance(event, SynthesisReadyEvent) for event in events)
        finish_generation.set()
        await drain(service)
        await asyncio.wait_for(collector, 1)
        assert texts == [text]
        assert RawAudio.concat([item[0] for item in router.played]) == generated
        assert (
            next(
                event for event in events if isinstance(event, SynthesisReadyEvent)
            ).audio
            == generated
        )
        assert service.state == ConversationState.LISTENING


async def test_small_chunks_apply_backpressure_without_loss(tmp_path: Path):
    service, router, _ = create_service(tmp_path, response_mode=ResponseMode.API)
    acknowledged = asyncio.Event()
    first_play = asyncio.Event()
    produced = 0
    raw = RawAudio(AudioFormat.MONO_48, np.ones(480, dtype=np.float32).tobytes())
    original_play = router.play

    async def play(audio, **kwargs):
        result = await original_play(audio, **kwargs)
        first_play.set()
        return result

    async def wait_for_playback(playback_id, timeout_seconds):
        await acknowledged.wait()
        return True

    class StreamingWorker:
        async def synthesize(self, request):
            nonlocal produced
            for _ in range(501):
                produced += 1
                yield SynthesisChunk(raw)

    router.play = play
    router.wait_for_playback = wait_for_playback
    service._synthesis_worker = StreamingWorker()
    async with router, service:
        await activate(service)
        await service.execute_command(
            SayTextCommand(text="Complete input", mode=ResponseMode.API)
        )
        await asyncio.wait_for(first_play.wait(), 1)
        await asyncio.sleep(0)
        assert service._buffered_audio_seconds <= 1.0 + 1e-9
        assert produced <= 110
        acknowledged.set()
        await drain(service)
        assert produced == 501
        assert b"".join(item[0].data for item in router.played) == raw.data * 501
        assert service._buffered_audio_seconds == pytest.approx(0)


async def test_burst_of_100_texts_is_played_in_fifo_order(tmp_path: Path):
    raw = raw_audio()
    service, router, _ = create_service(
        tmp_path, response_mode=ResponseMode.API, synthesis_chunks=[SynthesisChunk(raw)]
    )
    seen = []

    class Worker:
        async def synthesize(self, request):
            seen.append(request.text)
            yield SynthesisChunk(raw)

    service._synthesis_worker = Worker()
    async with router, service:
        await activate(service)
        for index in range(100):
            assert (
                await service.execute_command(
                    SayTextCommand(text=str(index), mode=ResponseMode.API)
                )
            ).accepted
        await drain(service)
    assert seen == [str(index) for index in range(100)]
    assert len(router.played) == 100


async def test_adapter_failure_does_not_stop_next_request(tmp_path: Path):
    service, router, _ = create_service(tmp_path, response_mode=ResponseMode.API)

    class Worker:
        async def synthesize(self, request):
            if request.text == "fail":
                raise RuntimeError("Synthetic failure")
            yield SynthesisChunk(raw_audio())

    service._synthesis_worker = Worker()
    failures = []
    async with router, service:
        await activate(service)

        async def collect():
            async for event in service.subscribe_events():
                if isinstance(event, ProcessingFailedEvent):
                    failures.append(event)
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        for text in ("fail", "works"):
            await service.execute_command(
                SayTextCommand(text=text, mode=ResponseMode.API)
            )
        await drain(service)
        await asyncio.wait_for(collector, 1)
        assert not any(task.done() for task in service._tasks)
    assert len(router.played) == 1
    assert failures[0].stage == "synthesis"
    assert failures[0].detail == "Synthetic failure"


@pytest.mark.parametrize("failure", ["rejected", "exception", "acknowledgement"])
async def test_playback_failure_releases_capacity_and_keeps_service_running(
    tmp_path: Path, failure: str
):
    service, router, _ = create_service(
        tmp_path,
        response_mode=ResponseMode.API,
        synthesis_chunks=[SynthesisChunk(raw_audio())],
    )
    original_play = router.play
    failed = False

    async def play(audio, **kwargs):
        nonlocal failed
        if not failed and failure != "acknowledgement":
            failed = True
            if failure == "exception":
                raise RuntimeError("Transport failed")
            return False
        return await original_play(audio, **kwargs)

    async def wait_for_playback(playback_id, timeout_seconds):
        nonlocal failed
        if not failed:
            failed = True
            return False
        return True

    router.play = play
    if failure == "acknowledgement":
        router.wait_for_playback = wait_for_playback
    async with router, service:
        await activate(service)
        for text in ("Fails", "Works after failure"):
            assert (
                await service.execute_command(
                    SayTextCommand(text=text, mode=ResponseMode.API)
                )
            ).accepted
            await drain(service)
        assert service._buffered_audio_seconds == pytest.approx(0)
        assert service.state == ConversationState.LISTENING
        assert not any(task.done() for task in service._tasks)
        assert len(router.played) == (2 if failure == "acknowledgement" else 1)


async def test_interruption_wakes_blocked_producer_and_discards_old_speech(
    tmp_path: Path,
):
    service, router, _ = create_service(tmp_path, response_mode=ResponseMode.API)
    first_play = asyncio.Event()
    closed = asyncio.Event()
    old_ack = asyncio.Event()
    raw = RawAudio(AudioFormat.MONO_48, b"\x00" * 19200)
    original_play = router.play

    async def play(audio, **kwargs):
        result = await original_play(audio, **kwargs)
        first_play.set()
        return result

    async def wait_for_playback(playback_id, timeout_seconds):
        await old_ack.wait()
        return True

    class Worker:
        async def synthesize(self, request):
            try:
                for _ in range(100):
                    yield SynthesisChunk(raw)
            finally:
                closed.set()

    router.play = play
    router.wait_for_playback = wait_for_playback
    service._synthesis_worker = Worker()
    async with router, service:
        await activate(service)
        for text in ("old", "queued old"):
            await service.execute_command(
                SayTextCommand(text=text, mode=ResponseMode.API)
            )
        await asyncio.wait_for(first_play.wait(), 1)
        await service._handle_detection_event(UtteranceStartedEvent())
        old_ack.set()
        await asyncio.wait_for(closed.wait(), 1)
        await drain(service)
        assert service._speech_queue.empty()
        assert service.state == ConversationState.LISTENING
        assert router.interruptions == 1
        assert all(turn_id == 0 for _, _, turn_id in router.played)


async def test_connected_plays_once_per_call_without_manual_greeting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    greeting = raw_audio()
    connected = RawAudio(greeting.format, np.ones(320, dtype=np.float32).tobytes())
    service, router, _ = create_service(
        tmp_path,
        reactions={ReactionKind.GREETING: greeting, ReactionKind.CONNECTED: connected},
    )
    monkeypatch.setattr(service, "_CONNECTED_REACTION_DELAY_SECONDS", 0.0)
    router.remote_profile_id = "alexa"
    async with router, service:
        await activate(service)
        await drain(service)
        first_session = service._identity.session_id
        event = ConnectedEvent("twilio", "alexa", "CA1", "+15555550100")
        await service._handle_audio_event(event)
        await drain(service)
        await service._handle_audio_event(event)
        await drain(service)
        assert service._identity.session_id != first_session
        await service._handle_audio_event(DisconnectedEvent("twilio", "CA1"))
        await service._handle_audio_event(
            ConnectedEvent("twilio", "alexa", "CA2", "+15555550100")
        )
        await drain(service)
    assert [item[0] for item in router.played] == [connected, connected]


async def test_connected_delay_does_not_block_call_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    connected = raw_audio()
    service, router, _ = create_service(
        tmp_path,
        reactions={ReactionKind.CONNECTED: connected},
    )
    router.remote_profile_id = "alexa"
    delay_started = asyncio.Event()
    release_delay = asyncio.Event()
    original_sleep = asyncio.sleep

    async def controlled_sleep(delay_seconds: float):
        if delay_seconds == service._CONNECTED_REACTION_DELAY_SECONDS:
            delay_started.set()
            await release_delay.wait()
            return
        await original_sleep(delay_seconds)

    monkeypatch.setattr(asyncio, "sleep", controlled_sleep)
    events = []
    async with router, service:

        async def collect():
            async for event in service.subscribe_events():
                events.append(event)
                if isinstance(event, CallStartedEvent):
                    return

        collector = asyncio.create_task(collect())
        await original_sleep(0)
        await service._handle_audio_event(
            ConnectedEvent("twilio", "alexa", "CA1", "+15555550100")
        )
        await asyncio.wait_for(collector, 1)
        await asyncio.wait_for(delay_started.wait(), 1)

        assert service._CONNECTED_REACTION_DELAY_SECONDS == 2.0
        assert service.active_profile is not None
        assert not router.played
        assert any(isinstance(event, CallStartedEvent) for event in events)

        release_delay.set()
        await drain(service)

    assert [item[0] for item in router.played] == [connected]


async def test_disconnect_cancels_delayed_connected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    service, router, _ = create_service(
        tmp_path,
        reactions={ReactionKind.CONNECTED: raw_audio()},
    )
    router.remote_profile_id = "alexa"
    delay_started = asyncio.Event()

    async def blocked_sleep(delay_seconds: float):
        assert delay_seconds == service._CONNECTED_REACTION_DELAY_SECONDS
        delay_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "sleep", blocked_sleep)
    async with router, service:
        await service._handle_audio_event(
            ConnectedEvent("twilio", "alexa", "CA1", "+15555550100")
        )
        await asyncio.wait_for(delay_started.wait(), 1)
        await service._handle_audio_event(DisconnectedEvent("twilio", "CA1"))
        await drain(service)

    assert service.active_profile is None
    assert not router.played


async def test_explicit_reactions_remain_immediate(tmp_path: Path):
    greeting = raw_audio()
    connected = RawAudio(greeting.format, np.ones(320, dtype=np.float32).tobytes())
    service, router, _ = create_service(
        tmp_path,
        reactions={ReactionKind.GREETING: greeting, ReactionKind.CONNECTED: connected},
    )
    async with router, service:
        await activate(service)
        for reaction in (ReactionKind.GREETING, ReactionKind.CONNECTED):
            result = await service.execute_command(
                SayReactionCommand(reaction=reaction, mode=ResponseMode.PARROT)
            )
            assert result.accepted
        await drain(service)

    assert [item[0] for item in router.played] == [greeting, connected]


@pytest.mark.parametrize(
    "state", [ConversationState.PROCESSING, ConversationState.SPEAKING]
)
async def test_follow_up_timeout_does_not_end_active_response(tmp_path: Path, state):
    service, _, detection = create_service(tmp_path)
    await activate(service)
    service._set_state(state)
    await service._handle_follow_up_timeout()
    assert service.state == state
    assert service.active_profile is not None
    assert detection.current_mode == DetectionMode.UTTERANCE


async def test_stale_turn_commands_and_turn_pair_validation(tmp_path: Path):
    service, _, _ = create_service(tmp_path, response_mode=ResponseMode.API)
    await activate(service)
    token = service._identity.current()
    await service._handle_detection_event(UtteranceStartedEvent())
    result = await service.execute_command(
        SayTextCommand(
            text="Old answer",
            mode=ResponseMode.API,
            session_id=token.session_id,
            turn_id=token.turn_id,
        )
    )
    assert result.rejection_code == CommandRejectionCode.STALE_TURN
    assert (
        await service.execute_command(
            EndConversationCommand(session_id=token.session_id, turn_id=token.turn_id)
        )
    ).rejection_code == CommandRejectionCode.STALE_TURN
    with pytest.raises(ValidationError, match="provided together"):
        SayTextCommand(text="Hello", mode=ResponseMode.API, turn_id=0)


async def test_graceful_close_waits_for_audio_without_blocking_barge_in(tmp_path: Path):
    service, router, _ = create_service(
        tmp_path,
        response_mode=ResponseMode.API,
        synthesis_chunks=[SynthesisChunk(raw_audio())],
    )
    acknowledged = asyncio.Event()

    async def wait_for_playback(playback_id, timeout_seconds):
        await acknowledged.wait()
        return True

    router.wait_for_playback = wait_for_playback
    async with router, service:
        await activate(service)
        await service.execute_command(
            SayTextCommand(text="Goodbye", mode=ResponseMode.API)
        )
        closing = asyncio.create_task(
            service.execute_command(EndConversationCommand(wait_for_speech=True))
        )
        await asyncio.sleep(0)
        assert not closing.done()
        await service._handle_detection_event(UtteranceStartedEvent())
        acknowledged.set()
        result = await asyncio.wait_for(closing, 1)
        assert result.rejection_code == CommandRejectionCode.STALE_TURN
        assert service.active_profile is not None
