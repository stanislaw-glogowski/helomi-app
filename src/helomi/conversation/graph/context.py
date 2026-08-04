from dataclasses import dataclass
from typing import TYPE_CHECKING

from langgraph.runtime import Runtime

from ..config import ConversationSettings
from ..profile import ConversationProfile

if TYPE_CHECKING:
    from ..tools.service import ToolService

type ConversationRuntime = Runtime[ConversationContext]


@dataclass(frozen=True, slots=True)
class ConversationContext:
    recent_messages: int
    system_prompt: str
    opening_prompt: str
    summary_prompt: str
    acknowledgement_delay: float
    tools: ToolService | None = None

    @staticmethod
    def from_profile(
        profile: ConversationProfile,
        settings: ConversationSettings | None = None,
        tools: ToolService | None = None,
    ) -> ConversationContext:
        settings = settings or ConversationSettings()
        return ConversationContext(
            recent_messages=profile.recent_messages,
            system_prompt=profile.prompts.system,
            opening_prompt=profile.prompts.opening,
            summary_prompt=profile.prompts.summary,
            acknowledgement_delay=settings.acknowledgement_delay,
            tools=tools,
        )
