from pathlib import Path

from helomi_core.config import Profile, ProfileSettings, Settings
from helomi_core.wakeword import WakeWordProfile


def test_profile_settings_model():
    """Verify ProfileSettings parsing and default values."""
    settings = ProfileSettings()
    assert settings.default == "default"

    settings_custom = ProfileSettings(default="custom")
    assert settings_custom.default == "custom"


def test_profile_model_and_label_property(tmp_path: Path):
    """Verify Profile model instantiation, disabled default/custom, and label format."""
    profile = Profile(
        name="Assistant",
        id="assistant_v1",
        root_path=tmp_path,
    )
    assert profile.name == "Assistant"
    assert profile.id == "assistant_v1"
    assert profile.disabled is False
    assert profile.label == "Assistant(assistant_v1)"

    disabled_profile = Profile(
        name="Disabled",
        id="disabled_v1",
        disabled=True,
        root_path=tmp_path,
    )
    assert disabled_profile.disabled is True


def test_wakeword_profile_openwakeword_filtering(tmp_path: Path):
    """Verify filter_openwakeword removes openwakeword dict if model_path is not set."""
    mod = tmp_path / "model.onnx"
    mod.touch()

    # When model_path is present, openwakeword remains
    p1 = WakeWordProfile.model_validate(
        {"adapter": "openwakeword", "openwakeword": {"model_path": str(mod)}}
    )
    assert p1.openwakeword is not None

    # When model_path is missing or empty, openwakeword is popped
    p2 = WakeWordProfile.model_validate({"adapter": "openwakeword", "openwakeword": {}})
    assert p2.openwakeword is None

    # When input is non-dict
    p3 = WakeWordProfile.model_validate({"adapter": "openwakeword"})
    assert p3.openwakeword is None


def test_settings_model_validation(sample_settings_dict: dict):
    """Verify Settings model validates sample dictionary successfully."""
    settings = Settings.model_validate(sample_settings_dict)
    assert settings.profile.default == "default"
    assert settings.audio.adapter == "avfaudio"
    assert settings.stt.adapter == "parakeet"
    assert settings.tts.adapter == "voxcpm2"
    assert settings.turn.adapter == "smart_turn"
    assert settings.vad.adapter == "silero_vad"
    assert settings.wakeword.adapter == "openwakeword"
    assert settings.server.host == "127.0.0.1"
    assert settings.server.port == 4356
