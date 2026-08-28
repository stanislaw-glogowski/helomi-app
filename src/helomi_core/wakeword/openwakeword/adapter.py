from collections import defaultdict

import numpy as np
from openwakeword import Model

from ...audio import AudioChunk
from ..domain import WakeWordPrediction
from ..ports import WakeWordAdapter
from .config import OpenWakeWordConfig, OpenWakeWordOptions


class OpenWakeWordAdapter(WakeWordAdapter[OpenWakeWordConfig, OpenWakeWordOptions]):
    def __init__(self, config, words) -> None:
        super().__init__(config, words)
        self._model: Model | None = None
        self._profile_mapping: dict[str, str] = {}
        self._samples_buffer = np.empty(0, dtype=np.float32)
        self._recent_voice_frames: int = 0
        self._consecutive_frames: dict[str, int] = defaultdict(int)

    def predict(self, audio: AudioChunk, voice_detected: bool) -> WakeWordPrediction:
        model = self._require_model()
        cfg = self._config

        if voice_detected:
            self._recent_voice_frames = 15  # Maintain voice active status for ~480ms
        elif self._recent_voice_frames > 0:
            self._recent_voice_frames -= 1

        incoming_samples = np.asarray(
            audio.samples,
            dtype=np.float32,
        ).reshape(-1)

        samples = np.asarray(
            np.concatenate(
                (self._samples_buffer, incoming_samples),
            ),
            dtype=np.float32,
        )

        complete_samples = (samples.size // cfg.frame_size) * cfg.frame_size

        matched: str | None = None
        scores: dict[str, float] = {}

        if complete_samples == 0:
            self._samples_buffer = samples
        else:
            self._samples_buffer = samples[complete_samples:].copy()

            chunks = samples[:complete_samples].reshape(-1, cfg.frame_size)

            highest_score = 0.0
            is_voice_active = voice_detected or self._recent_voice_frames > 0

            for chunk in chunks:
                float_chunk = np.asarray(
                    chunk,
                    dtype=np.float32,
                )

                clipped = np.asarray(
                    np.clip(float_chunk, -1.0, 1.0),
                    dtype=np.float32,
                )

                scaled = clipped * np.float32(32767.0)

                pcm16_chunk = np.asarray(
                    np.rint(scaled),
                    dtype=np.int16,
                )

                prediction = model.predict(pcm16_chunk)

                if not isinstance(prediction, dict):
                    raise RuntimeError("OpenWakeWord returned timing data unexpectedly")

                for model_name, score in prediction.items():
                    profile_id = self._profile_mapping.get(model_name)

                    if profile_id is None:
                        continue

                    word = self._words.get(profile_id)

                    if word is None:
                        continue

                    scores[profile_id] = max(scores.get(profile_id, 0), score)

                    threshold = word.threshold or self._config.threshold
                    patience = word.patience or self._config.patience

                    if score >= threshold:
                        self._consecutive_frames[profile_id] += 1
                    else:
                        self._consecutive_frames[profile_id] = 0

                    if (
                        is_voice_active
                        and self._consecutive_frames[profile_id] >= patience
                    ):
                        if score > highest_score:
                            highest_score = score
                            matched = profile_id
        return WakeWordPrediction(
            matched=matched,
            scores=scores,
        )

    def reset(self) -> None:
        self._require_model().reset()
        self._samples_buffer = np.empty(0, dtype=np.float32)
        self._recent_voice_frames = 0
        self._consecutive_frames.clear()

    def _do_open(self) -> None:
        cfg = self._config

        names: list[str] = []
        models: list[str] = []
        for profile_id, options in self._words.items():
            if not options.model_path:
                continue
            name = options.model_path.stem
            self._profile_mapping[name] = profile_id
            models.append(str(options.model_path))
            names.append(name)

        self._logger.debug("Loading models: {}", ", ".join(names))

        self._model = Model(
            inference_framework="onnx",
            wakeword_models=models,
            **{
                "embedding_model_path": str(cfg.embedding_path),
                "melspec_model_path": str(cfg.melspec_path),
            },
        )

    def _do_close(self) -> None:
        self._samples_buffer = np.empty(0, dtype=np.float32)
        self._consecutive_frames.clear()
        self._profile_mapping.clear()
        self._model = None

    def _require_model(self) -> Model:
        if self._model is None:
            raise RuntimeError("OpenWakeWord model is not loaded")
        return self._model
