from typing import TYPE_CHECKING, Any, cast

from huggingface_hub.utils import disable_progress_bars

from ...audio import AudioChunk
from ..domain import VADPrediction
from ..ports import VADAdapter
from .config import SileroVADMLXConfig

if TYPE_CHECKING:
    from mlx_audio.vad.models.silero_vad import Model as ModelType
    from mlx_audio.vad.models.silero_vad import SileroVADState as StateType
else:
    type ModelType = Any
    type StateType = Any


class SileroVADMLXAdapter(VADAdapter[SileroVADMLXConfig]):
    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: ModelType | None = None
        self._state: StateType | None = None

    def predict(self, audio: AudioChunk) -> VADPrediction:
        model = self._require_model()

        probability, self._state = model.feed(
            audio.samples,
            self._state,
            sample_rate=audio.format.sample_rate,
        )

        score = float(cast(Any, probability.item()))

        return VADPrediction(
            detected=score >= self._config.threshold,
            score=score,
        )

    def reset(self) -> None:
        self._require_model()
        self._state = None

    def _do_open(self) -> None:
        from mlx_audio.vad import load

        with disable_progress_bars():
            cfg = self._config

            self._logger.debug("Loading model: {}", cfg.model.id)
            self._model = cast(Any, load(cfg.model.path))

    def _do_close(self) -> None:
        self._model = None
        self._state = None

    def _require_model(self) -> ModelType:
        if self._model is None:
            raise RuntimeError("MLX SileroVAD model is not loaded")
        return self._model
