from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import Field

from helomi.common.validation import ConfigModel
from helomi.conversation.config import ConversationSettings
from helomi.speech.config import SpeechSettings

from .configuration import load_mapping, merge_mappings


class ProfilesSettings(ConfigModel):
    default: str | None = Field(default=None, min_length=1)
    selected: str | None = Field(default=None, min_length=1)


class Settings(ConfigModel):
    language: str = Field(default="en-US", min_length=1)
    profiles: ProfilesSettings = ProfilesSettings()
    conversation: ConversationSettings = ConversationSettings()
    speech: SpeechSettings = SpeechSettings()

    @staticmethod
    def from_mapping(data: dict) -> Settings:
        return Settings.model_validate(_normalize_legacy_settings(data))

    @staticmethod
    def load_from_file(path: Path) -> Settings:
        data = load_mapping(path, label="Settings configuration")
        return Settings.from_mapping(data)

    @staticmethod
    def load_from_files(
        default_path: Path,
        override_path: Path | None = None,
    ) -> Settings:
        data = load_mapping(default_path, label="Settings configuration")
        if override_path is not None and override_path.is_file():
            data = merge_mappings(
                data,
                load_mapping(override_path, label="Settings override configuration"),
            )
        return Settings.from_mapping(data)

def _normalize_legacy_settings(data: dict) -> dict:
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
