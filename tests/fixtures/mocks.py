import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from helomi_core.audio import (
    AudioChunk,
    AudioDriver,
    AudioFormat,
    AudioMode,
    RawAudio,
)
from helomi_core.audio.config import AudioProfile
from helomi_core.resources import ResourceCatalog
from helomi_core.stt import STTAdapter, STTChunk, STTRequest
from helomi_core.tts import TTSAdapter, TTSChunk, TTSRequest
from helomi_core.turn import TurnAdapter, TurnPrediction
from helomi_core.vad import VADAdapter, VADPrediction
from helomi_core.wakeword import WakeWordAdapter, WakeWordPrediction


class MockAudioDriver(AudioDriver[Any]):
    def __init__(
        self,
        config: Any = None,
        mode: AudioMode | None = None,
        incoming_chunks: list[RawAudio] | None = None,
    ) -> None:
        super().__init__(config, mode)
        self.played_audio: list[RawAudio] = []
        self.interrupt_count = 0
        self.room_voice_started = False
        self.room_voice_path: Path | str | None = None
        self.activated_profile: AudioProfile | None = None
        self._initial_chunks: list[RawAudio] = incoming_chunks or []
        self._incoming_queue: asyncio.Queue[RawAudio] | None = None

    @property
    def queue(self) -> asyncio.Queue[RawAudio]:
        if self._incoming_queue is None:
            self._incoming_queue = asyncio.Queue()
            for chunk in self._initial_chunks:
                self._incoming_queue.put_nowait(chunk)
            self._initial_chunks = []
        return self._incoming_queue

    def enqueue_capture(self, raw: RawAudio) -> None:
        self.queue.put_nowait(raw)

    async def capture(self) -> AsyncIterator[RawAudio]:
        while not self._exit_signal.is_set():
            try:
                chunk = await asyncio.wait_for(self.queue.get(), timeout=0.02)
                yield chunk
                self.queue.task_done()
            except TimeoutError:
                if self._exit_signal.is_set():
                    break
            except asyncio.CancelledError:
                break

    def play(self, audio: RawAudio) -> None:
        self.played_audio.append(audio)

    def interrupt(self) -> bool:
        self.interrupt_count += 1
        return True

    async def activate(self, profile: AudioProfile) -> None:
        self.activated_profile = profile
        if profile.room_voice_path:
            self.room_voice_started = True
            self.room_voice_path = profile.room_voice_path

    async def deactivate(self) -> None:
        self.activated_profile = None
        self.room_voice_started = False


class MockVADAdapter(VADAdapter[Any]):
    def __init__(self, config: Any = None, default_detected: bool = True) -> None:
        super().__init__(config)
        self.detected = default_detected
        self.score = 0.95
        self.predict_hook: Callable[[AudioChunk], VADPrediction] | None = None
        self.reset_count = 0

    def predict(self, audio: AudioChunk) -> VADPrediction:
        if self.predict_hook:
            return self.predict_hook(audio)
        return VADPrediction(detected=self.detected, score=self.score)

    def reset(self) -> None:
        self.reset_count += 1


class MockWakeWordAdapter(WakeWordAdapter[Any, Any]):
    def __init__(
        self,
        config: Any = None,
        words: dict[str, Any] | None = None,
        matched: str | None = None,
    ) -> None:
        super().__init__(config, words or {})
        self.matched = matched
        self.scores: dict[str, float] = {}
        self.predict_hook: Callable[[AudioChunk, bool], WakeWordPrediction] | None = (
            None
        )
        self.reset_count = 0

    def predict(self, audio: AudioChunk, voice_detected: bool) -> WakeWordPrediction:
        if self.predict_hook:
            return self.predict_hook(audio, voice_detected)
        return WakeWordPrediction(matched=self.matched, scores=self.scores)

    def reset(self) -> None:
        self.reset_count += 1


class MockTurnAdapter(TurnAdapter[Any]):
    def __init__(
        self,
        config: Any = None,
        prediction: TurnPrediction | None = None,
    ) -> None:
        super().__init__(config)
        self.next_prediction = prediction
        self.predictions: list[TurnPrediction | None] = []
        self.predict_hook: (
            Callable[[AudioChunk, bool], TurnPrediction | None] | None
        ) = None
        self.reset_count = 0

    def predict(self, audio: AudioChunk, voice_detected: bool) -> TurnPrediction | None:
        if self.predict_hook:
            return self.predict_hook(audio, voice_detected)
        if self.predictions:
            return self.predictions.pop(0)
        return self.next_prediction

    def reset(self) -> None:
        self.reset_count += 1


class MockSTTAdapter(STTAdapter[Any, Any]):
    def __init__(
        self,
        config: Any = None,
        chunks: list[STTChunk | Exception] | None = None,
    ) -> None:
        super().__init__(config)
        self.chunks: list[STTChunk | Exception] = (
            chunks if chunks is not None else [STTChunk(text="Hello world")]
        )
        self.calls: list[tuple[STTRequest, Any]] = []

    def transcribe(
        self, request: STTRequest, options: Any = None
    ) -> Iterator[Exception | STTChunk]:
        self.calls.append((request, options))
        yield from self.chunks
        yield StopIteration()


class MockTTSAdapter(TTSAdapter[Any, Any]):
    def __init__(
        self,
        config: Any = None,
        chunks: list[TTSChunk] | None = None,
    ) -> None:
        super().__init__(config)
        self.chunks = chunks or [
            TTSChunk(
                audio=AudioChunk(
                    format=AudioFormat.MONO_16,
                    samples=np.zeros(512, dtype=np.float32),
                )
            )
        ]
        self.calls: list[tuple[TTSRequest, Any]] = []

    def synthesize(
        self, request: TTSRequest, options: Any = None
    ) -> Iterator[Exception | TTSChunk]:
        self.calls.append((request, options))
        yield from self.chunks
        yield StopIteration()


class MockResourceCatalog(ResourceCatalog):
    def __init__(
        self,
        root_path: Path,
        settings_data: dict[str, Any] | None = None,
        profiles_data: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._root = root_path
        self._settings_data = settings_data or {}
        self._profiles_data = profiles_data or {}

    @property
    def root_path(self) -> Path:
        return self._root
