from collections.abc import Iterator
from typing import ClassVar

from huggingface_hub.utils import disable_progress_bars
from supertonic import TTS, Style

from ...audio import AudioFormat, RawAudio
from ..domain import TTSChunk, TTSRequest
from ..ports import TTSAdapter
from .config import SupertonicProfile, SupertonicSettings


class SupertonicAdapter(TTSAdapter[SupertonicSettings, SupertonicProfile]):
    _AUDIO_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_44

    def __init__(self, settings, profiles) -> None:
        super().__init__(settings, profiles)
        self._model: TTS | None = None
        self._styles: dict[str, Style] = {}

    def synthesize(self, request: TTSRequest) -> Iterator[Exception | TTSChunk]:
        try:
            profile = self._profiles.get(request.profile_id, None)
            text = request.raw_text

            if not profile:
                self._logger.warning("No profile found for {}", request.profile_id)

            if not text or not profile:
                yield StopIteration()
                return

            model = self._require_model()

            style = self._styles.get(profile.voice_name)
            if style is None:
                style = (
                    model.get_voice_style_from_path(profile.voice_path)
                    if profile.voice_path
                    else model.get_voice_style(profile.voice_name)
                )
                self._styles[profile.voice_name] = style

            samples, _ = model.synthesize(
                text=text,
                voice_style=style,
                total_steps=profile.quality,
                speed=profile.speed,
                max_chunk_length=profile.max_chunk_length,
                silence_duration=profile.silence_duration,
                lang=profile.language or self._settings.language,
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
            cfg = self._settings

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
