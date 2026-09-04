import json
from enum import IntEnum, auto
from pathlib import Path
from typing import Any, ClassVar

import yaml

from ..collections import DeepMergeDict
from .file import AbstractFile


class ConfigKind(IntEnum):
    YAML = auto()
    JSON = auto()


class ConfigFile(AbstractFile):
    _OVERRIDE_POSTFIX: ClassVar[str] = ".override"
    _SUFFIXES: ClassVar[list[str]] = [".yml", ".yaml", ".json"]

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        match path.suffix:
            case ".yaml" | ".yml":
                self._kind = ConfigKind.YAML
            case ".json":
                self._kind = ConfigKind.JSON
            case _:
                raise ValueError(f"Unsupported file type: {path.suffix}")

    @classmethod
    def read_configs(cls, path: Path) -> DeepMergeDict | None:
        root_path = path.parent
        file_name = path.name

        files = [
            cls(file)
            for ext in cls._SUFFIXES
            if (file := root_path / (file_name + ext)).exists()
        ]
        if not files:
            return None

        for ext in cls._SUFFIXES:
            if (file := root_path / (file_name + cls._OVERRIDE_POSTFIX + ext)).exists():
                files.append(cls(file))

        data = DeepMergeDict({})

        for file in files:
            data = data.merged_with(file.read())

        return data

    @classmethod
    def is_config(cls, path: Path) -> bool:
        return path.is_file() and path.suffix in cls._SUFFIXES

    @property
    def kind(self) -> ConfigKind:
        return self._kind

    def read(self) -> DeepMergeDict:
        with self.path.open("r", encoding="utf-8") as f:
            data: Any
            match self._kind:
                case ConfigKind.YAML:
                    data = yaml.safe_load(f)
                case ConfigKind.JSON:
                    data = json.load(f)
            prepared = self._prepare_data(None, data)
            return (
                DeepMergeDict(prepared)
                if isinstance(prepared, dict)
                else DeepMergeDict({})
            )

    def write(self, data: DeepMergeDict) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            match self._kind:
                case ConfigKind.YAML:
                    yaml.safe_dump(
                        dict(data),
                        f,
                        sort_keys=False,
                        allow_unicode=True,
                    )
                case ConfigKind.JSON:
                    json.dump(
                        data,
                        f,
                        indent=4,
                        ensure_ascii=False,
                    )

    def _prepare_data(self, key: str | None, value: Any) -> Any:
        match key, value:
            case _, dict():
                return {k: self._prepare_data(k, v) for k, v in value.items()}
            case _, list():
                return [self._prepare_data(None, v) for v in value]
            case str(), str() if (parts := value.split("://", 1)) and len(parts) == 2:
                prefix, v = parts
                match prefix:
                    case "path":
                        return self._path.parent / v

        return value
