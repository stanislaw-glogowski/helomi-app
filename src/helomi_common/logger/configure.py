import sys
from collections.abc import Callable
from enum import StrEnum, auto
from functools import partialmethod
from typing import TextIO

import loguru
import tqdm

from .proxy import TaggedStreamProxy


class LogLevel(StrEnum):
    TRACE = auto()
    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


def configure_logger(
    format_log: Callable[[loguru.Record], str] | str,
    level: LogLevel = LogLevel.DEBUG,
    skip_untagged=True,
    sink: TextIO | None = None,
) -> loguru.Logger:

    tqdm.tqdm.__init__ = partialmethod(tqdm.tqdm.__init__, disable=True)  # type: ignore[assignment]
    if hasattr(tqdm, "auto"):
        tqdm.auto.tqdm.__init__ = partialmethod(  # type: ignore[assignment]
            tqdm.auto.tqdm.__init__, disable=True
        )

    sys.stderr = TaggedStreamProxy(sys.stderr, skip_untagged)

    def _format_msg(record: loguru.Record) -> str:
        msg = format_log(record) if callable(format_log) else format_log
        return f"{TaggedStreamProxy.tag(msg)}\n"

    logger = loguru.logger
    logger.remove()
    logger.add(
        sink if sink is not None else sys.stderr,
        level=level.name,
        colorize=True,
        format=_format_msg,
    )

    logger.configure()
    return logger
