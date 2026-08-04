from collections.abc import Iterator
from typing import Any

from ...audio import AudioFrame
from ..config import MLXWhisperProfile, MLXWhisperSettings
from ..domain import TranscriptionChunk
from .mlx_base import MLXBaseModel


class WhisperModel(MLXBaseModel[MLXWhisperProfile, MLXWhisperSettings]):
    _MODEL_LABEL = "Whisper"

    def transcribe(self, frame: AudioFrame) -> Iterator[TranscriptionChunk]:
        model = self._require_model()

        options: dict[str, Any] = {
            "task": "transcribe",
            "verbose": None,
        }
        if self._settings.language is not None:
            options["language"] = self._settings.language

        result = model.generate(
            frame.samples,
            **options,
        )
        if text := result.text.strip():
            yield TranscriptionChunk(content=text)
