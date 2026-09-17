from typing import ClassVar

from .file import AbstractFile


class TextFile(AbstractFile):
    _SUFFIXES: ClassVar[list[str]] = [".txt", ".md"]

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, content: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")
