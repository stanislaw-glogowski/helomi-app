from typing import Any, Literal

from langgraph.graph import MessagesState

type ConversationInputKind = Literal[
    "activation", "user_turn", "maintenance", "background_result"
]


class ConversationState(MessagesState):
    delivery_context: str
    input_kind: ConversationInputKind
    summary: str
    pending_tool: dict[str, Any] | None
