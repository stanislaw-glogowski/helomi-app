from collections.abc import Iterator
from typing import ClassVar

from huggingface_hub.utils import disable_progress_bars
from supertonic import TTS, Style

from ...audio import AudioFormat, RawAudio
from ..domain import TTSChunk, TTSRequest
from ..ports import TTSAdapter
from .config import SupertonicConfig, SupertonicOptions


class SupertonicAdapter(TTSAdapter[SupertonicConfig, SupertonicOptions]):
    _AUDIO_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_44

    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: TTS | None = None
        self._styles: dict[str, Style] = {}

    def synthesize(
        self,
        request: TTSRequest,
        options: SupertonicOptions,
    ) -> Iterator[Exception | TTSChunk]:
        try:
            model = self._require_model()

            style = self._styles.get(options.voice_name)
            if style is None:
                style = (
                    model.get_voice_style_from_path(options.voice_path)
                    if options.voice_path
                    else model.get_voice_style(options.voice_name)
                )
                self._styles[options.voice_name] = style

            samples, _ = model.synthesize(
                text=request.raw_text,
                voice_style=style,
                total_steps=options.quality,
                speed=options.speed,
                max_chunk_length=options.max_chunk_length,
                silence_duration=options.silence_duration,
                lang=options.language or self._config.language,
                verbose=False,
            )

            yield TTSChunk(
                audio=RawAudio(
                    format=self._AUDIO_FORMAT,
                    data=samples.tobytes(),
                )
            )

            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open(self) -> None:
        with disable_progress_bars():
            cfg = self._config

            self._logger.debug("Loading model: {}", cfg.model.id)
            self._model = TTS(
                model=cfg.model.name,
                model_dir=cfg.model.path,
                intra_op_num_threads=cfg.intra_threads,
                inter_op_num_threads=cfg.inter_threads,
            )

    def _do_close(self) -> None:
        if self._model is None:
            return

    def _require_model(self) -> TTS:
        if self._model is None:
            raise RuntimeError("Supertonic model is not loaded")

        return self._model
