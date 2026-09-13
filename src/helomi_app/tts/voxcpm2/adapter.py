from collections.abc import Iterator
from typing import ClassVar

from huggingface_hub.utils import disable_progress_bars
from voxcpm import VoxCPM

from ...audio import AudioFormat, RawAudio
from ..domain import TTSChunk, TTSRequest
from ..ports import TTSAdapter
from .config import VoxCPM2Profile, VoxCPM2Settings


class VoxCPM2Adapter(TTSAdapter[VoxCPM2Settings, VoxCPM2Profile]):
    _AUDIO_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_48

    def __init__(self, settings, profiles) -> None:
        super().__init__(settings, profiles)
        self._model: VoxCPM | None = None

    def synthesize(self, request: TTSRequest) -> Iterator[Exception | TTSChunk]:
        try:
            profile = self._profiles.get(request.profile_id, None)

            if not profile:
                self._logger.warning("No profile found for {}", request.profile_id)
                yield StopIteration()
                return

            model = self._require_model()

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

            for chunk in stream:
                yield TTSChunk(
                    audio=RawAudio(
                        format=self._AUDIO_FORMAT,
                        data=chunk.tobytes(),
                    ),
                )
            yield StopIteration()
        except Exception as err:
            yield err

    def _do_open(self) -> None:
        with disable_progress_bars():
            cfg = self._settings

            self._logger.debug("Loading model: {}", cfg.model.id)
            self._model = VoxCPM.from_pretrained(
                str(cfg.model.path),
                load_denoiser=cfg.load_denoiser,
                local_files_only=True,
            )

    def _do_close(self) -> None:
        if self._model is None:
            return

    def _require_model(self) -> VoxCPM:
        if self._model is None:
            raise RuntimeError("VoxCPM2 model is not loaded")
        return self._model
