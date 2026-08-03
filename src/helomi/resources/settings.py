from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from helomi.common.validation import ConfigModel
from helomi.conversation.config import ConversationSettings
from helomi.speech.config import SpeechSettings


class Settings(ConfigModel):
    default_profile: str | None = Field(default=None, min_length=1)
    conversation: ConversationSettings = ConversationSettings()
    speech: SpeechSettings = SpeechSettings()

    @staticmethod
    def load_from_file(path: Path) -> Settings:
        data = _load_mapping(path)
        settings = Settings.model_validate(_normalize_legacy_settings(data))
        return settings

    @staticmethod
    def load_from_files(
        default_path: Path,
        override_path: Path | None = None,
    ) -> Settings:
        data = _load_mapping(default_path)
        if override_path is not None and override_path.is_file():
            data = _merge_mappings(data, _load_mapping(override_path))
        return Settings.model_validate(_normalize_legacy_settings(data))


def _load_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Settings configuration must be a mapping: {path}")
    return data


def _merge_mappings(
    default: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(default)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_mappings(existing, value)
        else:
            merged[key] = value
    return merged


def _normalize_legacy_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Ignore the removed classifier toggle in existing local overrides."""
    normalized = dict(data)
    conversation = normalized.get("conversation")
    if isinstance(conversation, dict) and "classify_ambiguous" in conversation:
        normalized["conversation"] = {
            key: value
            for key, value in conversation.items()
            if key != "classify_ambiguous"
        }
    return normalized


class SettingsStore(ABC):
    _SETTINGS_FILE = "settings.yml"
    _SETTINGS_OVERRIDE_FILE = "settings.override.yml"

    @abstractmethod
    def load_settings(self) -> Settings:
        raise NotImplementedError
