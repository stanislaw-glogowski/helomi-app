import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

from helomi_app.audio import (
    AudioChunk,
    AudioCmd,
    AudioDriver,
    AudioDriverKind,
    AudioEvent,
    AudioFormat,
    CapturedEvent,
    DisconnectCmd,
    DisconnectedEvent,
    InterruptCmd,
    InterruptedEvent,
    PlayCmd,
    PlayedEvent,
    RawAudio,
    RoomVoiceStartedEvent,
    RoomVoiceStoppedEvent,
    StartRoomVoiceCmd,
    StopRoomVoiceCmd,
)
from helomi_app.resources import ResourceCatalog
from helomi_app.stt import STTAdapter, STTChunk, STTRequest
from helomi_app.tts import TTSAdapter, TTSChunk, TTSRequest
from helomi_app.turn import TurnAdapter, TurnPrediction
from helomi_app.vad import VADAdapter, VADPrediction
from helomi_app.wakeword import WakeWordAdapter, WakeWordPrediction


class MockAudioDriver(AudioDriver[Any, Any]):
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
    def kind(self) -> AudioDriverKind:
        return AudioDriverKind.LOCAL

    def enqueue_capture(self, raw: RawAudio) -> None:
        if self._subscriptions:
            self._dispatch_event(CapturedEvent(audio=raw))
        else:
            self._queued_chunks.append(raw)

    async def subscribe_event(self) -> AsyncIterator[AudioEvent]:
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
        async for event in self.subscribe_event():
            if isinstance(event, CapturedEvent):
                yield event.audio_driver

    def execute_command(self, cmd: AudioCmd) -> bool:
        match cmd:
            case PlayCmd():
                self.played_audio.append(cmd.audio_driver)
                self._dispatch_event(PlayedEvent(profile_id=cmd.profile_id))
                return True
            case InterruptCmd():
                self.interrupt_count += 1
                self._dispatch_event(InterruptedEvent(profile_id=cmd.profile_id))
                return True
            case StartRoomVoiceCmd():
                self.room_voice_started = True
                self.room_voice_profile_id = cmd.profile_id
                self._dispatch_event(RoomVoiceStartedEvent(profile_id=cmd.profile_id))
                return True
            case StopRoomVoiceCmd():
                self.room_voice_started = False
                self.room_voice_profile_id = None
                self._dispatch_event(RoomVoiceStoppedEvent())
                return True
            case DisconnectCmd():
                self._dispatch_event(DisconnectedEvent())
                return True
            case _:
                return False


class MockVADAdapter(VADAdapter[Any]):
    def __init__(self, settings: Any = None, default_detected: bool = True) -> None:
        super().__init__(settings)
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
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        matched: str | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
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
        settings: Any = None,
        prediction: TurnPrediction | None = None,
    ) -> None:
        super().__init__(settings)
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
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        chunks: list[STTChunk | Exception] | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
        self.chunks: list[STTChunk | Exception] = (
            chunks if chunks is not None else [STTChunk(text="Hello world")]
        )
        self.calls: list[STTRequest] = []

    def transcribe(self, request: STTRequest) -> Iterator[Exception | STTChunk]:
        self.calls.append(request)
        yield from self.chunks
        yield StopIteration()


class MockTTSAdapter(TTSAdapter[Any, Any]):
    def __init__(
        self,
        settings: Any = None,
        profiles: dict[str, Any] | None = None,
        chunks: list[TTSChunk | Exception] | None = None,
    ) -> None:
        super().__init__(settings, profiles or {})
        self.chunks: list[TTSChunk | Exception] = (
            chunks
            if chunks is not None
            else [
                TTSChunk(
                    audio=RawAudio(
                        format=AudioFormat.MONO_16,
                        data=b"\x00" * 1024,
                    )
                )
            ]
        )
        self.calls: list[TTSRequest] = []

    def synthesize(self, request: TTSRequest) -> Iterator[Exception | TTSChunk]:
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
