import os
from pathlib import Path
from unittest.mock import patch

import pytest

from helomi_core.resources.store import LocalStore


def test_local_store_explicit_root_path(temp_helomi_store: Path):
    """Verify LocalStore uses explicitly provided root path."""
    store = LocalStore(root_path=temp_helomi_store)
    assert store.root_path == temp_helomi_store

    settings = store.read_settings_data()
    assert settings["profile"]["default"] == "default"

    profiles = store.read_profiles_data()
    assert "default" in profiles
    assert profiles["default"]["name"] == "Default Profile"


def test_local_store_home_env_var(tmp_path: Path):
    """Verify LocalStore honors HELOMI_HOME environment variable."""
    env_dir = tmp_path / "custom_home"
    env_dir.mkdir()

    with patch.dict(os.environ, {"HELOMI_HOME": str(env_dir)}):
        store = LocalStore()
        assert store.root_path == env_dir


def test_local_store_missing_settings_raises_error(tmp_path: Path):
    """Verify read_settings_data raises error when settings file is missing."""
    empty_dir = tmp_path / "empty_store"
    empty_dir.mkdir()
    store = LocalStore(root_path=empty_dir)

    with pytest.raises(FileNotFoundError, match="No settings file found"):
        store.read_settings_data()


def test_local_store_missing_profiles_dir_raises_error(tmp_path: Path):
    """Verify read_profiles_data raises error when profiles dir is absent."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    store = LocalStore(root_path=store_dir)

    with pytest.raises(FileNotFoundError, match="Profiles directory does not exist"):
        store.read_profiles_data()


def test_local_store_profiles_with_defaults_and_disabled(tmp_path: Path):
    """Verify read_profiles_data merges defaults and skips disabled profiles."""
    import yaml

    store_dir = tmp_path / ".helomi"
    store_dir.mkdir()
    profiles_dir = store_dir / "profiles"
    profiles_dir.mkdir()

    # 1. defaults.yml
    defaults_file = profiles_dir / "defaults.yml"
    defaults_data = {
        "stt": {"adapter": "parakeet", "parakeet": {"language": "en"}},
        "tts": {"adapter": "voxcpm2", "voxcpm2": {}},
    }
    defaults_file.write_text(yaml.safe_dump(defaults_data), encoding="utf-8")

    # 2. active profile
    p1_dir = profiles_dir / "active_p"
    p1_dir.mkdir()
    p1_data = {
        "name": "Active Profile",
        "wakeword": {"adapter": "openwakeword", "openwakeword": {}},
    }
    (p1_dir / "profile.yml").write_text(yaml.safe_dump(p1_data), encoding="utf-8")

    # 3. disabled profile
    p2_dir = profiles_dir / "disabled_p"
    p2_dir.mkdir()
    p2_data = {
        "name": "Disabled Profile",
        "disabled": True,
    }
    (p2_dir / "profile.yml").write_text(yaml.safe_dump(p2_data), encoding="utf-8")

    # 4. directory without profile.yml
    empty_p_dir = profiles_dir / "empty_dir"
    empty_p_dir.mkdir()

    store = LocalStore(root_path=store_dir)
    profiles = store.read_profiles_data()

    assert "active_p" in profiles
    assert "disabled_p" not in profiles
    assert "empty_dir" not in profiles
    assert profiles["active_p"]["name"] == "Active Profile"
    assert profiles["active_p"]["stt"]["adapter"] == "parakeet"
    assert profiles["active_p"]["id"] == "active_p"


def test_local_store_empty_profiles_dir_raises_error(tmp_path: Path):
    """Verify read_profiles_data raises error when profiles dir is empty."""
    store_dir = tmp_path / ".helomi"
    store_dir.mkdir()
    profiles_dir = store_dir / "profiles"
    profiles_dir.mkdir()

    store = LocalStore(root_path=store_dir)
    with pytest.raises(FileNotFoundError, match="No settings file found"):
        store.read_profiles_data()
