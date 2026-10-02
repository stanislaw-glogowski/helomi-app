import re
from collections.abc import Generator, Iterator
from typing import Any, cast

import numpy as np
from huggingface_hub.utils import disable_progress_bars
from voxcpm import VoxCPM
from voxcpm.model.voxcpm2 import VoxCPM2Model

from helomi_foundation import on_mount, on_unmount

from ...audio import AudioFormat, RawAudio
from ..domain import SynthesisChunk, SynthesisRequest
from ..ports import SynthesisAdapter
from .config import VoxCPM2Profile, VoxCPM2Settings


class VoxCPM2Adapter(SynthesisAdapter[VoxCPM2Settings, VoxCPM2Profile]):
    def __init__(self, settings, profiles):
        super().__init__(settings, profiles)
        self._model: VoxCPM | None = None
        self._prompt_caches: dict[str, dict[str, Any]] = {}

    def synthesize(
        self, request: SynthesisRequest
    ) -> Iterator[Exception | SynthesisChunk]:
        try:
            profile = self._profiles.get(request.profile_id, None)

            if not profile:
                self._logger.warning("No profile found for {}", request.profile_id)
                yield StopIteration()
                return

            model = self._require_model()

            audio_format = AudioFormat(sample_rate=model.tts_model.sample_rate)
            stream = self._generate_stream(model, request, profile)
            try:
                for chunk in stream:
                    samples = np.ascontiguousarray(chunk, dtype=np.float32)
                    yield SynthesisChunk(
                        audio=RawAudio(format=audio_format, data=samples.tobytes()),
                    )
            finally:
                stream.close()
            yield StopIteration()
        except Exception as error:
            yield error

    def _generate_stream(
        self, model: VoxCPM, request: SynthesisRequest, profile: VoxCPM2Profile
    ) -> Generator[Any]:
        if not profile.ref_audio or profile.normalize or profile.denoise:
            stream = model.generate_streaming(
                text=request.text,
                reference_wav_path=str(profile.ref_audio)
                if profile.ref_audio
                else None,
                inference_timesteps=profile.inference,
                cfg_value=profile.cfg_value,
                min_len=profile.min_len,
                max_len=profile.max_len,
                normalize=profile.normalize,
                denoise=profile.denoise,
                retry_badcase=False,
            )
            try:
                yield from stream
            finally:
                stream.close()
            return

        synthesis_model = cast(VoxCPM2Model, model.tts_model)
        if request.profile_id not in self._prompt_caches:
            self._prompt_caches[request.profile_id] = (
                synthesis_model.build_prompt_cache(
                    reference_wav_path=str(profile.ref_audio)
                )
            )
        # Match VoxCPM's public wrapper preprocessing without splitting the text.
        text = re.sub(r"\s+", " ", request.text.replace("\n", " "))
        stream = synthesis_model.generate_with_prompt_cache_streaming(
            target_text=text,
            prompt_cache=self._prompt_caches[request.profile_id],
            inference_timesteps=profile.inference,
            cfg_value=profile.cfg_value,
            min_len=profile.min_len,
            max_len=profile.max_len,
            retry_badcase=False,
        )
        try:
            for waveform, _, _ in stream:
                yield waveform.squeeze(0).cpu().numpy()
        finally:
            stream.close()

    @on_mount()
    def _load_model(self):
        with disable_progress_bars():
            settings = self._settings

            self._logger.debug("Loading model: {}", settings.model.id)
            self._model = VoxCPM.from_pretrained(
                str(settings.model.path),
                load_denoiser=settings.load_denoiser,
                local_files_only=True,
            )

    @on_unmount()
    def _release_model(self):
        self._prompt_caches.clear()
        self._model = None

    def _require_model(self) -> VoxCPM:
        if self._model is None:
            raise RuntimeError("VoxCPM2 model is not loaded")
        return self._model
