from collections.abc import Callable
from enum import StrEnum, auto
from typing import Any

type LogRecord = dict[str, Any]

type LogFormatter = Callable[[LogRecord], str]


class LogFormat(StrEnum):
    PRETTY = auto()


def pretty_log_formatter(record: LogRecord) -> str:
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
