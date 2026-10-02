from pathlib import Path
from typing import ClassVar


class PathFile:
    """Represent a filesystem path with a constrained default suffix."""

    _DEFAULT_SUFFIX: ClassVar[str] = ""
    _SUFFIXES: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls):
        super().__init_subclass__()
        if cls._SUFFIXES:
            cls._DEFAULT_SUFFIX = cls._SUFFIXES[0]

    def __init__(self, path: Path):
        self._path = (
            path.with_suffix(self._DEFAULT_SUFFIX)
            if not path.suffix and self._DEFAULT_SUFFIX
            else path
        )

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.is_file()

    def __str__(self) -> str:
        return str(self._path)

    def __repr__(self) -> str:
        return str(self)


class TextFile(PathFile):
    """Read and write UTF-8 text files."""

    _SUFFIXES = (".txt", ".md")

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")
