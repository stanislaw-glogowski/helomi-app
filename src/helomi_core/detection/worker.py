from collections.abc import AsyncIterator, Iterator
from typing import ClassVar

from helomi_common import AbstractWorker

from ..audio import AudioChunk, AudioFormat, AudioResampler, RawAudio
from ..turn import TurnAdapter, TurnPrediction, TurnStatus
from ..vad import VADAdapter
from ..wakeword import WakeWordAdapter, WakeWordPrediction
from .domain import (
    ConversationEnded,
    DetectionMode,
    DetectionResult,
    ProfileDetected,
    UtteranceContinued,
    UtteranceDetected,
    UtteranceStarted,
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
            DetectionMode.PROFILE if wakeword_adapter else DetectionMode.UTTERANCE
        )
        self._current_mode = self._default_mode
        self._vad_adapter = vad_adapter
        self._turn_adapter = turn_adapter
        self._wakeword_adapter = wakeword_adapter

        self._resamples = AudioResampler(self._INPUT_FORMAT)

    @property
    def current_mode(self) -> DetectionMode:
        return self._current_mode

    async def change_mode(self, mode: DetectionMode | None) -> None:
        if self._current_mode == mode:
            return
        if self._executor is None:
            self._reset(mode)
            return
        await self._run_sync(self._reset, mode)

    async def detect(self, raw: RawAudio) -> AsyncIterator[DetectionResult]:
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
    ) -> Iterator[Exception | DetectionResult]:
        try:
            for chunk in self._resamples.resample(raw):
                vad_prediction = self._vad_adapter.predict(chunk)

                prediction: TurnPrediction | WakeWordPrediction | None = None

                match self._current_mode:
                    case DetectionMode.PROFILE if self._wakeword_adapter is not None:
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
                        yield UtteranceStarted()

                    case TurnPrediction(
                        status=TurnStatus.COMPLETED, audio=AudioChunk() as audio
                    ):
                        yield UtteranceDetected(
                            audio=audio,
                        )
                    case TurnPrediction(status=TurnStatus.CONTINUED):
                        yield UtteranceContinued()

                    case TurnPrediction(status=TurnStatus.TIMEOUT):
                        self._reset()
                        if self._wakeword_adapter:
                            yield ConversationEnded()

                    case WakeWordPrediction(matched=str(profile_id)):
                        self._reset(DetectionMode.UTTERANCE)
                        yield ProfileDetected(
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
        self._exit_stack.callback(self._reset)

    def _reset(self, mode: DetectionMode | None = None) -> None:
        self._current_mode = mode if mode is not None else self._default_mode
        self._vad_adapter.reset()

        match self._current_mode:
            case DetectionMode.PROFILE if self._wakeword_adapter is not None:
                self._wakeword_adapter.reset()

            case DetectionMode.UTTERANCE:
                self._turn_adapter.reset()
