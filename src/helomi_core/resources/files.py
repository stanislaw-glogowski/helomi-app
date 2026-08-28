import json
import shutil
import wave
from enum import IntEnum, auto
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml

from ..audio import AudioChunk, AudioFormat, RawAudio


class AbstractFile:
    _DEFAULT_SUFFIX: ClassVar[str] = ""
    _SUFFIXES: ClassVar[list[str]] = []

    def __init_subclass__(cls) -> None:
        if cls._SUFFIXES:
            cls._DEFAULT_SUFFIX = cls._SUFFIXES[0]

    def __init__(self, path: Path) -> None:
        self._path = path
        if not self._path.suffix and self._DEFAULT_SUFFIX:
            self._path = self._path.with_suffix(self._DEFAULT_SUFFIX)

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.exists() and self._path.is_file()

    def __str__(self) -> str:
        return str(self._path)

    def __repr__(self) -> str:
        return str(self)

    def as_dir(
        self,
        ensure: Literal["exists", "empty", None] = None,
    ) -> Path:
        path = self.path.with_suffix("")

        if ensure:
            if path.exists():
                if ensure == "empty":
                    shutil.rmtree(path)
            path.mkdir(parents=True)
        return path


class ConfigKind(IntEnum):
    YAML = auto()
    JSON = auto()


class ConfigData(dict[str, Any]):
    def extend(self, override: dict[str, Any]) -> ConfigData:
        return ConfigData(self._merge_data(self, override))

    @classmethod
    def _merge_data(cls, base: Any, override: Any) -> Any:
        if isinstance(base, dict) and isinstance(override, dict):
            result = base.copy()
            for key, value in override.items():
                result[key] = cls._merge_data(base.get(key), value)
            return result
        else:
            return override


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
    def read_configs(cls, path: Path, file_name: str) -> ConfigData | None:
        files = [
            cls(file)
            for ext in cls._SUFFIXES
            if (file := path / (file_name + ext)).exists()
        ]
        if not files:
            return None

        for ext in cls._SUFFIXES:
            if (file := path / (file_name + cls._OVERRIDE_POSTFIX + ext)).exists():
                files.append(cls(file))

        data = ConfigData({})

        for file in files:
            data = data.extend(file.read())

        data["root_path"] = path

        return data

    @classmethod
    def is_config(cls, path: Path) -> bool:
        return path.is_file() and path.suffix is cls._SUFFIXES

    @property
    def kind(self) -> ConfigKind:
        return self._kind

    def read(self) -> ConfigData:
        with self.path.open("r", encoding="utf-8") as f:
            data: ConfigData
            match self._kind:
                case ConfigKind.YAML:
                    data = yaml.safe_load(f)
                case ConfigKind.JSON:
                    data = json.load(f)
            return self._prepare_data(None, data)

    def write(self, data: ConfigData) -> None:
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
                        if (
                            (subparts := v.split("://", 1))
                            and len(subparts) == 2
                            and subparts[0] == "txt"
                        ):
                            path = self._path.parent / subparts[1]
                            return TextFile(path).read()
                        return self._path.parent / v
                    case "txt":
                        path = self._path.parent / v
                        return TextFile(path).read()

        return value


class TextFile(AbstractFile):
    _SUFFIXES: ClassVar[list[str]] = [".txt", ".md"]

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        self.path.write_text(content, encoding="utf-8")


class WAVFile(AbstractFile):
    _SUFFIXES: ClassVar[list[str]] = [".wav", ".wave"]

    def read(self) -> RawAudio:
        with wave.open(str(self.path), "rb") as f:
            return RawAudio(
                format=AudioFormat(
                    sample_rate=f.getframerate(),
                    channels=f.getnchannels(),
                ),
                data=f.readframes(f.getnframes()),
            )

    def write(self, audio: RawAudio | AudioChunk, normalize=False) -> None:
        with wave.open(str(self.path), "wb") as f:
            chunk = (
                audio if isinstance(audio, AudioChunk) else AudioChunk.from_raw(audio)
            )

            sample_width, frame = chunk.to_pcm(normalize)

            f.setnchannels(chunk.format.channels)
            f.setframerate(chunk.format.sample_rate)
            f.setsampwidth(sample_width)
            f.writeframes(frame)
