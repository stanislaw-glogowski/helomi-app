import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

from helomi_runtime.audio import (
    AudioChunk,
    AudioCommand,
    AudioDriver,
    AudioDriverCapabilities,
    AudioDriverDescriptor,
    AudioDriverKind,
    AudioEvent,
    AudioFormat,
    CapturedEvent,
    DisconnectCommand,
    DisconnectedEvent,
    InterruptCommand,
    PlayCommand,
    RawAudio,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)
from helomi_runtime.detection import TurnAdapter, VADAdapter, WakeWordAdapter
from helomi_runtime.detection.domain import (
    TurnPrediction,
    VADPrediction,
    WakeWordPrediction,
)
from helomi_runtime.resources import ResourceCatalog
from helomi_runtime.synthesis import SynthesisAdapter, SynthesisChunk, SynthesisRequest
from helomi_runtime.transcription import (
    TranscriptionAdapter,
    TranscriptionChunk,
    TranscriptionRequest,
)


class MockAudioDriver(AudioDriver[Any, Any]):
    _DESCRIPTOR = AudioDriverDescriptor(
        id="avfaudio",
        name="Mock audio",
        kind=AudioDriverKind.LOCAL,
        capabilities=AudioDriverCapabilities(
            capture=True,
            playback=True,
            interrupt=True,
            room_voice=True,
            remote_session=False,
            local_monitoring=True,
            manual_profile_selection=True,
        ),
    )

    def __init__(
        self,
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        incoming_chunks: list[RawAudio] | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
        self.played_audio: list[RawAudio] = []
        self.interrupt_count = 0
        self.room_voice_started = False
        self.room_voice_profile_id: str | None = None
        self._queued_chunks: list[RawAudio] = list(incoming_chunks or [])

    @property
    def descriptor(self) -> AudioDriverDescriptor:
        return self._DESCRIPTOR

    def enqueue_capture(self, raw: RawAudio) -> None:
        if self._subscriptions:
            self._dispatch_event(CapturedEvent(audio=raw))
        else:
            self._queued_chunks.append(raw)

    async def subscribe_events(self) -> AsyncIterator[AudioEvent]:
        subscription = asyncio.Queue[AudioEvent | None]()
        self._subscriptions.add(subscription)
        while self._queued_chunks:
            chunk = self._queued_chunks.pop(0)
            subscription.put_nowait(CapturedEvent(audio=chunk))
        try:
            while not self._exit_signal.is_set():
                event = await subscription.get()
                if event is None:
                    break
                yield event
                subscription.task_done()
        finally:
            self._subscriptions.discard(subscription)

    async def capture(self) -> AsyncIterator[RawAudio]:
        async for event in self.subscribe_events():
            if isinstance(event, CapturedEvent):
                yield event.audio

    async def execute_command(self, cmd: AudioCommand) -> bool:
        match cmd:
            case PlayCommand():
                self.played_audio.append(cmd.audio)
                return True
            case InterruptCommand():
                self.interrupt_count += 1
                return True
            case StartRoomVoiceCommand():
                self.room_voice_started = True
                self.room_voice_profile_id = cmd.profile_id
                return True
            case StopRoomVoiceCommand():
                self.room_voice_started = False
                self.room_voice_profile_id = None
                return True
            case DisconnectCommand():
                self._dispatch_event(DisconnectedEvent())
                return True
            case _:
                return False


class MockVADAdapter(VADAdapter):
    def __init__(self, settings: Any = None, default_detected: bool = True) -> None:
        super().__init__()
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


class MockWakeWordAdapter(WakeWordAdapter):
    def __init__(
        self,
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        matched: str | None = None,
    ) -> None:
        super().__init__()
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


class MockTurnAdapter(TurnAdapter):
    def __init__(
        self,
        settings: Any = None,
        prediction: TurnPrediction | None = None,
    ) -> None:
        super().__init__()
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


class MockTranscriptionAdapter(TranscriptionAdapter[Any, Any]):
    def __init__(
        self,
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        chunks: list[TranscriptionChunk | Exception] | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
        self.chunks: list[TranscriptionChunk | Exception] = (
            chunks if chunks is not None else [TranscriptionChunk(text="Hello world")]
        )
        self.calls: list[TranscriptionRequest] = []

    def transcribe(
        self, request: TranscriptionRequest
    ) -> Iterator[Exception | TranscriptionChunk]:
        self.calls.append(request)
        yield from self.chunks
        yield StopIteration()


class MockSynthesisAdapter(SynthesisAdapter[Any, Any]):
    def __init__(
        self,
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        chunks: list[SynthesisChunk | Exception] | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
        self.chunks: list[SynthesisChunk | Exception] = (
            chunks
            if chunks is not None
            else [
                SynthesisChunk(
                    audio=RawAudio(
                        format=AudioFormat.MONO_16,
                        data=b"\x00" * 1024,
                    )
                )
            ]
        )
        self.calls: list[SynthesisRequest] = []

    def synthesize(
        self, request: SynthesisRequest
    ) -> Iterator[Exception | SynthesisChunk]:
        self.calls.append(request)
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
