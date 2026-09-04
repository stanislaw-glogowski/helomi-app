from pathlib import Path
from typing import Any

import pytest
import yaml

from helomi_core.audio import AudioChunk, AudioFormat, RawAudio
from tests.fixtures.audio import (
    create_audio_chunk,
    create_noise_raw_audio,
    create_raw_audio,
    create_silence_raw_audio,
)
from tests.fixtures.mocks import (
    MockAudioDriver,
    MockResourceCatalog,
    MockSTTAdapter,
    MockTTSAdapter,
    MockTurnAdapter,
    MockVADAdapter,
    MockWakeWordAdapter,
)


@pytest.fixture
def audio_format_16k() -> AudioFormat:
    """Standard 16kHz mono audio format."""
    return AudioFormat.MONO_16


@pytest.fixture
def sample_raw_audio() -> RawAudio:
    """Sample raw audio chunk (0.1s at 16kHz)."""
    return create_raw_audio(sample_rate=16000, duration=0.1)


@pytest.fixture
def sample_silence_raw_audio() -> RawAudio:
    """Sample silence raw audio chunk (0.1s at 16kHz)."""
    return create_silence_raw_audio(sample_rate=16000, duration=0.1)


@pytest.fixture
def sample_noise_raw_audio() -> RawAudio:
    """Sample noise raw audio chunk (0.1s at 16kHz)."""
    return create_noise_raw_audio(sample_rate=16000, duration=0.1)


@pytest.fixture
def sample_audio_chunk() -> AudioChunk:
    """Sample audio chunk (0.1s at 16kHz)."""
    return create_audio_chunk(sample_rate=16000, duration=0.1)


@pytest.fixture
def sample_settings_dict(tmp_path: Path) -> dict[str, Any]:
    """Sample settings dictionary for runtime validation."""
    emb_file = tmp_path / "embedding.onnx"
    emb_file.touch()
    mel_file = tmp_path / "melspec.onnx"
    mel_file.touch()

    return {
        "profile": {
            "default": "default",
        },
        "audio": {
            "adapter": "avfaudio",
            "avfaudio": {},
        },
        "stt": {
            "adapter": "parakeet",
            "parakeet": {},
        },
        "tts": {
            "adapter": "voxcpm2",
            "voxcpm2": {},
        },
        "turn": {
            "adapter": "smart_turn",
            "smart_turn": {},
        },
        "vad": {
            "adapter": "silero_vad",
            "silero_vad": {},
        },
        "wakeword": {
            "adapter": "openwakeword",
            "openwakeword": {
                "embedding_path": str(emb_file),
                "melspec_path": str(mel_file),
            },
        },
        "root_path": tmp_path,
    }


@pytest.fixture
def sample_profiles_dict(tmp_path: Path) -> dict[str, dict[str, Any]]:
    """Sample profiles dictionary for runtime validation."""
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    return {
        "default": {
            "name": "Default",
            "stt": {
                "adapter": "parakeet",
                "parakeet": {},
            },
            "tts": {
                "adapter": "voxcpm2",
                "voxcpm2": {},
            },
            "wakeword": {
                "adapter": "openwakeword",
                "openwakeword": {
                    "model_path": str(model_file),
                },
            },
            "id": "default",
            "root_path": tmp_path / "profiles" / "default",
        }
    }


@pytest.fixture
def mock_catalog(
    temp_helomi_store: Path,
) -> MockResourceCatalog:
    """Mock resource catalog populated with sample settings and profiles."""
    return MockResourceCatalog(
        root_path=temp_helomi_store,
    )


@pytest.fixture
def mock_audio_driver() -> MockAudioDriver:
    """Mock audio driver instance."""
    return MockAudioDriver()


@pytest.fixture
def mock_vad_adapter() -> MockVADAdapter:
    """Mock VAD adapter instance."""
    return MockVADAdapter()


@pytest.fixture
def mock_wakeword_adapter() -> MockWakeWordAdapter:
    """Mock WakeWord adapter instance."""
    return MockWakeWordAdapter()


@pytest.fixture
def mock_turn_adapter() -> MockTurnAdapter:
    """Mock Turn adapter instance."""
    return MockTurnAdapter()


@pytest.fixture
def mock_stt_adapter() -> MockSTTAdapter:
    """Mock STT adapter instance."""
    return MockSTTAdapter()


@pytest.fixture
def mock_tts_adapter() -> MockTTSAdapter:
    """Mock TTS adapter instance."""
    return MockTTSAdapter()


@pytest.fixture
def temp_helomi_store(tmp_path: Path) -> Path:
    """Create a temporary .helomi directory tree with valid YAML config files."""
    store_dir = tmp_path / ".helomi"
    store_dir.mkdir(parents=True)

    models_dir = store_dir / "models"
    models_dir.mkdir()
    emb_file = models_dir / "embedding_model.onnx"
    emb_file.touch()
    mel_file = models_dir / "melspectrogram.onnx"
    mel_file.touch()

    settings_file = store_dir / "settings.yml"
    settings_data = {
        "profile": {
            "default": "default",
        },
        "audio": {
            "adapter": "avfaudio",
            "avfaudio": {},
        },
        "stt": {
            "adapter": "parakeet",
            "parakeet": {},
        },
        "tts": {
            "adapter": "voxcpm2",
            "voxcpm2": {},
        },
        "turn": {
            "adapter": "smart_turn",
            "smart_turn": {},
        },
        "vad": {
            "adapter": "silero_vad",
            "silero_vad": {},
        },
        "wakeword": {
            "adapter": "openwakeword",
            "openwakeword": {
                "embedding_path": "path://models/embedding_model.onnx",
                "melspec_path": "path://models/melspectrogram.onnx",
            },
        },
    }
    settings_file.write_text(yaml.safe_dump(settings_data), encoding="utf-8")

    profiles_dir = store_dir / "profiles"
    default_profile_dir = profiles_dir / "default"
    default_profile_dir.mkdir(parents=True)
    default_models = default_profile_dir / "models"
    default_models.mkdir()
    default_model_file = default_models / "model.onnx"
    default_model_file.touch()

    default_profile_file = default_profile_dir / "profile.yml"
    default_profile_data = {
        "name": "Default Profile",
        "stt": {
            "adapter": "parakeet",
            "parakeet": {},
        },
        "tts": {
            "adapter": "voxcpm2",
            "voxcpm2": {},
        },
        "wakeword": {
            "adapter": "openwakeword",
            "openwakeword": {
                "model_path": "path://models/model.onnx",
            },
        },
    }
    default_profile_file.write_text(
        yaml.safe_dump(default_profile_data), encoding="utf-8"
    )

    return store_dir
