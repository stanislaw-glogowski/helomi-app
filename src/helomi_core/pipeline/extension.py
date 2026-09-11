from abc import ABC
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from ..profile import Profile, ProfileCatalog
from .component import PipelineComponent

if TYPE_CHECKING:
    from .domain import PipelineCmd, PipelineEvent, PipelineOptions
    from .service import PipelineService


class PipelineExtension(PipelineComponent, ABC):
    def __init__(self, service: PipelineService) -> None:
        super().__init__()
        self._service = service

    @property
    def options(self) -> PipelineOptions:
        return self._service.options

    @property
    def profiles(self) -> ProfileCatalog:
        return self._service.profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._service.active_profile

    @property
    def is_active(self) -> bool:
        return self._service.active_extension is self.__class__

    async def execute_command(self, cmd: PipelineCmd) -> bool:
        return await self._execute_command(cmd)

    async def _execute_command(self, cmd: PipelineCmd) -> bool:
        return await self._service.execute_command(cmd, self.__class__)

    def _subscribe_event(self) -> AsyncIterator[PipelineEvent]:
        return self._service.subscribe_event(self.__class__)
