from pathlib import Path

import pytest
import yaml

from tests.fixtures.mocks import MockResourceCatalog


@pytest.fixture
def mock_catalog(
    temp_helomi_store: Path,
) -> MockResourceCatalog:
    """Mock resource catalog populated with sample settings and profiles."""
    return MockResourceCatalog(
        root_path=temp_helomi_store,
    )


@pytest.fixture
def temp_helomi_store(tmp_path: Path) -> Path:
    """Create a temporary resources directory tree with valid YAML config files."""
    store_dir = tmp_path / "resources"
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
            "default": "alexa",
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
    alexa_profile_dir = profiles_dir / "alexa"
    alexa_profile_dir.mkdir(parents=True)
    alexa_models = alexa_profile_dir / "models"
    alexa_models.mkdir()
    alexa_model_file = alexa_models / "model.onnx"
    alexa_model_file.touch()

    alexa_profile_file = alexa_profile_dir / "profile.yml"
    alexa_profile_data = {
        "name": "Alexa",
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
    alexa_profile_file.write_text(yaml.safe_dump(alexa_profile_data), encoding="utf-8")

    return store_dir
