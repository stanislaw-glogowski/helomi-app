from dataclasses import dataclass

from helomi.common.events import Event, StateEvent

from .reply import PreparedReactionKind

type ReplyId = int
type PhraseId = int


@dataclass(frozen=True, slots=True)
class ConversationActivated:
    pass


@dataclass(frozen=True, slots=True)
class UserTurn:
    text: str


@dataclass(frozen=True, slots=True)
class BackgroundResult:
    tool_name: str
    content: str
    failed: bool = False


type ConversationInput = ConversationActivated | UserTurn | BackgroundResult


@dataclass(frozen=True, slots=True)
class GenerateReply(Event):
    input: ConversationInput
    protected_delivery: bool = False


@dataclass(frozen=True, slots=True)
class ConversationReady(StateEvent):
    pass


@dataclass(frozen=True, slots=True)
class CancelReply(Event):
    """Cancel generation and describe the prefix certainly heard by the user."""

    spoken_text: str = ""
    reply_id: ReplyId | None = None


@dataclass(frozen=True, slots=True)
class ReplyGenerationStarted(Event):
    """Signal that a finite conversation graph run started generating."""

    reply_id: ReplyId
    protected_delivery: bool = False


@dataclass(frozen=True, slots=True)
class ReplyGenerationCompleted(Event):
    """Signal that generation ended; audio delivery may still be active."""

    reply_id: ReplyId


@dataclass(frozen=True, slots=True)
class QuitRequested(Event):
    reply_id: ReplyId
    final_phrase_id: PhraseId


@dataclass(frozen=True, slots=True)
class ReplyChunk(Event):
    reply_id: ReplyId
    text: str


@dataclass(frozen=True, slots=True)
class ReplyDraftUpdated(Event):
    """Current incomplete phrase assembled from streamed model chunks."""

    reply_id: ReplyId
    text: str


@dataclass(frozen=True, slots=True)
class ReplyPhrase(Event):
    """Complete plain-text phrase ready for independent speech synthesis."""

    reply_id: ReplyId
    phrase_id: PhraseId
    text: str
    reaction: PreparedReactionKind | None = None
