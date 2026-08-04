from dataclasses import dataclass
from enum import StrEnum


class PreparedReactionKind(StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    WAIT = "wait"


@dataclass(frozen=True, slots=True)
class ConversationTextChunk:
    content: str
    reaction: PreparedReactionKind | None = None


@dataclass(frozen=True, slots=True)
class ConversationQuit:
    pass
