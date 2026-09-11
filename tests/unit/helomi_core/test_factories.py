from pathlib import Path
from unittest.mock import patch

from helomi_core.audio import get_audio_driver
from helomi_core.audio.config import AudioSettings
from helomi_core.stt import get_stt_adapter
from helomi_core.stt.config import STTSettings
from helomi_core.tts import get_tts_adapter
from helomi_core.tts.config import TTSSettings
from helomi_core.turn import get_turn_adapter
from helomi_core.turn.config import TurnSettings
from helomi_core.vad import get_vad_adapter
from helomi_core.vad.config import VADSettings
from helomi_core.wakeword import get_wakeword_adapter
from helomi_core.wakeword.config import WakeWordProfile, WakeWordSettings


def test_get_audio_driver_factory():
    """Verify get_audio_driver instantiates adapter from settings."""
    settings = AudioSettings.model_validate({"adapter": "avfaudio", "avfaudio": {}})
    with patch("helomi_core.audio.avfaudio.driver.AVFAudioDriver") as mock_driver:
        get_audio_driver(settings)
        assert mock_driver.called


def test_get_turn_adapter_factory():
    """Verify get_turn_adapter instantiates adapter from settings."""
    settings = TurnSettings.model_validate({"adapter": "smart_turn", "smart_turn": {}})
    with patch("helomi_core.turn.smart_turn.adapter.SmartTurnAdapter") as mock_turn:
        get_turn_adapter(settings)
        assert mock_turn.called


def test_get_vad_adapter_factory(tmp_path: Path):
    """Verify get_vad_adapter instantiates MLX and ONNX adapters from settings."""
    mlx_settings = VADSettings.model_validate(
        {"adapter": "silero_vad", "silero_vad": {"engine": "mlx"}}
    )
    with patch(
        "helomi_core.vad.silero_vad.mlx_adapter.SileroVADMLXAdapter"
    ) as mock_mlx:
        get_vad_adapter(mlx_settings)
        assert mock_mlx.called

    onnx_file = tmp_path / "model.onnx"
    onnx_file.touch()
    onnx_settings = VADSettings.model_validate(
        {
            "adapter": "silero_vad",
            "silero_vad": {"engine": "onnx", "model_path": str(onnx_file)},
        }
    )
    with patch(
        "helomi_core.vad.silero_vad.onnx_adapter.SileroVADONNXAdapter"
    ) as mock_onnx:
        get_vad_adapter(onnx_settings)
        assert mock_onnx.called


def test_get_wakeword_adapter_factory(tmp_path: Path):
    """Verify get_wakeword_adapter instantiates adapter from settings and profiles."""
    emb = tmp_path / "emb.onnx"
    emb.touch()
    mel = tmp_path / "mel.onnx"
    mel.touch()
    mod = tmp_path / "mod.onnx"
    mod.touch()

    settings = WakeWordSettings.model_validate(
        {
            "adapter": "openwakeword",
            "openwakeword": {
                "embedding_path": str(emb),
                "melspec_path": str(mel),
            },
        }
    )
    profiles = {
        "p1": WakeWordProfile.model_validate(
            {"adapter": "openwakeword", "openwakeword": {"model_path": str(mod)}}
        )
    }

    with patch(
        "helomi_core.wakeword.openwakeword.adapter.OpenWakeWordAdapter"
    ) as mock_ww:
        get_wakeword_adapter(settings, profiles)
        assert mock_ww.called


def test_get_stt_adapter_factories():
    """Verify get_stt_adapter instantiates parakeet and whisper adapters."""
    parakeet_settings = STTSettings.model_validate(
        {"adapter": "parakeet", "parakeet": {}}
    )
    with patch("helomi_core.stt.parakeet.adapter.ParakeetAdapter") as mock_para:
        get_stt_adapter(parakeet_settings)
        assert mock_para.called

    whisper_settings = STTSettings.model_validate({"adapter": "whisper", "whisper": {}})
    with patch("helomi_core.stt.whisper.adapter.WhisperAdapter") as mock_whisp:
        get_stt_adapter(whisper_settings)
        assert mock_whisp.called


def test_get_tts_adapter_factories():
    """Verify get_tts_adapter instantiates supertonic and voxcpm2 adapters."""
    vox_settings = TTSSettings.model_validate({"adapter": "voxcpm2", "voxcpm2": {}})
    with patch("helomi_core.tts.voxcpm2.adapter.VoxCPM2Adapter") as mock_vox:
        get_tts_adapter(vox_settings)
        assert mock_vox.called

    super_settings = TTSSettings.model_validate(
        {"adapter": "supertonic", "supertonic": {}}
    )
    with patch("helomi_core.tts.supertonic.adapter.SupertonicAdapter") as mock_sup:
        get_tts_adapter(super_settings)
        assert mock_sup.called
