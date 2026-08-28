from openwakeword import VAD

from ...audio import AudioChunk
from ..domain import VADPrediction
from ..ports import VADAdapter
from .config import SileroVADONNXConfig


class SileroVADONNXAdapter(VADAdapter[SileroVADONNXConfig]):
    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: VAD | None = None

    def predict(self, audio: AudioChunk) -> VADPrediction:
        model = self._require_model()

        prediction = model.predict(
            audio.samples,
            frame_size=audio.format.block_size,
        )

        score = float(prediction.item())

        return VADPrediction(
            detected=score >= self._config.threshold,
            score=score,
        )

    def reset(self) -> None:
        self._require_model().reset_states()

    def _do_open(self) -> None:
        cfg = self._config
        self._logger.debug("Loading model: {}", cfg.model_path.name)
        self._model = VAD(
            model_path=str(cfg.model_path),
        )

    def _do_close(self) -> None:
        self._model = None

    def _require_model(self) -> VAD:
        if self._model is None:
            raise RuntimeError("ONNX SileroVAD model is not loaded")
        return self._model
