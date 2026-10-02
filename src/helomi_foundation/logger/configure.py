import sys
from enum import StrEnum, auto
from functools import partialmethod
from typing import TextIO

import loguru
import tqdm

from .formatter import LogFormat, LogFormatter, pretty_log_formatter
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
    level: LogLevel = LogLevel.TRACE,
    format: LogFormat | LogFormatter = LogFormat.PRETTY,
    sink: TextIO | None = None,
    skip_untagged=True,
) -> loguru.Logger:
    tqdm.tqdm.__init__ = partialmethod(tqdm.tqdm.__init__, disable=True)  # type: ignore[assignment]
    if hasattr(tqdm, "auto"):
        tqdm.auto.tqdm.__init__ = partialmethod(  # type: ignore[assignment]
            tqdm.auto.tqdm.__init__, disable=True
        )

    sys.stderr = TaggedStreamProxy(sys.stderr, skip_untagged)

    match format:
        case LogFormat.PRETTY:
            formatter = pretty_log_formatter
        case _:
            formatter = format

    logger = loguru.logger
    logger.remove()
    logger.add(
        sink if sink is not None else sys.stderr,
        level=level.name,
        colorize=True,
        format=lambda record: f"{TaggedStreamProxy.tag(formatter(record))}\n",
    )
    logger.configure()
    return logger
