from typing import TYPE_CHECKING, Any, cast

from huggingface_hub.utils import disable_progress_bars

from helomi_foundation import Logger, on_mount, on_unmount

from ...audio import AudioChunk
from ..config import VADOptions
from ..domain import VADPrediction
from ..ports import VADAdapter
from .config import SileroVADConfig

if TYPE_CHECKING:
    from mlx_audio.vad.models.silero_vad import Model as ModelType
    from mlx_audio.vad.models.silero_vad import SileroVADState as StateType
else:
    type ModelType = Any
    type StateType = Any


class SileroVADAdapter(VADAdapter):
    def __init__(
        self,
        config: SileroVADConfig,
        options: VADOptions,
        logger: Logger | None = None,
    ):
        super().__init__(logger)
        self._config = config
        self._options = options
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
            detected=score >= self._options.threshold,
            score=score,
        )

    def reset(self):
        self._require_model()
        self._state = None

    @on_mount()
    def _load_model(self):
        from mlx_audio.vad import load

        with disable_progress_bars():
            config = self._config

            self._logger.debug("Loading model: {}", config.model.id)
            self._model = cast(Any, load(config.model.path))

    @on_unmount()
    def _release_model(self):
        self._model = None
        self._state = None

    def _require_model(self) -> ModelType:
        if self._model is None:
            raise RuntimeError("SileroVAD model is not loaded")
        return self._model
