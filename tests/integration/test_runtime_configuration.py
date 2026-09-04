from pathlib import Path

import yaml

from helomi_app.resources import UserData
from helomi_app.runtime import Runtime


def test_runtime_configuration_with_local_store(tmp_path: Path):
    """Integration test: UserData directory structure -> Runtime initialization."""
    store_dir = tmp_path / ".helomi"
    store_dir.mkdir(parents=True)

    models_dir = store_dir / "models"
    models_dir.mkdir()
    emb_file = models_dir / "embedding_model.onnx"
    emb_file.touch()
    mel_file = models_dir / "melspectrogram.onnx"
    mel_file.touch()

    # 1. Create base settings.yml
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
    (store_dir / "settings.yml").write_text(
        yaml.safe_dump(settings_data), encoding="utf-8"
    )

    # 2. Create settings.override.yml (overriding default profile)
    settings_override = {
        "profile": {
            "default": "gizmo",
        }
    }
    (store_dir / "settings.override.yml").write_text(
        yaml.safe_dump(settings_override), encoding="utf-8"
    )

    # 3. Create profiles directory with default and gizmo profiles
    profiles_dir = store_dir / "profiles"

    # Default profile
    default_dir = profiles_dir / "default"
    default_dir.mkdir(parents=True)
    default_model = default_dir / "model.onnx"
    default_model.touch()
    default_data = {
        "name": "Default Assistant",
        "stt": {"adapter": "parakeet", "parakeet": {}},
        "tts": {"adapter": "voxcpm2", "voxcpm2": {}},
        "wakeword": {
            "adapter": "openwakeword",
            "openwakeword": {"model_path": "path://model.onnx"},
        },
    }
    (default_dir / "profile.yml").write_text(
        yaml.safe_dump(default_data), encoding="utf-8"
    )

    # Gizmo profile
    gizmo_dir = profiles_dir / "gizmo"
    gizmo_dir.mkdir(parents=True)
    gizmo_model = gizmo_dir / "model.onnx"
    gizmo_model.touch()
    gizmo_data = {
        "name": "Gizmo Robot",
        "stt": {"adapter": "parakeet", "parakeet": {}},
        "tts": {"adapter": "voxcpm2", "voxcpm2": {}},
        "wakeword": {
            "adapter": "openwakeword",
            "openwakeword": {"model_path": "path://model.onnx"},
        },
    }
    (gizmo_dir / "profile.yml").write_text(yaml.safe_dump(gizmo_data), encoding="utf-8")

    # 4. Initialize UserData and Runtime
    user_data = UserData(root_path=store_dir)
    runtime = Runtime(user_data)

    assert runtime.settings.profile.default == "gizmo"

    # Default profile lookup without argument resolves to default "gizmo"
    resolved_profile = runtime.profiles.get(None)
    assert resolved_profile.id == "gizmo"
    assert resolved_profile.name == "Gizmo Robot"

    # Explicit lookup of default profile
    default_prof = runtime.profiles.get("default")
    assert default_prof.id == "default"
    assert default_prof.name == "Default Assistant"
