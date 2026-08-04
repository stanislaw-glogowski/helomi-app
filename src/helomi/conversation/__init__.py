import asyncio
from typing import TYPE_CHECKING

from helomi.common.events import EventBus

from .config import ConversationSettings
from .events import (
    BackgroundResult,
    CancelReply,
    ConversationActivated,
    ConversationReady,
    GenerateReply,
    PhraseId,
    QuitRequested,
    ReplyChunk,
    ReplyDraftUpdated,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyId,
    ReplyPhrase,
    UserTurn,
)
from .graph import ResponseDepth, ToolPolicy, TurnIntent, TurnPlan, TurnPlanner
from .memory import (
    ConversationMemory,
    InMemoryConversationMemory,
    MemoryFact,
    SqliteConversationMemory,
)
from .model import (
    ConversationMessage,
    ConversationRole,
    LanguageModelChunk,
    LanguageModelProtocolError,
    LanguageModelRequest,
    LanguageModelRole,
    ToolChoice,
)
from .profile import ConversationProfile, ConversationReactions
from .reply import ConversationTextChunk

if TYPE_CHECKING:
    from .tools.service import ToolService

__all__ = [
    "BackgroundResult",
    "CancelReply",
    "ConversationActivated",
    "ConversationMemory",
    "ConversationMessage",
    "ConversationProfile",
    "ConversationReactions",
    "ConversationReady",
    "ConversationRole",
    "ConversationSettings",
    "ConversationTextChunk",
    "GenerateReply",
    "InMemoryConversationMemory",
    "LanguageModelChunk",
    "LanguageModelProtocolError",
    "LanguageModelRequest",
    "LanguageModelRole",
    "MemoryFact",
    "PhraseId",
    "QuitRequested",
    "ReplyChunk",
    "ReplyDraftUpdated",
    "ReplyGenerationCompleted",
    "ReplyGenerationStarted",
    "ReplyId",
    "ReplyPhrase",
    "ResponseDepth",
    "SqliteConversationMemory",
    "ToolChoice",
    "ToolPolicy",
    "TurnIntent",
    "TurnPlan",
    "TurnPlanner",
    "UserTurn",
    "run_conversation_worker",
]


async def run_conversation_worker(
    event_bus: EventBus,
    profile: ConversationProfile,
    settings: ConversationSettings,
    start_event: asyncio.Event | None = None,
    tools: ToolService | None = None,
    memory: ConversationMemory | None = None,
) -> None:
    from .graph import ConversationContext, ConversationGraph, ConversationNodes
    from .memory import InMemoryConversationMemory
    from .model import LanguageModelService, get_language_model
    from .profile import ProfilePreparation
    from .worker import Worker

    language_model = get_language_model(
        profile,
        settings.language_model,
        require_classifier=True,
    )
    memory = memory or InMemoryConversationMemory()
    context = ConversationContext.from_profile(profile, settings, tools, memory)
    async with LanguageModelService(language_model) as service:
        preparation = ProfilePreparation(service, profile.reactions)
        graph = ConversationGraph(
            nodes=ConversationNodes(service, profile_preparation=preparation),
            checkpointer=memory.checkpointer,
        )
        await Worker(
            event_bus=event_bus,
            graph=graph,
            context=context,
            profile_preparation=preparation,
            start_event=start_event,
            memory=memory,
        ).run()
