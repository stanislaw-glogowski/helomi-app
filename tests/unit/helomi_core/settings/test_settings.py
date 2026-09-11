from pathlib import Path

import pytest

from helomi_core.resources.user import UserData
from helomi_core.settings import Settings


def test_settings_load_success(temp_helomi_store: Path) -> None:
    resources = UserData(temp_helomi_store)
    settings = Settings.load(resources)
    assert settings.profile.default == "alexa"
    assert settings.audio.adapter == "avfaudio"
    assert settings.root_path == temp_helomi_store


def test_settings_load_missing_raises_error(tmp_path: Path) -> None:
    resources = UserData(tmp_path)
    with pytest.raises(ValueError, match="No settings file found"):
        Settings.load(resources)


def test_settings_override(tmp_path: Path) -> None:
    store = tmp_path / "resources"
    store.mkdir()
    (store / "settings.yml").write_text(
        "audio:\n  adapter: avfaudio\n", encoding="utf-8"
    )
    (store / "settings.override.yml").write_text(
        "profile:\n  default: custom\n", encoding="utf-8"
    )
    resources = UserData(store)
    settings = Settings.load(resources)
    assert settings.audio.adapter == "avfaudio"
    assert settings.profile.default == "custom"
