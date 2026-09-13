import shutil
from pathlib import Path
from typing import ClassVar, Literal


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
            path.mkdir(parents=True, exist_ok=True)
        return path
