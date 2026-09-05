from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from pathlib import Path
from types import TracebackType
from typing import cast

from .audio import AudioDriver, get_audio_driver
from .config import ProfileCatalog, Settings
from .detection import DetectionWorker
from .parrot import ParrotExtension
from .pipeline import PipelineService
from .resources import ResourceCatalog, UserData
from .server import ServerExtension
from .stt import STTWorker, get_stt_adapter
from .tts import TTSWorker, get_tts_adapter
from .turn import get_turn_adapter
from .vad import get_vad_adapter
from .wakeword import get_wakeword_adapter


class Runtime(AbstractAsyncContextManager):
    def __init__(self, resources: ResourceCatalog | Path | None = None) -> None:
        match resources:
            case Path() | None:
                resources = UserData(resources)

        self._resources: ResourceCatalog = resources
        self._settings: Settings | None = None
        self._profiles: ProfileCatalog | None = None
        self._components: dict[type, object] = {}
        self._exit_stack = AsyncExitStack()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        await self._exit_stack.aclose()

    @property
    def resources(self) -> ResourceCatalog:
        return self._resources

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings.load(self.resources)
        return cast(Settings, self._settings)

    @property
    def profiles(self) -> ProfileCatalog:
        if self._profiles is None:
            self._profiles = ProfileCatalog.load(self.settings, self.resources)
        return cast(ProfileCatalog, self._profiles)

    async def get_audio_driver(self) -> AudioDriver:
        return await self._get_component(
            AudioDriver,
            lambda: get_audio_driver(self.settings.audio),
        )

    async def get_stt_worker(self) -> STTWorker:
        return await self._get_component(
            STTWorker,
            lambda: STTWorker(
                adapter=get_stt_adapter(self.settings.stt),
            ),
        )

    async def get_tts_worker(self) -> TTSWorker:
        return await self._get_component(
            TTSWorker,
            lambda: TTSWorker(
                adapter=get_tts_adapter(self.settings.tts),
            ),
        )

    async def get_detection_worker(self) -> DetectionWorker:
        return await self._get_component(
            DetectionWorker,
            lambda: DetectionWorker(
                turn_adapter=get_turn_adapter(self.settings.turn),
                vad_adapter=get_vad_adapter(self.settings.vad),
                wakeword_adapter=get_wakeword_adapter(
                    self.settings.wakeword,
                    {profile.id: profile.wakeword for profile in self.profiles},
                ),
            ),
        )

    async def get_pipeline_service(self) -> PipelineService:
        async def _creator() -> PipelineService:
            return PipelineService(
                profiles=self.profiles,
                audio_driver=await self.get_audio_driver(),
                detection_worker=await self.get_detection_worker(),
                stt_worker=await self.get_stt_worker(),
                tts_worker=await self.get_tts_worker(),
            )

        return await self._get_component(
            PipelineService,
            _creator,
        )

    async def get_parrot_extension(self, activate=True) -> ParrotExtension:
        async def _creator() -> ParrotExtension:
            pipeline = await self.get_pipeline_service()
            extension = ParrotExtension(
                pipeline=pipeline,
            )
            pipeline.register_extension(extension, activate=activate)
            return extension

        return await self._get_component(
            ParrotExtension,
            _creator,
        )

    async def get_server_extension(self, activate=True) -> ServerExtension:
        async def _creator() -> ServerExtension:
            pipeline = await self.get_pipeline_service()
            extension = ServerExtension(
                config=self.settings.server,
                pipeline=pipeline,
            )
            pipeline.register_extension(extension, activate=activate)
            return extension

        return await self._get_component(
            ServerExtension,
            _creator,
        )

    async def _get_component[T](
        self, cls: type[T], creator: Callable[[], Awaitable[T] | T]
    ) -> T:
        if cls not in self._components:
            res = creator()
            component = await res if isinstance(res, Awaitable) else res

            self._components[cls] = (
                await self._exit_stack.enter_async_context(component)
                if isinstance(component, AbstractAsyncContextManager)
                else component
            )

        return cast(T, self._components[cls])
