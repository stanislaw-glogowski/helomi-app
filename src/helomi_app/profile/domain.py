from enum import StrEnum, auto


class ReactionKind(StrEnum):
    GREETING = auto()
    FAREWELL = auto()
    INTERRUPTED = auto()
