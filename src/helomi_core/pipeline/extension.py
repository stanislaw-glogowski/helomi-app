from abc import ABC
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .component import PipelineComponent
from .domain import PipelineCmd, PipelineEvent

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog
    from .service import PipelineService


type PipelineExtensionKey = type[PipelineExtension]


class PipelineExtension(PipelineComponent, ABC):
    def __init__(self, pipeline: PipelineService) -> None:
        super().__init__()
        self._pipeline = pipeline

    @property
    def profiles(self) -> ProfileCatalog:
        return self._pipeline.profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._pipeline.active_profile

    @property
    def is_active(self) -> bool:
        return self._pipeline.active_extension is self.__class__

    async def execute_command(self, cmd: PipelineCmd) -> bool:
        return await self._execute_command(cmd)

    async def _execute_command(self, cmd: PipelineCmd) -> bool:
        return await self._pipeline.execute_command(cmd, self)

    def _subscribe_event(self) -> AsyncIterator[PipelineEvent]:
        return self._pipeline.subscribe_event(self)
