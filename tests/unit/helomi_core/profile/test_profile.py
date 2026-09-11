from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from helomi_core.profile import Profile, ProfileCatalog
from helomi_core.profile.config import ProfileSettings
from helomi_core.resources.user import UserData
from helomi_core.settings import Settings


def test_profile_catalog_load(temp_helomi_store: Path) -> None:
    resources = UserData(temp_helomi_store)
    settings = Settings.load(resources)
    catalog = ProfileCatalog.load(settings, resources)

    assert len(catalog) == 1
    assert next(iter(catalog)).id == "alexa"

    default_prof = catalog.get(None)
    assert default_prof.id == "alexa"
    assert default_prof.name == "Alexa"
    assert default_prof.root_path == temp_helomi_store / "profiles" / "alexa"

    prof = catalog.get("alexa")
    assert prof is default_prof

    assert catalog.get("unknown", throw_on_not_found=False) is None

    with pytest.raises(KeyError, match="Profile not found: unknown"):
        catalog.get("unknown")


def test_profile_catalog_defaults_merging_and_filtering(tmp_path: Path) -> None:
    store = tmp_path / "resources"
    store.mkdir()
    settings_file = store / "settings.yml"
    settings_file.write_text(
        yaml.safe_dump(
            {
                "profile": {"default": "active"},
                "audio": {"adapter": "avfaudio"},
                "stt": {"adapter": "parakeet"},
                "tts": {"adapter": "voxcpm2"},
                "turn": {"adapter": "smart_turn"},
                "vad": {"adapter": "silero_vad"},
                "wakeword": {"adapter": "openwakeword"},
            }
        ),
        encoding="utf-8",
    )

    profiles_dir = store / "profiles"
    profiles_dir.mkdir()

    # defaults.yml
    (profiles_dir / "defaults.yml").write_text(
        yaml.safe_dump(
            {
                "stt": {"adapter": "parakeet", "parakeet": {}},
                "tts": {"adapter": "voxcpm2", "voxcpm2": {}},
                "wakeword": {"adapter": "openwakeword", "openwakeword": {}},
            }
        ),
        encoding="utf-8",
    )

    # 1. active profile
    active_dir = profiles_dir / "active"
    active_dir.mkdir()
    (active_dir / "profile.yml").write_text(
        yaml.safe_dump({"name": "Active Profile"}),
        encoding="utf-8",
    )

    # 2. disabled profile
    disabled_dir = profiles_dir / "disabled"
    disabled_dir.mkdir()
    (disabled_dir / "profile.yml").write_text(
        yaml.safe_dump({"name": "Disabled Profile", "disabled": True}),
        encoding="utf-8",
    )

    # 3. empty directory (no profile.yml)
    empty_dir = profiles_dir / "empty"
    empty_dir.mkdir()

    resources = UserData(store)
    settings = Settings.load(resources)
    catalog = ProfileCatalog.load(settings, resources)

    assert len(catalog) == 1
    assert "active" in [p.id for p in catalog]
    assert "disabled" not in [p.id for p in catalog]


def test_profile_settings_defaults() -> None:
    ps = ProfileSettings()
    assert ps.default == Profile.DEFAULT_ID


def test_profile_with_room_voice_path(tmp_path: Path) -> None:
    profile_dir = tmp_path / "default"
    profile_dir.mkdir()
    assets_dir = profile_dir / "assets"
    assets_dir.mkdir()
    wav_file = assets_dir / "hospital_room_voice.wav"
    wav_file.write_bytes(b"RIFFdummywav")

    (profile_dir / "profile.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Default",
                "audio": {
                    "room_voice_path": "path://assets/hospital_room_voice.wav",
                },
                "stt": {"adapter": "parakeet", "parakeet": {}},
                "tts": {"adapter": "voxcpm2", "voxcpm2": {}},
            }
        ),
        encoding="utf-8",
    )

    from helomi_common import DeepMergeDict

    profile = Profile.load(
        root_path=profile_dir,
        settings_data=DeepMergeDict(
            {
                "stt": {"adapter": "parakeet"},
                "tts": {"adapter": "voxcpm2"},
                "wakeword": {"adapter": "openwakeword"},
            }
        ),
    )
    assert profile is not None
    assert profile.name == "Default"
    assert profile.audio.room_voice_path == wav_file


def test_profile_emoji_validation() -> None:
    # Valid single emoji
    p1 = Profile(name="Test1", emoji="👩🏻")
    assert p1.emoji == "👩🏻"

    p2 = Profile(name="Test2", emoji="🦆")
    assert p2.emoji == "🦆"

    # None and empty string resolve to None
    p3 = Profile(name="Test3", emoji=None)
    assert p3.emoji is None

    p4 = Profile(name="Test4", emoji="")
    assert p4.emoji is None

    # Invalid non-emoji string raises ValueError
    with pytest.raises(ValueError, match="Input should be a single emoji"):
        Profile(name="Test5", emoji="not_an_emoji")


def test_profile_readonly_field() -> None:
    p_default = Profile(name="Test")
    assert p_default.readonly is False

    p_readonly = Profile(name="Test Readonly", readonly=True)
    assert p_readonly.readonly is True


def test_profile_catalog_get_not_found(mock_catalog) -> None:
    from helomi_core.profile import ProfileCatalog
    from helomi_core.settings import Settings

    settings = Settings.load(mock_catalog)
    catalog = ProfileCatalog.load(settings, mock_catalog)

    assert catalog.get("non_existent", throw_on_not_found=False) is None
    with pytest.raises(KeyError, match="Profile not found: non_existent"):
        catalog.get("non_existent", throw_on_not_found=True)


def test_profile_reactions() -> None:
    from helomi_core.profile import ReactionKind

    # Profile with multiple reactions
    p1 = Profile(
        name="Test",
        reactions={
            ReactionKind.GREETING: ["Tak?", "Słucham?"],
            ReactionKind.INTERRUPTED: "Czekam...",
        },
    )
    assert p1.reactions[ReactionKind.GREETING] == ["Tak?", "Słucham?"]
    assert p1.reactions[ReactionKind.INTERRUPTED] == ["Czekam..."]
    assert p1.get_reaction(ReactionKind.GREETING) in ("Tak?", "Słucham?")
    assert p1.get_reaction(ReactionKind.INTERRUPTED) == "Czekam..."

    # Empty / None reactions
    p2 = Profile(name="Empty", reactions={ReactionKind.GREETING: []})
    assert p2.get_reaction(ReactionKind.GREETING) is None
    assert p2.get_reaction(ReactionKind.INTERRUPTED) is None

    # Non-dict reactions passes through to pydantic validator
    with pytest.raises(ValidationError):
        Profile.model_validate({"name": "Invalid", "reactions": 123})
