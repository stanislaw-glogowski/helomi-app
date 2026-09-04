from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from helomi_common import AbstractAsyncComponent, TaskManager

from .domain import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    SayText,
)

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog


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
    def active_profile(self) -> Profile | None:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, cmd: PipelineCmd) -> bool:
        raise NotImplementedError

    async def activate_profile(self, profile_id: str | None = None) -> bool:
        return await self.execute(ActivateProfile(profile_id=profile_id))

    async def deactivate_profile(self) -> bool:
        return await self.execute(DeactivateProfile())

    async def say_text(self, text: str, profile_id: str | None = None) -> bool:
        return await self.execute(SayText(text=text, profile_id=profile_id))

    async def _pre_open(self) -> None:
        await self._exit_stack.enter_async_context(self._tasks)
