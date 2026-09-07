from typing import TYPE_CHECKING, Any, cast

import numpy as np
from huggingface_hub.utils import disable_progress_bars

from ...audio import AudioChunk
from ..domain import TurnPrediction, TurnStatus
from ..ports import TurnAdapter
from .config import SmartTurnConfig
from .state import SmartTurnState

if TYPE_CHECKING:
    from mlx_audio.vad.models.smart_turn import Model as ModelType
else:
    ModelType = Any


class SmartTurnAdapter(TurnAdapter[SmartTurnConfig]):
    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: ModelType | None = None
        self._state: SmartTurnState | None = None

    def predict(self, audio: AudioChunk, voice_detected: bool) -> TurnPrediction | None:
        model = self._require_model()
        cfg = self._config
        state = self._state

        if state is None:
            state = SmartTurnState(cfg, audio)
            self._state = state

        samples = np.asarray(audio.samples, dtype=np.float32).copy()

        # 1. Idle state (waiting for speech to start)
        if not state.active:
            if not voice_detected:
                state.pre_roll.append(samples)
                state.idle_silence_samples += samples.size

                # Detect inactivity timeout -> conversation ended
                if state.idle_silence_samples >= state.conversation_timeout_samples:
                    state.reset(full=True)
                    return TurnPrediction(status=TurnStatus.TIMEOUT)

                return None

            # Speech detected: transition to active turn
            state.active = True
            state.idle_silence_samples = 0
            state.turn_frames = list(state.pre_roll)
            state.turn_frames.append(samples)
            state.last_voice_frame_idx = len(state.turn_frames) - 1
            state.speech_samples = samples.size
            state.silence_samples = 0
            state.waiting_for_continuation = False
            return TurnPrediction(status=TurnStatus.STARTED)

        # 2. Active state: speech currently detected
        if voice_detected:
            state.turn_frames.append(samples)
            state.last_voice_frame_idx = len(state.turn_frames) - 1
            state.speech_samples += samples.size
            state.silence_samples = 0
            state.waiting_for_continuation = False

            # Force completion if max turn duration is reached
            if state.speech_samples >= state.max_turn_samples:
                return self._complete_turn(state, score=1.0)

            return None

        # 3. Active state: silence / pause
        state.turn_frames.append(samples)
        state.silence_samples += samples.size

        # Reject short noise bursts (< min_speech_seconds) followed by silence
        if state.speech_samples < state.min_speech_samples:
            if state.silence_samples >= state.silence_samples_required:
                state.reset(full=False)
            return None

        # Fallback timeout: speaker remained silent after a continuation pause
        if state.waiting_for_continuation:
            if state.silence_samples >= state.fallback_silence_samples:
                return self._complete_turn(state, score=1.0)
            return None

        # Check endpoint model once sufficient silence has accumulated
        if state.silence_samples < state.silence_samples_required:
            return None

        candidate_samples = np.concatenate(state.turn_frames)
        eval_window = candidate_samples[
            -round(cfg.max_audio_seconds * audio.format.sample_rate) :
        ]

        output = model.predict_endpoint(
            eval_window,
            sample_rate=audio.format.sample_rate,
            threshold=cfg.threshold,
        )
        score = float(output.probability)

        if output.prediction == 0:
            # Model predicts intermediate pause in utterance
            state.waiting_for_continuation = True
            return TurnPrediction(status=TurnStatus.CONTINUED, score=score)

        return self._complete_turn(state, score=score)

    def _complete_turn(self, state: SmartTurnState, score: float) -> TurnPrediction:
        # Trim audio to last voiced frame plus configured post-roll margin
        end_idx = min(
            len(state.turn_frames),
            state.last_voice_frame_idx + 1 + state.post_roll_frames,
        )
        trimmed_frames = state.turn_frames[:end_idx]

        candidate = AudioChunk(
            format=state.format,
            samples=np.concatenate(trimmed_frames),
        )
        state.reset(full=False)

        return TurnPrediction(
            status=TurnStatus.COMPLETED,
            audio=candidate,
            score=score,
        )

    def reset(self) -> None:
        self._require_model()

        if self._state is not None:
            self._state.reset(full=True)

    def _do_open(self) -> None:
        from mlx_audio.vad import load

        with disable_progress_bars():
            cfg = self._config

            self._logger.debug("Loading model: {}", cfg.model.id)
            self._model = cast(Any, load(cfg.model.path))

    def _do_close(self) -> None:
        self._state = None
        self._model = None

    def _require_model(self) -> ModelType:
        if self._model is None:
            raise RuntimeError("SmartTurn is not loaded")

        return self._model
