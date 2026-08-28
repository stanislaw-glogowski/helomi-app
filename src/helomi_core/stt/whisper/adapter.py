from collections.abc import Iterator

from ..domain import STTChunk, STTRequest
from ..ports import STTAdapter
from .config import WhisperConfig, WhisperOptions


class WhisperAdapter(STTAdapter[WhisperConfig, WhisperOptions]):
    def transcribe(
        self,
        request: STTRequest,
        options: WhisperOptions,
    ) -> Iterator[Exception | STTChunk]:
        import mlx_whisper

        try:
            self._require_open()

            cfg = self._config

            output = mlx_whisper.transcribe(
                audio=request.audio.samples,
                path_or_hf_repo=str(cfg.model.path),
                initial_prompt=options.initial_prompt,
                **{
                    "language": options.language or cfg.language,
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

    def _do_open(self) -> None:
        self._logger.debug("Using model: {}", self._config.model.id)
