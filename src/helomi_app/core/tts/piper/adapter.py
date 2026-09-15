from collections.abc import Iterator

import numpy as np
from piper import PiperVoice, SynthesisConfig

from ...audio import AudioFormat, RawAudio
from ..domain import TTSChunk, TTSRequest
from ..ports import TTSAdapter
from .config import PiperProfile, PiperSettings


class PiperAdapter(TTSAdapter[PiperSettings, PiperProfile]):
    def __init__(self, settings, profiles) -> None:
        super().__init__(settings, profiles)
        self._models: dict[str, PiperVoice] = {}

    def synthesize(self, request: TTSRequest) -> Iterator[Exception | TTSChunk]:
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

                yield TTSChunk(
                    audio=RawAudio(
                        format=AudioFormat(
                            sample_rate=chunk.sample_rate,
                            channels=chunk.sample_channels,
                        ),
                        data=samples.tobytes(),
                    )
                )

            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open(self) -> None:
        for profile_id, profile in self._profiles.items():
            self._logger.debug("Loading model: {}", profile.model_path.name)
            self._models[profile_id] = PiperVoice.load(
                model_path=profile.model_path,
                config_path=profile.config_path,
            )

    def _do_close(self) -> None:
        self._models.clear()
