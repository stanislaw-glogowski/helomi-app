from enum import StrEnum, auto


class ReactionKind(StrEnum):
    GREETING = auto()
    CONNECTED = auto()
    FAREWELL = auto()
    INTERRUPTED = auto()
