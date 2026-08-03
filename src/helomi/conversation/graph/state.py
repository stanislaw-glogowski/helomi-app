from typing import Literal

from langgraph.graph import MessagesState

type ConversationInputKind = Literal["activation", "user_turn", "maintenance"]


class ConversationState(MessagesState):
    delivery_context: str
    input_kind: ConversationInputKind
    summary: str
