import asyncio
import threading
from contextlib import aclosing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from helomi_runtime.audio import AudioFormat, AudioStreamBuffer, RawAudio
from helomi_runtime.audio.avfaudio.config import AVFAudioSettings
from helomi_runtime.audio.avfaudio.driver import AVFAudioDriver
from helomi_runtime.audio.avfaudio.protocol import (
    ErrorCode,
    ErrorPacket,
    MessageKind,
    WireFrame,
)
from helomi_runtime.audio.twilio.mixer import TwilioMixer
from helomi_runtime.synthesis import SynthesisChunk, SynthesisRequest, SynthesisWorker
from tests.fixtures.audio import create_raw_audio
from tests.fixtures.mocks import MockSynthesisAdapter


def test_audio_stream_buffer_preserves_samples_and_tail():
    audio = create_raw_audio(sample_rate=48000, num_samples=10001)
    buffer = AudioStreamBuffer()
    portions = []
    for offset in range(0, len(audio.data), 28):
        portions.extend(
            buffer.feed(RawAudio(audio.format, audio.data[offset : offset + 28]))
        )
    portions.append(buffer.finish())
    assert RawAudio.concat(portions) == audio
    assert [portion.duration_seconds for portion in portions[:2]] == [0.1, 0.1]
    assert buffer.finish() is None
    with pytest.raises(ValueError, match="duration"):
        AudioStreamBuffer(0)
    with pytest.raises(ValueError, match="incomplete"):
        list(AudioStreamBuffer().feed(RawAudio(audio.format, b"\x00")))
    with pytest.raises(ValueError, match="format changed"):
        list(buffer.feed(create_raw_audio(sample_rate=16000, num_samples=1)))


async def test_synthesis_exhaustion_and_close_keep_thread_affinity():
    threads = []
    raw = create_raw_audio(num_samples=320)

    class Adapter(MockSynthesisAdapter):
        def synthesize(self, request):
            threads.append(threading.get_ident())
            try:
                yield SynthesisChunk(raw)
                yield SynthesisChunk(raw)
            finally:
                threads.append(threading.get_ident())

    worker = SynthesisWorker(Adapter())
    async with worker:
        async with aclosing(
            worker.synthesize(SynthesisRequest("Full text", "alexa"))
        ) as stream:
            assert (await anext(stream)).audio == raw
        assert len(threads) == 2
        results = [
            chunk
            async for chunk in worker.synthesize(
                SynthesisRequest("Natural exhaustion", "alexa")
            )
        ]
        assert len(results) == 2
    assert len(set(threads)) == 1
    assert threads[0] != threading.get_ident()


async def test_cancelled_running_generation_closes_before_next_request():
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    steps = []
    raw = create_raw_audio(num_samples=320)

    class Adapter(MockSynthesisAdapter):
        def synthesize(self, request):
            try:
                if request.text == "blocked":
                    entered.set()
                    assert release.wait(2)
                steps.append(request.text)
                yield SynthesisChunk(raw)
            finally:
                steps.append("close:" + request.text)
                closed.set()

    async with SynthesisWorker(Adapter()) as worker:

        async def consume():
            return [
                chunk
                async for chunk in worker.synthesize(
                    SynthesisRequest("blocked", "alexa")
                )
            ]

        task = asyncio.create_task(consume())
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert (
            len(
                [
                    chunk
                    async for chunk in worker.synthesize(
                        SynthesisRequest("next", "alexa")
                    )
                ]
            )
            == 1
        )
    assert steps == ["blocked", "close:blocked", "next", "close:next"]


async def test_concurrent_synthesis_requests_do_not_interleave_model_state():
    raw = create_raw_audio(num_samples=320)
    async with SynthesisWorker(
        MockSynthesisAdapter(chunks=[SynthesisChunk(raw)])
    ) as worker:
        first = worker.synthesize(SynthesisRequest("first", "alexa"))
        second = worker.synthesize(SynthesisRequest("second", "alexa"))
        await anext(first)
        pending = asyncio.create_task(anext(second))
        await asyncio.sleep(0)
        assert not pending.done()
        await first.aclose()
        assert (await asyncio.wait_for(pending, 1)).audio == raw
        await second.aclose()


def driver_fixture():
    driver = AVFAudioDriver(AVFAudioSettings(), {})
    writer = MagicMock()
    writer.drain = AsyncMock()
    reader = asyncio.StreamReader()
    driver._proc = SimpleNamespace(stdin=writer, stdout=reader)
    driver._ready_signal.set()
    events = []
    driver._dispatch_event = events.append
    return driver, writer, reader, events


def feed(reader, frame):
    reader.feed_data(
        WireFrame._HEADER.pack(frame.kind, frame.request_id, len(frame.payload))
        + frame.payload
    )


async def test_avfaudio_late_interrupted_ack_cannot_complete_new_playback():
    driver, writer, reader, events = driver_fixture()
    raw = create_raw_audio(num_samples=320)
    await driver.play(raw, playback_id="old")
    old = next(iter(driver._playback_requests))
    await driver.interrupt()
    await driver.play(raw, playback_id="new")
    new = next(iter(driver._playback_requests))
    feed(reader, WireFrame(MessageKind.PLAYBACK_FINISHED, b"\x01", old))
    feed(reader, WireFrame(MessageKind.PLAYBACK_FINISHED, b"\x00", new))
    reader.feed_eof()
    await driver._proc_loop()
    assert [(event.playback_id, event.status) for event in events] == [
        ("old", "interrupted"),
        ("new", "played"),
    ]
    assert writer.drain.await_count == 3
    assert driver._pending_playbacks == 0


async def test_avfaudio_out_of_order_error_and_eof_resolve_correct_playbacks():
    driver, _, reader, events = driver_fixture()
    for name in ("first", "second", "third"):
        await driver.play(create_raw_audio(num_samples=320), playback_id=name)
    first, second, _ = driver._playback_requests
    feed(reader, WireFrame(MessageKind.PLAYBACK_FINISHED, b"\x00", second))
    error = ErrorPacket(
        code=ErrorCode.AUDIO_CONVERSION_FAILED, message="Synthetic error", fatal=False
    )
    feed(reader, WireFrame(MessageKind.ERROR, error.pack(), first))
    reader.feed_eof()
    await driver._proc_loop()
    assert [(event.playback_id, event.status) for event in events] == [
        ("second", "played"),
        ("first", "failed"),
        ("third", "failed"),
    ]
    assert not driver._ready_signal.is_set()


def test_twilio_mixer_fills_frames_across_portions_and_resets_session_turn():
    mixer = TwilioMixer(50)
    raw = RawAudio(AudioFormat.MONO_8, np.ones(80, dtype=np.float32).tobytes())
    assert mixer.enqueue(raw, "one", 5)
    assert mixer.enqueue(raw, "two", 5)
    frame = mixer.next_frame()
    assert frame.completed_playbacks == ("one", "two")
    assert len(set(frame.data)) == 1
    assert not mixer.has_output
    mixer.interrupt()
    assert mixer.enqueue(raw, "new-call", 0)


def test_voxcpm_reference_cache_retains_whole_input_and_closes_streams(tmp_path: Path):
    from helomi_runtime.synthesis.voxcpm2.adapter import VoxCPM2Adapter
    from helomi_runtime.synthesis.voxcpm2.config import VoxCPM2Profile, VoxCPM2Settings

    reference = tmp_path / "reference.wav"
    reference.touch()
    cache_calls = []
    texts = []
    closed = []

    class Waveform:
        def squeeze(self, axis):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.ones(2400, dtype=np.float64)

    class Model:
        sample_rate = 24000

        def build_prompt_cache(self, **kwargs):
            cache_calls.append(kwargs)
            return {"reference": "cached"}

        def generate_with_prompt_cache_streaming(self, **kwargs):
            texts.append(kwargs["target_text"])
            try:
                yield Waveform(), None, None
            finally:
                closed.append(True)

    adapter = VoxCPM2Adapter(
        VoxCPM2Settings(), {"alexa": VoxCPM2Profile(ref_audio=reference)}
    )
    adapter._model = SimpleNamespace(tts_model=Model())
    text = "A complete sentence. Another sentence with its original context."
    for _ in range(2):
        stream = adapter.synthesize(SynthesisRequest(text, "alexa"))
        chunk = next(stream)
        assert chunk.audio.format.sample_rate == 24000
        assert chunk.audio.duration_seconds == pytest.approx(0.1)
        stream.close()
    assert len(cache_calls) == 1
    assert texts == [text, text]
    assert len(closed) == 2
    adapter._release_model()
    assert not adapter._prompt_caches
