from openwakeword import VAD

from ...audio import AudioChunk
from ..domain import VADPrediction
from ..ports import VADAdapter
from .config import SileroVADONNXSettings


class SileroVADONNXAdapter(VADAdapter[SileroVADONNXSettings]):
    def __init__(self, settings):
        super().__init__(settings)
        self._model: VAD | None = None

    def predict(self, audio: AudioChunk) -> VADPrediction:
        model = self._require_model()

        prediction = model.predict(
            audio.samples,
            frame_size=audio.format.block_size,
        )

        score = float(prediction.item())

        return VADPrediction(
            detected=score >= self._settings.threshold,
            score=score,
        )

    def reset(self):
        self._require_model().reset_states()

    def _do_open(self):
        cfg = self._settings
        self._logger.debug("Loading model: {}", cfg.model_path.name)
        self._model = VAD(
            model_path=str(cfg.model_path),
        )

    def _do_close(self):
        self._model = None

    def _require_model(self) -> VAD:
        if self._model is None:
            raise RuntimeError("ONNX SileroVAD model is not loaded")
        return self._model
