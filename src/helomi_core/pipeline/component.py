from abc import ABC, abstractmethod

from helomi_common import AbstractAsyncComponent, TaskManager

from ..profile import Profile, ProfileCatalog, ReactionKind
from .domain import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    PipelineCmd,
    PipelineOptions,
    SayReactionCmd,
    SayTextCmd,
    SetOptionsCmd,
)


class PipelineComponent(AbstractAsyncComponent, ABC):
    def __init__(self) -> None:
        super().__init__()
        self._tasks = TaskManager()

    @property
    @abstractmethod
    def profiles(self) -> ProfileCatalog:
        raise NotImplementedError

    @property
    @abstractmethod
    def options(self) -> PipelineOptions:
        raise NotImplementedError

    @property
    @abstractmethod
    def active_profile(self) -> Profile | None:
        raise NotImplementedError

    async def set_options(
        self,
        greeting_enabled: bool | None = None,
        room_voice_enabled: bool | None = None,
        wakeword_enabled: bool | None = None,
    ) -> bool:
        return await self._execute_command(
            SetOptionsCmd(
                greeting_enabled=greeting_enabled,
                room_voice_enabled=room_voice_enabled,
                wakeword_enabled=wakeword_enabled,
            )
        )

    async def activate_profile(self, profile_id: str | None = None) -> bool:
        return await self._execute_command(
            ActivateProfileCmd(
                profile_id=profile_id,
            )
        )

    async def deactivate_profile(self) -> bool:
        return await self._execute_command(DeactivateProfileCmd())

    async def say_text(self, text: str, profile_id: str | None = None) -> bool:
        return await self._execute_command(
            SayTextCmd(
                text=text,
                profile_id=profile_id,
            )
        )

    async def say_reaction(
        self,
        reaction: ReactionKind,
        profile_id: str | None = None,
    ) -> bool:
        return await self._execute_command(
            SayReactionCmd(
                reaction=reaction,
                profile_id=profile_id,
            )
        )

    @abstractmethod
    async def _execute_command(self, cmd: PipelineCmd) -> bool:
        raise NotImplementedError

    async def _pre_open(self) -> None:
        await self._exit_stack.enter_async_context(self._tasks)
