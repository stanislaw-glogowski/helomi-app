import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .component import PipelineComponent
from .domain import PipelineCmd, PipelineEvent
from .service import PipelineService

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog


class PipelineExtension(PipelineComponent):
    def __init__(self, pipeline: PipelineService, is_enabled: bool) -> None:
        super().__init__()

        self._pipeline = pipeline
        self._is_enabled = asyncio.Event()

        if is_enabled:
            self._is_enabled.set()

    @property
    def profiles(self) -> ProfileCatalog:
        return self._pipeline.profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._pipeline.active_profile

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled.is_set()

    def disable(self) -> None:
        self._is_enabled.clear()

    def enable(self) -> None:
        self._is_enabled.set()

    async def execute(self, cmd: PipelineCmd) -> bool:
        if not self._is_enabled.is_set():
            return False

        return await self._pipeline.execute(cmd)

    def _subscribe(self) -> AsyncIterator[PipelineEvent]:
        return self._pipeline.subscribe(self._is_enabled)
