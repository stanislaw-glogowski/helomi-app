import asyncio
import threading
import webbrowser
from contextlib import suppress
from dataclasses import replace
from typing import ClassVar, Unpack

import rumps

from helomi_app import Runtime
from helomi_app.common import BaseComponent, TaskManager
from helomi_app.core.audio import AudioDriverKind
from helomi_app.pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ExtensionActivatedEvent,
    ExtensionDeactivatedEvent,
    OptionsSetEvent,
    PipelineCmd,
    PipelineExtensionType,
    PipelineService,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayTextCmd,
    SetOptionsCmd,
)
from helomi_app.pipeline.parrot import ParrotExtension
from helomi_app.pipeline.server import ServerExtension

from .icons import AppIcon
from .menu import MenuGroup, MenuItem
from .state import AppMode, AppState, AppStatus
from .windows import BaseWindow, TTSWindow


class App(rumps.App, BaseComponent):
    _TITLE: ClassVar[str] = "Helomi"

    def __init__(self, runtime: Runtime):
        rumps.App.__init__(
            self,
            name=self._TITLE,
            title=self._TITLE,
            quit_button=None,
        )
        BaseComponent.__init__(self)

        self._runtime = runtime

        self._pipeline: PipelineService | None = None

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._ready_signal: asyncio.Event | None = None
        self._shutdown_signal: asyncio.Event | None = None

        self._start_icon = AppIcon.Start()
        self._state = AppState()
        self._last_state = AppState()
        self._previous_mode: AppMode = AppMode.SERVER

        self._window: BaseWindow | None = None

        self._lock = threading.Lock()

        with suppress(Exception):
            import AppKit

            AppKit.NSApplication.sharedApplication().setActivationPolicy_(
                AppKit.NSApplicationActivationPolicyAccessory
            )

        # menu

        self._menu_profiles = MenuGroup(
            title="Profiles",
        )

        for index, profile in enumerate(runtime.profiles):
            self._menu_profiles.add_action(
                MenuItem(
                    id=profile.id,
                    key=str(index) if index < 9 else None,
                    title=f"{profile.name} (default)" if index == 0 else profile.name,
                    callback=self._on_profile_click,
                    checked=profile.id == self._state.profile_id,
                )
            )

        self._menu_settings = MenuGroup(
            title="Settings",
        )

        self._menu_settings.add_action(
            MenuItem(
                id="persistent_profile",
                title="Persistent Profile",
                callback=self._on_setting_click,
            )
        )
        self._menu_settings.add_action(
            MenuItem(
                id="wakeword",
                title="Wake Word",
                callback=self._on_setting_click,
            )
        )
        self._menu_settings.add_action(
            MenuItem(
                id="reactions",
                title="Reactions",
                callback=self._on_setting_click,
            )
        )
        self._menu_settings.add_action(
            MenuItem(
                id="room_voice",
                title="Room Voice",
                callback=self._on_setting_click,
            )
        )

        self._menu_tts = MenuItem(
            id="tts_window",
            title="Text-to-Speech",
            key="t",
            callback=self._handle_open_window,
        )

        self._menu_parrot = MenuItem(
            title="Parrot Mode",
            key="p",
            callback=self._on_parrot_click,
        )

        self._menu_server = MenuItem(
            title="Starting Server",
            callback=self._on_server_click,
        )

        self.menu = [
            self._menu_profiles,
            rumps.separator,
            self._menu_tts,
            self._menu_parrot,
            rumps.separator,
            self._menu_server,
            rumps.separator,
            self._menu_settings,
            rumps.separator,
            rumps.MenuItem(
                title="Quit",
                callback=self._on_quit_click,
                key="q",
            ),
        ]

    def run(self, **options):
        self._before_run()
        super().run(**options)

    def quit(self):
        self._on_quit_click(None)

    @rumps.timer(0.1)
    def _animate_start_icon(self, sender: rumps.Timer | None = None):
        if self._state.status != AppStatus.STARTING:
            if sender:
                sender.stop()
            return

        self.title = f"{self._start_icon} {self._TITLE}"

    @rumps.timer(0.5)
    def _sync_state(self, _: rumps.Timer | None = None):
        state = self._state
        if self._last_state == state:
            return

        last_state, self._last_state = self._last_state, state

        match state.status:
            case AppStatus.RUNNING:
                profile = (
                    self._runtime.profiles.get(state.profile_id)
                    if state.profile_id
                    else None
                )

                self._menu_tts.set_enabled(True)
                self._menu_tts.set_checked(state.mode == AppMode.TTS)

                self._menu_parrot.set_enabled(True)
                self._menu_parrot.set_checked(state.mode == AppMode.PARROT)

                match state.mode:
                    case AppMode.SERVER:
                        mode_icon = None
                    case AppMode.TTS:
                        mode_icon = AppIcon.TTS_MODE
                    case AppMode.PARROT:
                        mode_icon = AppIcon.PARROT_MODE

                match state.audio_driver:
                    case AudioDriverKind.LOCAL | None:
                        self._menu_profiles.set_enabled(True)

                        action = self._menu_settings.get_action("persistent_profile")
                        action.set_checked(
                            state.persistent_profile_enabled
                            and state.persistent_profile_supported
                        )
                        action.set_enabled(state.persistent_profile_supported)

                        action = self._menu_settings.get_action("wakeword")
                        action.set_checked(
                            state.wakeword_enabled and state.wakeword_supported
                        )
                        action.set_enabled(state.wakeword_supported)

                        action = self._menu_settings.get_action("reactions")
                        action.set_checked(
                            state.reactions_enabled and state.reactions_supported
                        )
                        action.set_enabled(state.reactions_supported)

                        action = self._menu_settings.get_action("room_voice")
                        action.set_checked(
                            state.room_voice_enabled and state.room_voice_supported
                        )
                        action.set_enabled(state.room_voice_supported)

                        if mode_icon:
                            icon = mode_icon
                        elif profile:
                            icon = profile.emoji
                        elif state.wakeword_enabled:
                            icon = AppIcon.WAKEWORD_ACTIVE
                        else:
                            icon = AppIcon.WAKEWORD_IDLE

                    case AudioDriverKind.GSM:
                        self._menu_profiles.set_enabled(False)
                        self._menu_parrot.set_checked(state.mode == AppMode.PARROT)

                        if mode_icon:
                            icon = mode_icon
                        elif profile:
                            icon = AppIcon.PHONE_ACTIVE
                        else:
                            icon = AppIcon.PHONE_IDLE

                label = profile.name if profile else self._TITLE

                title = f"{icon} {label}"

                if profile and state.room_voice_enabled and profile.has_room_voice:
                    title = f"{title} {AppIcon.ROOM_VOICE}"

                self.title = title

                if state.mode == AppMode.SERVER and state.api_url:
                    self._menu_server.title = "API Documentation"
                    self._menu_server.set_enabled(True)
                else:
                    self._menu_server.title = "API Disabled"
                    self._menu_server.set_enabled(False)

                if last_state.profile_id != state.profile_id:
                    if last_state.profile_id:
                        self._menu_profiles.get_action(
                            last_state.profile_id,
                        ).set_checked(False)

                    if state.profile_id:
                        self._menu_profiles.get_action(
                            state.profile_id,
                        ).set_checked(True)

            case AppStatus.QUITING:
                if last_state.status == AppStatus.RUNNING:
                    self._menu_profiles.set_enabled(False)
                    self._menu_parrot.set_enabled(False)
                    self._menu_tts.set_enabled(False)
                    self._menu_server.title = "Stopping Server"
                    self._menu_server.set_enabled(False)
                    self._menu_settings.set_enabled(False)

                self.title = f"{AppIcon.QUITING} {self._TITLE}"

    def _update_state(
        self,
        force_sync: bool = False,
        **kwargs: Unpack[AppState.Update],
    ):
        if self._state.status == AppStatus.QUITING:
            return

        with self._lock:
            self._state = replace(self._state, **kwargs)

            if force_sync:
                self._sync_state(None)

    def _set_mode(self, mode: AppMode):
        extension: PipelineExtensionType | None
        match mode:
            case AppMode.SERVER:
                extension = ServerExtension
            case AppMode.PARROT:
                extension = ParrotExtension
            case AppMode.TTS:
                extension = None

        self._update_state(mode=mode)

        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.activate_extension(extension)
            if extension
            else self._pipeline.deactivate_extension(),
            self._loop,
        )

    def _on_profile_click(self, sender: MenuItem):
        if sender.checked:
            self._pipeline_execute_command(DeactivateProfileCmd())
        else:
            self._pipeline_execute_command(
                ActivateProfileCmd(
                    profile_id=sender.id,
                )
            )

    def _on_parrot_click(self, sender: MenuItem):
        self._handle_close_window()

        if sender.checked:
            self._set_mode(AppMode.SERVER)
        else:
            self._set_mode(AppMode.PARROT)

    def _on_server_click(self, _: MenuItem):
        if url := self._state.api_url:
            webbrowser.open(url)

    def _on_audio_click(self, sender: MenuItem):
        pass

    def _on_setting_click(self, sender: MenuItem):
        self._pipeline_execute_command(
            SetOptionsCmd(
                persistent_profile_enabled=not sender.checked
                if sender.id == "persistent_profile"
                else None,
                wakeword_enabled=not sender.checked
                if sender.id == "wakeword"
                else None,
                reactions_enabled=not sender.checked
                if sender.id == "reactions"
                else None,
                room_voice_enabled=not sender.checked
                if sender.id == "room_voice"
                else None,
            )
        )

    def _on_quit_click(self, sender: rumps.MenuItem | None = None):
        if sender is not None:
            sender.set_callback(None)

        self._update_state(
            status=AppStatus.QUITING,
            force_sync=True,
        )
        rumps.Timer(self._handle_exit, 0.1).start()

    def _handle_exit(self, sender: rumps.Timer):
        sender.stop()

        if self._window is not None:
            self._window.close()
            self._window = None

        if self._loop and self._shutdown_signal and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_signal.set)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        rumps.quit_application()

    def _handle_open_window(self, sender: MenuItem):
        match sender.id:
            case "tts_window":
                if isinstance(self._window, TTSWindow):
                    self._window.close()
                    return
            case _:
                return

        if self._window:
            self._window.close()

        match sender.id:
            case "tts_window":
                self._previous_mode = self._state.mode
                self._set_mode(AppMode.TTS)
                window = TTSWindow(
                    on_send=self._handle_tts_send,
                    on_close=lambda: self._handle_close_window(),
                    get_profile_id=lambda: self._state.profile_id,
                )
                self._window = window
                window.show()

    def _handle_close_window(
        self,
    ):
        window, self._window = self._window, None
        if window is None:
            return

        window.close()
        self._window = None

        self._set_mode(self._previous_mode)

    def _handle_tts_send(self, text: str):
        self._pipeline_execute_command(
            SayTextCmd(
                text=text,
                profile_id=self._state.profile_id,
            )
        )

    def _before_run(self):
        thread = threading.Thread(
            target=self._thread_worker,
            daemon=True,
            name=self.__label__,
        )
        self._thread = thread
        thread.start()

    def _thread_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self._loop = loop

        try:
            loop.run_until_complete(self._runtime_loop())
        except asyncio.CancelledError, KeyboardInterrupt:
            pass
        except Exception as err:
            self._logger.exception("Error in TrayApp runtime loop: {}", err)
        finally:
            with suppress(Exception):
                loop.close()

    async def _runtime_loop(self):
        self._shutdown_signal = (shutdown_signal := asyncio.Event())

        async with self._runtime:
            audio_driver = await self._runtime.get_audio_driver()
            pipeline = await self._runtime.get_pipeline_service()
            server_extension = await self._runtime.get_pipeline_server_extension(
                self._state.mode is AppMode.SERVER
            )
            await self._runtime.get_pipeline_parrot_extension(
                self._state.mode is AppMode.PARROT
            )

            self._pipeline = pipeline

            async with TaskManager() as tasks:
                tasks.add_task(self._pipeline_loop())

                self._update_state(
                    status=AppStatus.RUNNING,
                    api_url=server_extension.docs_url,
                    profile_id=profile.id
                    if (profile := pipeline.active_profile) is not None
                    else None,
                    persistent_profile_enabled=pipeline.options.persistent_profile_enabled,
                    persistent_profile_supported=pipeline.options.persistent_profile_supported,
                    wakeword_enabled=pipeline.options.wakeword_enabled,
                    wakeword_supported=pipeline.options.wakeword_supported,
                    reactions_enabled=pipeline.options.reactions_enabled,
                    reactions_supported=pipeline.options.reactions_supported,
                    room_voice_enabled=pipeline.options.room_voice_enabled,
                    room_voice_supported=pipeline.options.room_voice_supported,
                    audio_driver=audio_driver.kind,
                )

                await shutdown_signal.wait()

    async def _pipeline_loop(self):
        if self._pipeline is None:
            return

        async for event in self._pipeline.subscribe_event():
            match event:
                case OptionsSetEvent():
                    self._update_state(
                        persistent_profile_enabled=self._pipeline.options.persistent_profile_enabled,
                        wakeword_enabled=self._pipeline.options.wakeword_enabled,
                        reactions_enabled=self._pipeline.options.reactions_enabled,
                        room_voice_enabled=self._pipeline.options.room_voice_enabled,
                    )

                case ProfileActivatedEvent(profile_id=profile_id):
                    self._update_state(profile_id=profile_id)

                case ProfileDeactivatedEvent():
                    self._update_state(profile_id=None)

                case ExtensionActivatedEvent(options=options):
                    self._update_state(
                        persistent_profile_supported=options.persistent_profile_supported,
                        wakeword_supported=options.wakeword_supported,
                        reactions_supported=options.reactions_supported,
                        room_voice_supported=options.room_voice_supported,
                    )

                case ExtensionDeactivatedEvent(options=options) if options is not None:
                    self._update_state(
                        persistent_profile_supported=options.persistent_profile_supported,
                        wakeword_supported=options.wakeword_supported,
                        reactions_supported=options.reactions_supported,
                        room_voice_supported=options.room_voice_supported,
                    )

                case _:
                    pass

            if self._window is not None:
                self._window.handle_event(event)

    def _pipeline_execute_command(self, cmd: PipelineCmd):
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.execute_command(cmd),
            self._loop,
        )
