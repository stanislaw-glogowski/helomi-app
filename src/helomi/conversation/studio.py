from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from helomi.conversation.graph import (
    ConversationContext,
    ConversationGraph,
    ConversationNodes,
)
from helomi.conversation.model import LanguageModelService, get_language_model
from helomi.resources import LocalStore


@asynccontextmanager
async def conversation_graph() -> AsyncGenerator[
    CompiledStateGraph[Any, ConversationContext, Any, Any]
]:
    """Own the model service for the lifetime of a LangGraph Studio run."""

    store = LocalStore()
    profile = store.load_default_profile().conversation
    settings = store.load_settings().conversation
    adapter = get_language_model(
        profile,
        settings.language_model,
        require_classifier=True,
    )
    async with LanguageModelService(adapter) as service:
        yield ConversationGraph(nodes=ConversationNodes(service)).compiled
