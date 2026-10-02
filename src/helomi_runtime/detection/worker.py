from collections.abc import AsyncGenerator, Iterator
from contextlib import aclosing
from functools import partial
from typing import ClassVar

from helomi_foundation import Logger, ThreadedComponent, on_mount, on_unmount

from ..audio import AudioChunk, AudioFormat, AudioResampler, RawAudio
from .domain import DetectionMode, TurnPrediction, TurnStatus, WakeWordPrediction
from .messages import (
    ConversationEndedEvent,
    DetectionEvent,
    UtteranceContinuedEvent,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)
from .ports import TurnAdapter, VADAdapter, WakeWordAdapter


class DetectionWorker(ThreadedComponent):
    _INPUT_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_16

    def __init__(
        self,
        turn_adapter: TurnAdapter,
        vad_adapter: VADAdapter,
        wakeword_adapter: WakeWordAdapter | None = None,
        logger: Logger | None = None,
    ):
        super().__init__(logger)
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

    async def set_mode(self, mode: DetectionMode | None, force=False) -> bool:
        if mode is None:
            mode = self._default_mode

        if (mode == DetectionMode.WAKEWORD and self._wakeword_adapter is None) or (
            self._current_mode == mode and not force
        ):
            return False

        self._current_mode = mode
        await self._run_in_executor(self._reset_adapters)
        return True

    async def detect(self, raw: RawAudio) -> AsyncGenerator[DetectionEvent]:
        async with aclosing(
            self._iterate_in_executor(partial(self._detect_sync, raw))
        ) as stream:
            async for item in stream:
                match item:
                    case StopIteration():
                        return
                    case Exception() as error:
                        raise error
                    case result:
                        yield result

    async def reset_idle_timeout(self) -> None:
        await self._run_in_executor(self._turn_adapter.reset_idle_timeout)

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
                        if (
                            self._wakeword_adapter is not None
                            and vad_prediction.detected
                        ):
                            wake_pred = self._wakeword_adapter.predict(
                                chunk,
                                vad_prediction.detected,
                            )
                            if wake_pred and wake_pred.matched:
                                prediction = wake_pred
                            else:
                                prediction = self._turn_adapter.predict(
                                    chunk,
                                    vad_prediction.detected,
                                )
                        else:
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
                        self._current_mode = self._default_mode
                        self._reset_adapters()
                        yield ConversationEndedEvent()

                    case WakeWordPrediction(matched=str(profile_id)) if (
                        self._wakeword_adapter is not None
                    ):
                        self._current_mode = DetectionMode.UTTERANCE
                        self._reset_adapters()
                        yield WakeWordDetectedEvent(
                            profile_id=profile_id,
                        )

            yield StopIteration()
        except Exception as error:
            yield error

    @on_mount()
    async def _start(self):
        await self._run_in_executor(self._start_sync)

    def _start_sync(self):
        self._turn_adapter.mount()
        self._vad_adapter.mount()
        if self._wakeword_adapter is not None:
            self._wakeword_adapter.mount()

    @on_unmount(order=-10)
    async def _stop(self):
        await self._run_in_executor(self._stop_sync)

    def _stop_sync(self):
        errors: list[BaseException] = []
        for adapter in (
            self._wakeword_adapter,
            self._vad_adapter,
            self._turn_adapter,
        ):
            if adapter is None:
                continue
            try:
                adapter.unmount()
            except BaseException as error:
                errors.append(error)
        self._resamples.reset()
        if errors:
            raise BaseExceptionGroup("Detection adapter cleanup failed", errors)

    @on_unmount()
    def _reset_mode(self):
        self._current_mode = self._default_mode

    def _reset_adapters(self):
        self._vad_adapter.reset()
        self._turn_adapter.reset()
        if self._wakeword_adapter is not None:
            self._wakeword_adapter.reset()
