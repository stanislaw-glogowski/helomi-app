from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

from huggingface_hub.utils import disable_progress_bars

from ..domain import STTChunk, STTRequest
from ..ports import STTAdapter
from .config import ParakeetConfig, ParakeetOptions

if TYPE_CHECKING:
    from mlx_audio.stt.models.parakeet import Model as ModelType
else:
    ModelType = Any


class ParakeetAdapter(STTAdapter[ParakeetConfig, ParakeetOptions]):
    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: ModelType | None = None

    def transcribe(
        self,
        request: STTRequest,
        options: ParakeetOptions,
    ) -> Iterator[Exception | STTChunk]:
        try:
            model = self._require_model()

            stream = model.stream_generate(
                audio=request.audio.to_mlx(),
                language=options.language or self._config.language,
                verbose=False,
            )

            for chunk in stream:
                if chunk.text:
                    yield STTChunk(
                        text=chunk.text,
                    )

            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open(self) -> None:
        from mlx_audio.stt import load

        with disable_progress_bars():
            cfg = self._config

            self._logger.debug("Loading model: {}", cfg.model.id)
            self._model = cast(Any, load(cfg.model.path))

    def _do_close(self) -> None:
        self._model = None

    def _require_model(self) -> ModelType:
        if self._model is None:
            raise RuntimeError("Parakeet model is not loaded")
        return self._model
