from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from helomi_foundation import ManagedComponent, on_mount, on_unmount
from helomi_runtime.audio import AudioRouter
from helomi_runtime.config import Profile, ProfileCatalog, Settings
from helomi_runtime.resources import ResourceCatalog
from helomi_runtime.runtime import Runtime

from .config import ApplicationSettings, ResponseMode
from .conversation import ConversationOptions, ConversationService
from .messages import (
    ActivateProfileCommand,
    ActivationSource,
    ApplicationCommand,
    ApplicationEvent,
    CommandResult,
    ConversationState,
    DeactivateProfileCommand,
    SayTextCommand,
    SetResponseModeCommand,
)
from .response import (
    APIResponseModule,
    OperatorResponseModule,
    ParrotResponseModule,
    ResponseModule,
)

if TYPE_CHECKING:
    from .server import ServerModule


class Application(ManagedComponent):
    """Public façade shared by the CLI, tray, and HTTP API."""

    def __init__(
        self,
        resources: ResourceCatalog | Path | None = None,
        *,
        serve_api: bool = False,
        response_mode: ResponseMode | None = None,
    ):
        super().__init__()
        self._runtime = Runtime(resources)
        self._app_settings: ApplicationSettings | None = None
        self._serve_api = serve_api
        self._initial_response_mode = response_mode
        self._conversation: ConversationService | None = None
        self._response_modules: dict[ResponseMode, ResponseModule] = {}
        self._server: ServerModule | None = None

    @property
    def settings(self) -> Settings:
        return self._runtime.settings

    @property
    def app_settings(self) -> ApplicationSettings:
        if self._app_settings is None:
            try:
                self._app_settings = ApplicationSettings.model_validate(
                    self.settings.app
                )
            except ValueError as error:
                raise ValueError(
                    f"Invalid app settings in {self.settings.config_path}: {error}"
                ) from error
        return self._app_settings

    @property
    def resources(self) -> ResourceCatalog:
        return self._runtime.resources

    @property
    def profiles(self) -> ProfileCatalog:
        return self._runtime.profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._require_conversation().active_profile

    @property
    def options(self) -> ConversationOptions:
        return self._require_conversation().options

    @property
    def state(self) -> ConversationState:
        return self._require_conversation().state

    @property
    def response_mode(self) -> ResponseMode:
        return self._require_conversation().response_mode

    @property
    def audio_router(self) -> AudioRouter:
        return self._require_conversation().audio_router

    @property
    def server(self) -> ServerModule | None:
        return self._server

    async def execute_command(self, command: ApplicationCommand) -> CommandResult:
        return await self._require_conversation().execute_command(command)

    def subscribe_events(self) -> AsyncIterator[ApplicationEvent]:
        return self._require_conversation().subscribe_events()

    async def activate_profile(
        self,
        profile_id: str,
        source: ActivationSource,
    ) -> CommandResult:
        return await self.execute_command(
            ActivateProfileCommand(profile_id=profile_id, source=source)
        )

    async def deactivate_profile(self, *, play_farewell: bool = True) -> CommandResult:
        return await self.execute_command(
            DeactivateProfileCommand(play_farewell=play_farewell)
        )

    async def say_text(
        self,
        text: str,
        *,
        mode: ResponseMode,
        profile_id: str | None = None,
    ) -> CommandResult:
        return await self.execute_command(
            SayTextCommand(text=text, mode=mode, profile_id=profile_id)
        )

    async def set_response_mode(self, mode: ResponseMode) -> CommandResult:
        return await self.execute_command(SetResponseModeCommand(mode=mode))

    @on_mount()
    async def _compose(self):
        exit_stack = self._exit_stack
        if exit_stack is None:
            raise RuntimeError("Application exit stack is not ready")
        app_settings = self.app_settings
        await exit_stack.enter_async_context(self._runtime)

        modules: tuple[ResponseModule, ...] = (
            APIResponseModule(),
            ParrotResponseModule(),
            OperatorResponseModule(),
        )
        for module in modules:
            await exit_stack.enter_async_context(module)
            self._response_modules[module.mode] = module

        conversation = ConversationService(
            settings=app_settings.conversation,
            profiles=self.profiles,
            reactions=await self._runtime.get_reaction_catalog(),
            audio_router=await self._runtime.get_audio_router(),
            detection_worker=await self._runtime.get_detection_worker(),
            transcription_worker=await self._runtime.get_transcription_worker(),
            synthesis_worker=await self._runtime.get_synthesis_worker(),
            transcription_adapter=self.settings.transcription.adapter,
            synthesis_adapter=self.settings.synthesis.adapter,
            response_mode=(self._initial_response_mode or app_settings.response_mode),
            response_modules=self._response_modules,
        )
        self._conversation = await exit_stack.enter_async_context(conversation)
        if self._serve_api:
            from .server import ServerModule

            self._server = await exit_stack.enter_async_context(
                ServerModule(app_settings.server, self)
            )

    @on_unmount()
    def _release(self):
        self._conversation = None
        self._server = None
        self._response_modules.clear()

    def _require_conversation(self) -> ConversationService:
        if self._conversation is None:
            raise RuntimeError("Application is not mounted")
        return self._conversation
