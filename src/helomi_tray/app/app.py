import asyncio
import threading
import webbrowser
from contextlib import suppress
from dataclasses import replace
from typing import ClassVar, Unpack

import rumps

from helomi_common import BaseComponent, TaskManager
from helomi_core import Runtime
from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    OptionsSetEvent,
    PipelineCmd,
    PipelineExtensionType,
    PipelineService,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayTextCmd,
    SetOptionsCmd,
)
from helomi_core.server import ServerExtension

from .icons import AppIcon
from .menu import MenuGroup, MenuItem
from .state import AppMode, AppState, AppStatus
from .windows import BaseWindow, TTSWindow


class App(rumps.App, BaseComponent):
    _TITLE: ClassVar[str] = "Helomi"

    def __init__(self, runtime: Runtime) -> None:
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
                id="greeting_enabled",
                title="Greeting",
                callback=self._on_setting_click,
            )
        )
        self._menu_settings.add_action(
            MenuItem(
                id="room_voice_enabled",
                title="Room Voice",
                callback=self._on_setting_click,
            )
        )
        self._menu_settings.add_action(
            MenuItem(
                id="wakeword_enabled",
                title="Wake Word",
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

    def run(self, **options) -> None:
        self._before_run()
        super().run(**options)

    def quit(self) -> None:
        self._on_quit_click(None)

    @rumps.timer(0.1)
    def _animate_start_icon(self, sender: rumps.Timer | None = None) -> None:
        if self._state.status != AppStatus.STARTING:
            if sender:
                sender.stop()
            return

        self.title = f"{self._start_icon} {self._TITLE}"

    @rumps.timer(0.5)
    def _sync_state(self, _: rumps.Timer | None = None) -> None:
        if self._last_state == self._state:
            return

        last_state, self._last_state = self._last_state, self._state

        match self._state.status:
            case AppStatus.RUNNING:
                self._menu_profiles.set_enabled(True)

                if last_state.profile_id != self._state.profile_id:
                    if last_state.profile_id:
                        self._menu_profiles.get_action(
                            last_state.profile_id,
                        ).set_checked(False)

                    if self._state.profile_id:
                        self._menu_profiles.get_action(
                            self._state.profile_id,
                        ).set_checked(True)

                if self._state.mode == AppMode.SERVER and self._state.api_url:
                    self._menu_server.title = "API Documentation"
                    self._menu_server.set_enabled(True)
                else:
                    self._menu_server.title = "API Disabled"
                    self._menu_server.set_enabled(False)

                self._menu_parrot.set_enabled(True)
                self._menu_parrot.set_checked(self._state.mode == AppMode.PARROT)

                self._menu_tts.set_enabled(True)

                self._menu_settings.set_enabled(self._state.mode != AppMode.TTS)
                self._menu_settings.get_action("greeting_enabled").set_checked(
                    self._state.greeting_enabled
                )
                self._menu_settings.get_action("room_voice_enabled").set_checked(
                    self._state.room_voice_enabled
                )
                self._menu_settings.get_action("wakeword_enabled").set_checked(
                    self._state.wakeword_enabled
                )

                profile = (
                    self._runtime.profiles.get(self._state.profile_id)
                    if self._state.profile_id
                    else None
                )

                label = profile.name if profile else self._TITLE

                if self._state.mode == AppMode.PARROT:
                    icon = AppIcon.PARROT
                elif self._state.mode == AppMode.TTS:
                    icon = AppIcon.TTS
                elif profile:
                    icon = profile.emoji
                elif self._state.wakeword_enabled:
                    icon = AppIcon.LISTEN
                else:
                    icon = AppIcon.IDLE

                title = f"{icon} {label}"

                if (
                    profile
                    and self._state.mode != AppMode.TTS
                    and profile.audio.room_voice_path
                    and self._state.room_voice_enabled
                ):
                    title = f"{title} {AppIcon.MUSIC}"

                self.title = title

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
    ) -> None:
        if self._state.status == AppStatus.QUITING:
            return

        with self._lock:
            self._state = replace(self._state, **kwargs)

            if force_sync:
                self._sync_state(None)

    def _set_mode(self, mode: AppMode) -> None:
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

    def _on_profile_click(self, sender: MenuItem) -> None:
        if sender.checked:
            self._pipeline_execute_command(DeactivateProfileCmd())
        else:
            self._pipeline_execute_command(
                ActivateProfileCmd(
                    profile_id=sender.id,
                )
            )

    def _on_parrot_click(self, sender: MenuItem) -> None:
        self._handle_close_window()

        if sender.checked:
            self._set_mode(AppMode.SERVER)
        else:
            self._set_mode(AppMode.PARROT)

    def _on_server_click(self, _: MenuItem) -> None:
        if url := self._state.api_url:
            webbrowser.open(url)

    def _on_setting_click(self, sender: MenuItem) -> None:
        self._pipeline_execute_command(
            SetOptionsCmd(
                greeting_enabled=not sender.checked
                if sender.id == "greeting_enabled"
                else None,
                room_voice_enabled=not sender.checked
                if sender.id == "room_voice_enabled"
                else None,
                wakeword_enabled=not sender.checked
                if sender.id == "wakeword_enabled"
                else None,
            )
        )

    def _on_quit_click(self, sender: rumps.MenuItem | None = None) -> None:
        if sender is not None:
            sender.set_callback(None)

        self._update_state(
            status=AppStatus.QUITING,
            force_sync=True,
        )
        rumps.Timer(self._handle_exit, 0.1).start()

    def _handle_exit(self, sender: rumps.Timer) -> None:
        sender.stop()

        if self._window is not None:
            self._window.close()
            self._window = None

        if self._loop and self._shutdown_signal and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_signal.set)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        rumps.quit_application()

    def _handle_open_window(self, sender: MenuItem) -> None:
        match sender.id:
            case "tts_window":
                if isinstance(self._window, TTSWindow):
                    self._window.activate()
                    return
            case _:
                return

        if self._window:
            self._window.close()

        previous_mode = self._state.mode

        match sender.id:
            case "tts_window":
                self._set_mode(AppMode.TTS)
                window = TTSWindow(
                    on_send=self._handle_tts_send,
                    on_close=lambda: self._handle_close_window(previous_mode),
                    get_profile_id=lambda: self._state.profile_id,
                )
                self._window = window
                window.show()

    def _handle_close_window(self, mode: AppMode | None = None) -> None:
        window, self._window = self._window, None
        if window is None:
            return

        window.close()
        self._window = None

        if mode:
            self._set_mode(mode)

    def _handle_tts_send(self, text: str) -> None:
        self._pipeline_execute_command(
            SayTextCmd(
                text=text,
                profile_id=self._state.profile_id,
            )
        )

    def _before_run(self) -> None:
        thread = threading.Thread(
            target=self._thread_worker,
            daemon=True,
            name=self.__label__,
        )
        self._thread = thread
        thread.start()

    def _thread_worker(self) -> None:
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

    async def _runtime_loop(self) -> None:
        self._shutdown_signal = (shutdown_signal := asyncio.Event())

        async with self._runtime:
            pipeline = await self._runtime.get_pipeline_service()
            server_extension = await self._runtime.get_server_extension(
                self._state.mode is AppMode.SERVER
            )
            await self._runtime.get_parrot_extension(self._state.mode is AppMode.PARROT)

            self._pipeline = pipeline

            async with TaskManager() as tasks:
                tasks.add_task(self._pipeline_loop())

                self._update_state(
                    status=AppStatus.RUNNING,
                    api_url=server_extension.docs_url,
                    profile_id=profile.id
                    if (profile := pipeline.active_profile) is not None
                    else None,
                    greeting_enabled=pipeline.options.greeting_enabled,
                    room_voice_enabled=pipeline.options.room_voice_enabled,
                    wakeword_enabled=pipeline.options.wakeword_enabled,
                )

                await shutdown_signal.wait()

    async def _pipeline_loop(self) -> None:
        if self._pipeline is None:
            return

        async for event in self._pipeline.subscribe_event():
            match event:
                case OptionsSetEvent():
                    self._update_state(
                        greeting_enabled=self._pipeline.options.greeting_enabled,
                        room_voice_enabled=self._pipeline.options.room_voice_enabled,
                        wakeword_enabled=self._pipeline.options.wakeword_enabled,
                    )

                case ProfileActivatedEvent(profile_id=profile_id):
                    self._update_state(profile_id=profile_id)
                case ProfileDeactivatedEvent():
                    self._update_state(profile_id=None)
                case _:
                    pass

            if self._window is not None:
                self._window.handle_event(event)

    def _pipeline_execute_command(self, cmd: PipelineCmd) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.execute_command(cmd),
            self._loop,
        )
