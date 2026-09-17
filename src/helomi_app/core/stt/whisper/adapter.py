from collections.abc import Iterator

from ..domain import STTChunk, STTRequest
from ..ports import STTAdapter
from .config import WhisperProfile, WhisperSettings


class WhisperAdapter(STTAdapter[WhisperSettings, WhisperProfile]):
    def transcribe(self, request: STTRequest) -> Iterator[Exception | STTChunk]:
        import mlx_whisper

        profile = self._profiles.get(request.profile_id, None)

        if not profile:
            self._logger.warning("No profile found for {}", request.profile_id)
            yield StopIteration()
            return

        try:
            self._require_open()

            cfg = self._settings

            output = mlx_whisper.transcribe(
                audio=request.audio.samples,
                path_or_hf_repo=str(cfg.model.path),
                initial_prompt=profile.initial_prompt,
                **{
                    "language": profile.language or cfg.language,
                },
            )

            text = output.get("text")
            if isinstance(text, str):
                yield STTChunk(
                    text=text,
                )

            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open(self):
        self._logger.debug("Using model: {}", self._settings.model.id)
