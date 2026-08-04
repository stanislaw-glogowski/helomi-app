from itertools import cycle
from random import shuffle

from ..model import LanguageModelRole, LanguageModelService
from .config import ConversationReactions


class ProfilePreparation:
    """Rotate shuffled reactions and warm the fast model outside response runs."""

    def __init__(
        self,
        language_model: LanguageModelService,
        reactions: ConversationReactions,
    ) -> None:
        self._language_model = language_model
        wake_reactions = list(reactions.wake)
        acknowledge_reactions = list(reactions.acknowledge)
        wait_reactions = list(reactions.wait)
        background_reactions = list(reactions.background)
        quit_reactions = list(reactions.quit)
        shuffle(wake_reactions)
        shuffle(acknowledge_reactions)
        shuffle(wait_reactions)
        shuffle(background_reactions)
        shuffle(quit_reactions)
        self._wake_reactions = cycle(wake_reactions)
        self._acknowledge_reactions = cycle(acknowledge_reactions)
        self._wait_reactions = cycle(wait_reactions)
        self._background_reactions = cycle(background_reactions)
        self._quit_reactions = cycle(quit_reactions)

    async def prepare(self) -> None:
        await self._language_model.prepare(LanguageModelRole.FAST)

    def next_wake_reaction(self) -> str | None:
        return next(self._wake_reactions, None)

    def next_acknowledgement_reaction(self) -> str | None:
        return next(self._acknowledge_reactions, None)

    def next_wait_reaction(self) -> str | None:
        return next(self._wait_reactions, None)

    def next_background_reaction(self) -> str | None:
        return next(self._background_reactions, None)

    def next_quit_reaction(self) -> str | None:
        return next(self._quit_reactions, None)
