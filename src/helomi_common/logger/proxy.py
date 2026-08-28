from collections.abc import Iterable
from typing import Any, ClassVar, TextIO


class TaggedStreamProxy:
    _TAG: ClassVar[str] = "\u200b"
    _TRACEBACK_PREFIX: ClassVar[str] = "Traceback (most recent call last):"

    def __init__(self, target_stream: TextIO, skip_untagged=True) -> None:
        self._target = target_stream
        self._enabled = True
        self._skip_untagged = skip_untagged

    @classmethod
    def tag(cls, message: str, /) -> str:
        return f"{cls._TAG}{message}"

    def write(self, message: Any) -> Any:
        if self._enabled and isinstance(message, str):
            if message.startswith(self._TAG):
                return self._target.write(message.removeprefix(self._TAG))
            elif any(message.startswith(prefix) for prefix in self._TRACEBACK_PREFIX):
                self._enabled = False
                return self._target.write(message)
            elif self._skip_untagged:
                return len(message)

        return self._target.write(message)

    def writelines(self, lines: Iterable[str], /) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self._target.flush()

    def fileno(self) -> int:
        return self._target.fileno()

    def isatty(self) -> bool:
        return self._target.isatty()

    @property
    def encoding(self) -> str:
        return getattr(self._target, "encoding", "utf-8")

    @property
    def errors(self) -> str | None:
        return getattr(self._target, "errors", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)
