import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from helomi_foundation import ManagedComponent, on_unmount

from .adapters import (
    create_audio_drivers,
    create_synthesis_adapter,
    create_transcription_adapter,
    create_turn_adapter,
    create_vad_adapter,
    create_wakeword_adapter,
)
from .audio import AudioRouter
from .config import ProfileCatalog, Settings
from .detection import DetectionWorker
from .reaction import ReactionCatalog
from .resources import FileSystemResourceCatalog, ResourceCatalog
from .synthesis import SynthesisWorker
from .transcription import TranscriptionWorker


class Runtime(ManagedComponent):
    """Compose and lazily mount profile-scoped runtime components."""

    def __init__(self, resources: ResourceCatalog | Path | None = None):
        super().__init__()
        if isinstance(resources, Path) or resources is None:
            resources = FileSystemResourceCatalog(resources)
        self._resources = resources
        self._settings: Settings | None = None
        self._profiles: ProfileCatalog | None = None
        self._components: dict[type, object] = {}

    @property
    def resources(self) -> ResourceCatalog:
        return self._resources

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings.load(self.resources)
        return self._settings

    @property
    def profiles(self) -> ProfileCatalog:
        if self._profiles is None:
            self._profiles = ProfileCatalog.load(self.settings, self.resources)
        return self._profiles

    async def get_audio_router(self) -> AudioRouter:
        return await self._get_component(
            AudioRouter,
            lambda: AudioRouter(
                settings=self.settings.audio,
                drivers=create_audio_drivers(self),
            ),
        )

    async def get_detection_worker(self) -> DetectionWorker:
        return await self._get_component(
            DetectionWorker,
            lambda: DetectionWorker(
                turn_adapter=create_turn_adapter(self),
                vad_adapter=create_vad_adapter(self),
                wakeword_adapter=create_wakeword_adapter(self),
            ),
        )

    async def get_transcription_worker(self) -> TranscriptionWorker:
        return await self._get_component(
            TranscriptionWorker,
            lambda: TranscriptionWorker(adapter=create_transcription_adapter(self)),
        )

    async def get_synthesis_worker(self) -> SynthesisWorker:
        return await self._get_component(
            SynthesisWorker,
            lambda: SynthesisWorker(adapter=create_synthesis_adapter(self)),
        )

    async def get_reaction_catalog(self) -> ReactionCatalog:
        async def create() -> ReactionCatalog:
            synthesis = self.settings.synthesis
            return ReactionCatalog(
                profiles=self.profiles,
                synthesis_worker=await self.get_synthesis_worker(),
                synthesis_adapter=synthesis.adapter,
            )

        return await self._get_component(ReactionCatalog, create)

    async def _get_component[T](
        self,
        component_type: type[T],
        creator: Callable[[], Awaitable[T] | T],
    ) -> T:
        if not self.is_mounted or self._exit_stack is None:
            raise RuntimeError("Runtime is not mounted")
        component = self._components.get(component_type)
        if component is None:
            created = creator()
            component = await created if inspect.isawaitable(created) else created
            if isinstance(component, ManagedComponent):
                component = await self._exit_stack.enter_async_context(component)
            self._components[component_type] = component
        return cast(T, component)

    @on_unmount()
    def _clear_components(self) -> None:
        self._components.clear()
