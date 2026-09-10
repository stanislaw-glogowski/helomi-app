import asyncio
import threading
from contextlib import suppress
from dataclasses import replace
from typing import Any, ClassVar, Unpack

import rumps

from helomi_common import BaseComponent, TaskManager
from helomi_core import Runtime
from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    PipelineExtensionKey,
    PipelineOptions,
    PipelineService,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
)
from helomi_core.server import ServerExtension

from .icons import AppIcon
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
        self._current_window: BaseWindow | None = None
        self._previous_mode: AppMode = AppMode.SERVER

        self._lock = threading.Lock()

        with suppress(Exception):
            import AppKit

            AppKit.NSApplication.sharedApplication().setActivationPolicy_(
                AppKit.NSApplicationActivationPolicyAccessory
            )

        # menu

        self._menu_profiles: dict[str, rumps.MenuItem] = {
            profile.id: rumps.MenuItem(
                title=profile.name,
                key=str(index) if index < 9 else None,
            )
            for index, profile in enumerate(runtime.profiles)
        }

        self._menu_tts = rumps.MenuItem(
            title="Text-to-Speech",
            key="t",
        )
        self._menu_parrot = rumps.MenuItem(
            title="Parrot Mode",
            key="p",
        )
        self._menu_server = rumps.MenuItem(
            title="Starting Server",
        )

        self._menu_room_voice = rumps.MenuItem(
            title="Room Voice",
        )
        self._menu_wake_word = rumps.MenuItem(
            title="Wake Word",
        )

        menu_profiles = rumps.MenuItem(
            title="Profiles",
        )
        self._menu_settings = rumps.MenuItem(
            title="Settings",
        )
        for menu_item in self._menu_profiles.values():
            menu_profiles.add(menu_item)
        self._menu_settings.add(self._menu_room_voice)
        self._menu_settings.add(self._menu_wake_word)

        self.menu = [
            menu_profiles,
            rumps.separator,
            self._menu_tts,
            self._menu_parrot,
            rumps.separator,
            self._menu_settings,
            rumps.separator,
            self._menu_server,
            rumps.separator,
            rumps.MenuItem(
                title="Quit",
                callback=self._handle_quit,
                key="q",
            ),
        ]

    def run(self, **options) -> None:
        self._before_run()
        super().run(**options)

    def quit(self) -> None:
        self._handle_quit(None)

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
                if last_state.status == AppStatus.STARTING:
                    self._menu_parrot.set_callback(self._handle_parrot_toggle)
                    self._menu_tts.set_callback(self._handle_tts_open)
                    self._menu_room_voice.state = 1 if self._state.room_voice else 0
                    self._menu_room_voice.set_callback(self._handle_room_voice_toggle)
                    self._menu_wake_word.state = 1 if self._state.wake_word else 0
                    self._menu_wake_word.set_callback(self._handle_wake_word_toggle)

                    for menu_item in self._menu_profiles.values():
                        menu_item.state = 0
                        menu_item.set_callback(self._handle_profile_toggle)

                if last_state.profile_id != self._state.profile_id:
                    if last_state.profile_id:
                        self._menu_profiles[last_state.profile_id].state = 0

                    if self._state.profile_id:
                        self._menu_profiles[self._state.profile_id].state = 1

                self._menu_server.title = (
                    f"API: {self._state.server_url}"
                    if self._state.mode == AppMode.SERVER and self._state.server_url
                    else "API Disabled"
                )
                self._menu_parrot.state = 1 if self._state.mode is AppMode.PARROT else 0

                if self._state.mode == AppMode.TTS:
                    self._menu_room_voice.state = 0
                    self._menu_wake_word.state = 0
                    self._menu_room_voice.set_callback(None)
                    self._menu_wake_word.set_callback(None)
                else:
                    self._menu_room_voice.state = 1 if self._state.room_voice else 0
                    self._menu_wake_word.state = 1 if self._state.wake_word else 0
                    self._menu_room_voice.set_callback(self._handle_room_voice_toggle)
                    self._menu_wake_word.set_callback(self._handle_wake_word_toggle)

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
                    icon = profile.emoji or AppIcon.PROFILE
                else:
                    icon = AppIcon.EAR

                self.title = f"{icon} {label}"

            case AppStatus.QUITING:
                if last_state.status == AppStatus.RUNNING:
                    self._menu_server.title = "Stopping Server"
                    self._menu_parrot.state = 0
                    self._menu_parrot.set_callback(None)
                    self._menu_tts.set_callback(None)
                    self._menu_room_voice.set_callback(None)
                    self._menu_wake_word.set_callback(None)

                    for menu_item in self._menu_profiles.values():
                        menu_item.state = 0
                        menu_item.set_callback(None)

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
        ext: PipelineExtensionKey | None
        match mode:
            case AppMode.SERVER:
                ext = ServerExtension
            case AppMode.PARROT:
                ext = ParrotExtension
            case AppMode.TTS:
                ext = None

        self._update_state(mode=mode)

        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.set_active_extension(ext),
            self._loop,
        )

    def _open_window(self, window: BaseWindow, mode: AppMode) -> None:
        if self._current_window is not None and self._current_window is not window:
            self._current_window.close()

        if self._state.mode != mode:
            self._previous_mode = self._state.mode
            self._set_mode(mode)

        self._current_window = window
        window.show()

    def _handle_tts_open(self, _: rumps.MenuItem | None = None) -> None:
        if isinstance(self._current_window, TTSWindow):
            self._current_window.activate()
            return

        window = TTSWindow(
            on_send=self._handle_tts_send,
            on_close=self._handle_tts_close,
            get_profile_id=lambda: self._state.profile_id,
        )
        self._open_window(window, AppMode.TTS)

    def _handle_tts_close(self) -> None:
        self._current_window = None
        self._set_mode(self._previous_mode)

    def _handle_tts_send(self, text: str) -> None:
        self._pipeline_execute_command(
            SayText(text=text, profile_id=self._state.profile_id)
        )

    def _handle_profile_toggle(self, sender: rumps.MenuItem) -> None:
        match sender.state:
            case 1:
                self._pipeline_execute_command(DeactivateProfile())
            case 0:
                for profile_id, menu_item in self._menu_profiles.items():
                    if menu_item is sender:
                        self._pipeline_execute_command(
                            ActivateProfile(profile_id=profile_id)
                        )
                        return

    def _handle_parrot_toggle(self, sender: rumps.MenuItem) -> None:
        if self._current_window is not None:
            self._current_window.close()
            self._current_window = None

        match sender.state:
            case 1:
                self._set_mode(AppMode.SERVER)
            case 0:
                self._set_mode(AppMode.PARROT)

    def _handle_room_voice_toggle(self, sender: rumps.MenuItem) -> None:
        new_val = not (sender.state == 1)
        self._update_state(room_voice=new_val)
        self._pipeline_set_option("room_voice", new_val)

    def _handle_wake_word_toggle(self, sender: rumps.MenuItem) -> None:
        new_val = not (sender.state == 1)
        self._update_state(wake_word=new_val)
        self._pipeline_set_option("wake_word", new_val)

    def _handle_quit(self, sender: rumps.MenuItem | None = None) -> None:
        if sender is not None:
            sender.set_callback(None)

        self._update_state(
            status=AppStatus.QUITING,
            force_sync=True,
        )
        rumps.Timer(self._handle_exit, 0.1).start()

    def _handle_exit(self, sender: rumps.Timer) -> None:
        sender.stop()

        if self._current_window is not None:
            self._current_window.close()
            self._current_window = None

        self._menu_room_voice.set_callback(None)
        self._menu_wake_word.set_callback(None)

        if self._loop and self._shutdown_signal and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_signal.set)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        rumps.quit_application()

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

            if hasattr(pipeline, "options") and isinstance(
                pipeline.options, PipelineOptions
            ):
                if self._state.room_voice != pipeline.options.room_voice:
                    await pipeline.set_option("room_voice", self._state.room_voice)
                if self._state.wake_word != pipeline.options.wake_word:
                    await pipeline.set_option("wake_word", self._state.wake_word)

            async with TaskManager() as tasks:
                tasks.add_task(self._pipeline_loop())

                self._update_state(
                    status=AppStatus.RUNNING,
                    server_url=server_extension.url,
                    profile_id=profile.id
                    if (profile := pipeline.active_profile) is not None
                    else None,
                )

                await shutdown_signal.wait()

    async def _pipeline_loop(self) -> None:
        if self._pipeline is None:
            return

        async for event in self._pipeline.subscribe_event():
            match event:
                case ProfileActivated(profile_id=profile_id):
                    self._update_state(profile_id=profile_id)
                case ProfileDeactivated():
                    self._update_state(profile_id=None)
                case _:
                    pass

            if self._current_window is not None:
                self._current_window.handle_event(event)

    def _pipeline_execute_command(self, cmd: PipelineCmd) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.execute_command(cmd),
            self._loop,
        )

    def _pipeline_set_option(self, key: str, value: Any) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.set_option(key, value),
            self._loop,
        )
