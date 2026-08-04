from dataclasses import dataclass
from enum import StrEnum

from helomi.conversation.tools.domain import ToolCall, ToolDefinition


class ConversationRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LanguageModelRole(StrEnum):
    FAST = "fast"
    DETAILED = "detailed"
    CLASSIFIER = "classifier"


class ToolChoice(StrEnum):
    """Whether a model response must contain a valid tool call."""

    AUTO = "auto"
    REQUIRED = "required"


class LanguageModelProtocolError(RuntimeError):
    """A model emitted control syntax or failed a required tool-call contract."""


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: ConversationRole
    content: str


@dataclass(frozen=True, slots=True)
class LanguageModelRequest:
    role: LanguageModelRole
    messages: tuple[ConversationMessage, ...]
    cache_prefix: str | None = None
    tools: tuple[ToolDefinition, ...] = ()
    tool_choice: ToolChoice = ToolChoice.AUTO


@dataclass(frozen=True, slots=True)
class LanguageModelChunk:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
