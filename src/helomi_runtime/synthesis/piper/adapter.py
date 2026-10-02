from collections.abc import Iterator

import numpy as np
from piper import PiperVoice, SynthesisConfig

from helomi_foundation import on_mount, on_unmount

from ...audio import AudioFormat, RawAudio
from ..domain import SynthesisChunk, SynthesisRequest
from ..ports import SynthesisAdapter
from .config import PiperProfile, PiperSettings


class PiperAdapter(SynthesisAdapter[PiperSettings, PiperProfile]):
    def __init__(self, settings, profiles):
        super().__init__(settings, profiles)
        self._models: dict[str, PiperVoice] = {}

    def synthesize(
        self, request: SynthesisRequest
    ) -> Iterator[Exception | SynthesisChunk]:
        try:
            profile = self._profiles.get(request.profile_id, None)
            model = self._models.get(request.profile_id, None)
            text = request.raw_text

            if not profile or not model:
                self._logger.warning("No profile found for {}", request.profile_id)

            if not text or not profile or not model:
                yield StopIteration()
                return

            chunks = model.synthesize(
                text=text,
                include_alignments=False,
                syn_config=SynthesisConfig(
                    speaker_id=profile.speaker_id,
                    length_scale=profile.length_scale,
                    noise_scale=profile.noise_scale,
                    noise_w_scale=profile.noise_w_scale,
                    normalize_audio=self._settings.normalize_audio,
                    volume=self._settings.volume,
                ),
            )

            for chunk in chunks:
                samples = np.ascontiguousarray(
                    chunk.audio_float_array,
                    dtype=np.float32,
                )

                yield SynthesisChunk(
                    audio=RawAudio(
                        format=AudioFormat(
                            sample_rate=chunk.sample_rate,
                            channels=chunk.sample_channels,
                        ),
                        data=samples.tobytes(),
                    )
                )

            yield StopIteration()
        except Exception as error:
            yield error

    @on_mount()
    def _load_models(self):
        for profile_id, profile in self._profiles.items():
            self._logger.debug("Loading model: {}", profile.model_path.name)
            self._models[profile_id] = PiperVoice.load(
                model_path=profile.model_path,
                config_path=profile.config_path,
            )

    @on_unmount()
    def _release_models(self):
        self._models.clear()
