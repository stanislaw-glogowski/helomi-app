from collections.abc import Iterator
from typing import Any

from ...audio import AudioFrame
from ..config import MLXQwen3ASRProfile, MLXQwen3ASRSettings
from ..domain import TranscriptionChunk
from .mlx_base import MLXBaseModel


class Qwen3ASRModel(MLXBaseModel[MLXQwen3ASRProfile, MLXQwen3ASRSettings]):
    _MODEL_LABEL = "Qwen3 ASR"

    def transcribe(self, frame: AudioFrame) -> Iterator[TranscriptionChunk]:
        from mlx_audio.stt.models.base import STTOutput

        model = self._require_model()

        options: dict[str, Any] = {
            "stream": False,
        }
        if self._settings.language is not None:
            options["language"] = self._settings.language

        result = model.generate(frame.samples, **options)

        if not isinstance(result, STTOutput):
            raise RuntimeError("Qwen3 ASR returned an unexpected streaming result")

        if text := result.text.strip():
            yield TranscriptionChunk(content=text)
