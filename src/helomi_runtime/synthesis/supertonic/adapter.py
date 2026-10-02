from collections.abc import Iterator
from typing import ClassVar

from huggingface_hub.utils import disable_progress_bars
from supertonic import TTS, Style

from helomi_foundation import on_mount, on_unmount

from ...audio import AudioFormat, RawAudio
from ..domain import SynthesisChunk, SynthesisRequest
from ..ports import SynthesisAdapter
from .config import SupertonicProfile, SupertonicSettings


class SupertonicAdapter(SynthesisAdapter[SupertonicSettings, SupertonicProfile]):
    _AUDIO_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_44

    def __init__(self, settings, profiles):
        super().__init__(settings, profiles)
        self._model: TTS | None = None
        self._styles: dict[str, Style] = {}

    def synthesize(
        self, request: SynthesisRequest
    ) -> Iterator[Exception | SynthesisChunk]:
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

            yield SynthesisChunk(
                audio=RawAudio(
                    format=self._AUDIO_FORMAT,
                    data=samples.tobytes(),
                )
            )

            yield StopIteration()
        except Exception as error:
            yield error

    @on_mount()
    def _load_model(self):
        with disable_progress_bars():
            settings = self._settings

            self._logger.debug("Loading model: {}", settings.model.id)
            self._model = TTS(
                model=settings.model.name,
                model_dir=settings.model.path,
                intra_op_num_threads=settings.intra_threads,
                inter_op_num_threads=settings.inter_threads,
            )

    @on_unmount()
    def _release_model(self):
        self._styles.clear()
        self._model = None

    def _require_model(self) -> TTS:
        if self._model is None:
            raise RuntimeError("Supertonic model is not loaded")

        return self._model
