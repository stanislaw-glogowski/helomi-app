import sys
from collections.abc import Callable
from enum import StrEnum, auto
from functools import partialmethod
from typing import TextIO

import loguru
import tqdm

from .proxy import TaggedStreamProxy

type LogFormatter = Callable[[loguru.Record], str]


class LogLevel(StrEnum):
    TRACE = auto()
    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class LogFormat(StrEnum):
    PRETTY = auto()


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


def pretty_log_formatter(record: loguru.Record) -> str:
    extra = record["extra"]
    path: list[str] = []

    if (comp := extra.get("component")) and isinstance(comp, str) and comp:
        path.append(comp)

    match extra.get("context"):
        case str(ctx) if ctx:
            path.append(ctx)
        case list(items):
            path.extend(c for c in items if isinstance(c, str) and c)

    parts = filter(
        None,
        [
            "<level>{level: <8}</level>",
            f"<cyan>{'.'.join(path)}</cyan>" if path else None,
            "<level>{message}</level>",
        ],
    )
    return " | ".join(parts)
