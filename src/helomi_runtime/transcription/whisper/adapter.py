from collections.abc import Iterator

from helomi_foundation import on_mount

from ..config import TranscriptionOptions
from ..domain import TranscriptionChunk, TranscriptionRequest
from ..ports import TranscriptionAdapter
from .config import WhisperProfile, WhisperSettings


class WhisperAdapter(TranscriptionAdapter[WhisperSettings, WhisperProfile]):
    def __init__(
        self,
        settings: WhisperSettings,
        profiles: dict[str, WhisperProfile],
        options: TranscriptionOptions,
    ):
        super().__init__(settings, profiles)
        self._options = options

    def transcribe(
        self, request: TranscriptionRequest
    ) -> Iterator[Exception | TranscriptionChunk]:
        import mlx_whisper

        profile = self._profiles.get(request.profile_id, None)

        if not profile:
            self._logger.warning("No profile found for {}", request.profile_id)
            yield StopIteration()
            return

        try:
            if not self.is_mounted:
                raise RuntimeError("Whisper adapter is not mounted")

            settings = self._settings

            output = mlx_whisper.transcribe(
                audio=request.audio.samples,
                path_or_hf_repo=str(settings.model.path),
                initial_prompt=profile.initial_prompt,
                **{
                    "language": profile.language or self._options.language,
                },
            )

            text = output.get("text")
            if isinstance(text, str):
                yield TranscriptionChunk(
                    text=text,
                )

            yield StopIteration()
        except Exception as error:
            yield error

    @on_mount()
    def _prepare_model(self):
        self._logger.debug("Using model: {}", self._settings.model.id)
