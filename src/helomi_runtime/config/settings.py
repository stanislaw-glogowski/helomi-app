from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import Field, PrivateAttr, field_validator

from helomi_foundation import ConfigFile, ConfigModel, PromptReader

from ..audio.config import AudioRouterSettings
from ..detection.config import DetectionSettings
from ..resources import ResourceCatalog
from ..synthesis.config import SynthesisSettings
from ..transcription.config import TranscriptionSettings


class Settings(ConfigModel, PromptReader):
    """Validated application settings loaded from the resource root."""

    _CONFIG_FILE: ClassVar[str] = "settings"

    audio: AudioRouterSettings
    detection: DetectionSettings
    transcription: TranscriptionSettings
    synthesis: SynthesisSettings
    app: dict[str, Any] = Field(default_factory=dict)

    @field_validator("app", mode="before")
    @classmethod
    def resolve_app_references(cls, data: Any) -> Any:
        return ConfigFile.resolve_references(data)

    _config_path: Path = PrivateAttr()
    _root_path: Path = PrivateAttr()
    _prompts: dict[str, str] = PrivateAttr()

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def prompts(self) -> dict[str, str]:
        return self._prompts

    @classmethod
    def load(cls, resources: ResourceCatalog) -> Self:
        root_path = resources.root_path
        config_path = cls._resolve_config_path(root_path / cls._CONFIG_FILE)
        data = ConfigFile.read_merged(
            root_path / cls._CONFIG_FILE, resolve_references=False
        )
        if data is None:
            raise ValueError(f"Settings file not found in {root_path}")

        if "application" in data:
            raise ValueError(f"Rename 'application' to 'app' in {config_path}")

        try:
            return cls.model_validate(
                data,
                context={
                    "config_path": config_path,
                    "root_path": root_path,
                    "prompts": cls._read_prompts(root_path),
                },
            )
        except ValueError as error:
            raise ValueError(f"Invalid settings in {config_path}: {error}") from error

    @classmethod
    def _resolve_config_path(cls, stem: Path) -> Path:
        for suffix in (".yml", ".yaml", ".json"):
            path = stem.with_suffix(suffix)
            if path.is_file():
                return path
        return stem

    def model_post_init(self, context: Any):
        if isinstance(context, dict):
            for key in ("config_path", "root_path", "prompts"):
                self._set_private_attr(key, context.get(key))
