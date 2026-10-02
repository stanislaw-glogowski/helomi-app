from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

from huggingface_hub.utils import disable_progress_bars

from helomi_foundation import on_mount, on_unmount

from ..config import TranscriptionOptions
from ..domain import TranscriptionChunk, TranscriptionRequest
from ..ports import TranscriptionAdapter
from .config import ParakeetProfile, ParakeetSettings

if TYPE_CHECKING:
    from mlx_audio.stt.models.parakeet import Model as ModelType
else:
    ModelType = Any


class ParakeetAdapter(TranscriptionAdapter[ParakeetSettings, ParakeetProfile]):
    def __init__(
        self,
        settings: ParakeetSettings,
        profiles: dict[str, ParakeetProfile],
        options: TranscriptionOptions,
    ):
        super().__init__(settings, profiles)
        self._options = options
        self._model: ModelType | None = None

    def transcribe(
        self, request: TranscriptionRequest
    ) -> Iterator[Exception | TranscriptionChunk]:
        try:
            model = self._require_model()
            profile = self._profiles.get(request.profile_id, None)

            if not profile:
                self._logger.warning("No profile found for {}", request.profile_id)
                yield StopIteration()
                return

            stream = model.stream_generate(
                audio=request.audio.to_mlx(),
                language=profile.language or self._options.language,
                verbose=False,
            )

            for chunk in stream:
                if chunk.text:
                    yield TranscriptionChunk(
                        text=chunk.text,
                    )

            yield StopIteration()
        except Exception as error:
            yield error

    @on_mount()
    def _load_model(self):
        from mlx_audio.stt import load

        with disable_progress_bars():
            settings = self._settings

            self._logger.debug("Loading model: {}", settings.model.id)
            self._model = cast(Any, load(settings.model.path))

    @on_unmount()
    def _release_model(self):
        self._model = None

    def _require_model(self) -> ModelType:
        if self._model is None:
            raise RuntimeError("Parakeet model is not loaded")
        return self._model
