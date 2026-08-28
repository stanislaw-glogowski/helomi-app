from collections.abc import Iterator
from typing import ClassVar

from huggingface_hub.utils import disable_progress_bars
from voxcpm import VoxCPM

from ...audio import AudioFormat, RawAudio
from ..domain import TTSChunk, TTSRequest
from ..ports import TTSAdapter
from .config import VoxCPM2Config, VoxCPM2Options


class VoxCPM2Adapter(TTSAdapter[VoxCPM2Config, VoxCPM2Options]):
    _AUDIO_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_48

    def __init__(self, config) -> None:
        super().__init__(config)
        self._model: VoxCPM | None = None

    def synthesize(
        self,
        request: TTSRequest,
        options: VoxCPM2Options,
    ) -> Iterator[Exception | TTSChunk]:
        try:
            model = self._require_model()

            stream = model.generate_streaming(
                text=request.text,
                reference_wav_path=str(options.ref_audio)
                if options.ref_audio
                else None,
                inference_timesteps=options.inference,
                cfg_value=options.cfg_value,
                min_len=options.min_len,
                max_len=options.max_len,
                normalize=options.normalize,
                denoise=options.denoise,
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
            cfg = self._config

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
