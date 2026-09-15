from collections.abc import AsyncIterator, Iterator
from typing import ClassVar

from ...common import AbstractWorker
from ..audio import AudioChunk, AudioFormat, AudioResampler, RawAudio
from ..turn import TurnAdapter, TurnPrediction, TurnStatus
from ..vad import VADAdapter
from ..wakeword import WakeWordAdapter, WakeWordPrediction
from .domain import DetectionMode
from .messages import (
    ConversationEndedEvent,
    DetectionEvent,
    UtteranceContinuedEvent,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)


class DetectionWorker(AbstractWorker):
    _INPUT_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_16

    def __init__(
        self,
        turn_adapter: TurnAdapter,
        vad_adapter: VADAdapter,
        wakeword_adapter: WakeWordAdapter | None = None,
    ) -> None:
        super().__init__()
        self._default_mode = (
            DetectionMode.WAKEWORD if wakeword_adapter else DetectionMode.UTTERANCE
        )
        self._current_mode = self._default_mode
        self._vad_adapter = vad_adapter
        self._turn_adapter = turn_adapter
        self._wakeword_adapter = wakeword_adapter
        self._resamples = AudioResampler(self._INPUT_FORMAT)

    @property
    def wakeword_supported(self) -> bool:
        return self._wakeword_adapter is not None

    @property
    def current_mode(self) -> DetectionMode:
        return self._current_mode

    async def change_mode(self, mode: DetectionMode | None, force=False) -> bool:
        if mode is None:
            mode = self._default_mode

        if (mode == DetectionMode.WAKEWORD and self._wakeword_adapter is None) or (
            self._current_mode == mode and not force
        ):
            return False

        self._current_mode = mode
        await self._run_sync(self._reset)
        return True

    async def detect(self, raw: RawAudio) -> AsyncIterator[DetectionEvent]:
        iterator = await self._run_sync(self._detect_sync, raw)
        while not self._exit_signal.is_set():
            match await self._run_sync(next, iterator):
                case StopIteration():
                    return
                case Exception() as err:
                    raise err
                case result:
                    yield result

    def _detect_sync(
        self,
        raw: RawAudio,
    ) -> Iterator[Exception | DetectionEvent]:
        try:
            for chunk in self._resamples.resample(raw):
                vad_prediction = self._vad_adapter.predict(chunk)

                prediction: TurnPrediction | WakeWordPrediction | None = None

                match self._current_mode:
                    case DetectionMode.WAKEWORD if self._wakeword_adapter is not None:
                        prediction = self._wakeword_adapter.predict(
                            chunk,
                            vad_prediction.detected,
                        )

                    case DetectionMode.UTTERANCE:
                        prediction = self._turn_adapter.predict(
                            chunk,
                            vad_prediction.detected,
                        )

                match prediction:
                    case TurnPrediction(status=TurnStatus.STARTED):
                        yield UtteranceStartedEvent()

                    case TurnPrediction(
                        status=TurnStatus.COMPLETED, audio=AudioChunk() as audio
                    ):
                        yield UtteranceDetectedEvent(
                            audio=audio,
                        )
                    case TurnPrediction(status=TurnStatus.CONTINUED):
                        yield UtteranceContinuedEvent()

                    case TurnPrediction(status=TurnStatus.TIMEOUT):
                        self._vad_adapter.reset()
                        self._turn_adapter.reset()
                        yield ConversationEndedEvent()

                    case WakeWordPrediction(matched=str(profile_id)) if (
                        self._wakeword_adapter is not None
                    ):
                        self._current_mode = DetectionMode.UTTERANCE
                        self._vad_adapter.reset()
                        self._wakeword_adapter.reset()
                        yield WakeWordDetectedEvent(
                            profile_id=profile_id,
                        )

            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open_sync(self) -> None:
        self._exit_stack.enter_context(self._turn_adapter)
        self._exit_stack.enter_context(self._vad_adapter)
        if self._wakeword_adapter is not None:
            self._exit_stack.enter_context(self._wakeword_adapter)
        self._exit_stack.callback(self._resamples.reset)

    def _do_close_sync(self) -> None:
        self._current_mode = self._default_mode

    def _reset(self) -> None:
        self._vad_adapter.reset()
        match self._current_mode:
            case DetectionMode.WAKEWORD if self._wakeword_adapter is not None:
                self._wakeword_adapter.reset()
            case DetectionMode.UTTERANCE:
                self._turn_adapter.reset()
