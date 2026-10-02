from __future__ import annotations

from typing import Protocol

from .configure import LogLevel, configure_logger


class Logger(Protocol):
    def bind(self, **values: object) -> Logger: ...

    def trace(self, message: str, *args: object, **kwargs: object) -> None: ...

    def debug(self, message: str, *args: object, **kwargs: object) -> None: ...

    def info(self, message: str, *args: object, **kwargs: object) -> None: ...

    def warning(self, message: str, *args: object, **kwargs: object) -> None: ...

    def error(self, message: str, *args: object, **kwargs: object) -> None: ...

    def exception(self, message: str, *args: object, **kwargs: object) -> None: ...


__all__ = [
    "LogLevel",
    "Logger",
    "configure_logger",
]
