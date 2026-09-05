from pathlib import Path

import pytest
import yaml

from helomi_core.config.profile import Profile, ProfileCatalog, ProfileSettings
from helomi_core.config.settings import Settings
from helomi_core.resources.user import UserData


def test_profile_catalog_load(temp_helomi_store: Path) -> None:
    resources = UserData(temp_helomi_store)
    settings = Settings.load(resources)
    catalog = ProfileCatalog.load(settings, resources)

    assert len(catalog) == 1
    assert next(iter(catalog)).id == "default"

    default_prof = catalog.get(None)
    assert default_prof.id == "default"
    assert default_prof.name == "Default Profile"
    assert default_prof.root_path == temp_helomi_store / "profiles" / "default"

    prof = catalog.get("default")
    assert prof is default_prof

    assert catalog.get("unknown", throw_on_not_found=False) is None

    with pytest.raises(KeyError, match="Profile not found: unknown"):
        catalog.get("unknown")


def test_profile_catalog_defaults_merging_and_filtering(tmp_path: Path) -> None:
    store = tmp_path / ".helomi"
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
