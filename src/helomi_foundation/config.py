import json
import os
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Any, ClassVar

import yaml

from .collections import DeepMergeDict
from .files import PathFile


@dataclass(frozen=True, slots=True)
class ConfigReference:
    value: str
    source: Path
    key_path: str


class ConfigFormat(StrEnum):
    YAML = auto()
    JSON = auto()


class ConfigFile(PathFile):
    """Read YAML or JSON configuration with one optional override."""

    _OVERRIDE_POSTFIX: ClassVar[str] = ".override"
    _SUFFIXES = (".yml", ".yaml", ".json")

    def __init__(self, path: Path):
        super().__init__(path)
        match self.path.suffix:
            case ".yaml" | ".yml":
                self._kind = ConfigFormat.YAML
            case ".json":
                self._kind = ConfigFormat.JSON
            case suffix:
                raise ValueError(f"Unsupported configuration file type: {suffix}")

    @classmethod
    def read_merged(
        cls, path: Path, *, resolve_references: bool = True
    ) -> DeepMergeDict | None:
        base_files = cls._find_candidates(path)
        if not base_files:
            return None
        if len(base_files) > 1:
            names = ", ".join(str(file) for file in base_files)
            raise ValueError(f"Multiple configuration files found: {names}")

        base_path = base_files[0]
        override_files = [
            candidate
            for suffix in cls._SUFFIXES
            if (
                candidate := base_path.parent
                / f"{base_path.stem}{cls._OVERRIDE_POSTFIX}{suffix}"
            ).is_file()
        ]
        if len(override_files) > 1:
            names = ", ".join(str(file) for file in override_files)
            raise ValueError(f"Multiple override files found: {names}")

        data = cls(base_path).read(resolve_references=resolve_references)
        if override_files:
            data = data.merged_with(
                cls(override_files[0]).read(resolve_references=resolve_references)
            )
        return data

    @classmethod
    def _find_candidates(cls, path: Path) -> list[Path]:
        if path.suffix:
            return [path] if path.is_file() else []
        return [
            candidate
            for suffix in cls._SUFFIXES
            if (candidate := path.with_suffix(suffix)).is_file()
        ]

    @classmethod
    def is_config(cls, path: Path) -> bool:
        return path.is_file() and path.suffix in cls._SUFFIXES

    @property
    def kind(self) -> ConfigFormat:
        return self._kind

    def read(self, *, resolve_references: bool = True) -> DeepMergeDict:
        with self.path.open("r", encoding="utf-8") as stream:
            data: Any
            match self._kind:
                case ConfigFormat.YAML:
                    data = yaml.safe_load(stream)
                case ConfigFormat.JSON:
                    data = json.load(stream)

        if data is None:
            return DeepMergeDict()
        if not isinstance(data, dict):
            raise ValueError(f"Configuration root must be an object: {self.path}")
        return DeepMergeDict(
            self._resolve(data, key_path="", defer=not resolve_references)
        )

    def write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            match self._kind:
                case ConfigFormat.YAML:
                    yaml.safe_dump(
                        data,
                        stream,
                        sort_keys=False,
                        allow_unicode=True,
                    )
                case ConfigFormat.JSON:
                    json.dump(data, stream, indent=4, ensure_ascii=False)

    @classmethod
    def resolve_references(cls, value: Any) -> Any:
        """Resolve retained references against their original source files."""
        if isinstance(value, ConfigReference):
            return cls(value.source)._resolve(value.value, key_path=value.key_path)
        if isinstance(value, dict):
            return {key: cls.resolve_references(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls.resolve_references(item) for item in value]
        return value

    def _resolve(self, value: Any, *, key_path: str, defer: bool = False) -> Any:
        if isinstance(value, dict):
            return {
                key: self._resolve(
                    item,
                    key_path=f"{key_path}.{key}" if key_path else str(key),
                    defer=defer,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve(item, key_path=f"{key_path}[{index}]", defer=defer)
                for index, item in enumerate(value)
            ]
        if not isinstance(value, str) or "://" not in value:
            return value

        prefix, target = value.split("://", 1)
        if defer and prefix in {"env", "path"}:
            return ConfigReference(value, self.path, key_path)
        match prefix:
            case "path":
                return (self.path.parent / target).resolve()
            case "env":
                resolved = os.getenv(target)
                if resolved is None:
                    raise ValueError(
                        f"Missing environment variable {target!r} for "
                        f"{key_path!r} in {self.path}"
                    )
                return resolved
            case _:
                return value
