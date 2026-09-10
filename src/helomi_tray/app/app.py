import asyncio
import atexit
import threading
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import ClassVar, Unpack

import rumps

from helomi_common import BaseComponent, TaskManager
from helomi_core import Runtime
from helomi_core.audio import AudioFile, RawAudio
from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    PipelineExtensionKey,
    PipelineService,
    ProfileActivated,
    ProfileDeactivated,
    SynthesisReady,
)
from helomi_core.server import ServerExtension

from .icons import AppIcon
from .state import AppState, AppStatus


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

        self._lock = threading.Lock()

        # menu

        self._menu_profiles: dict[str, rumps.MenuItem] = {
            profile.id: rumps.MenuItem(
                title=profile.name,
                key=str(index) if index < 9 else None,
            )
            for index, profile in enumerate(runtime.profiles)
        }

        self._menu_server = rumps.MenuItem(
            title="Starting Server",
        )
        self._menu_parrot = rumps.MenuItem(
            title="Parrot Mode",
            key="p",
        )
        self._menu_recording = rumps.MenuItem(
            title="Recording",
            key="r",
        )
        self._menu_save_recording = rumps.MenuItem(
            title="Save As …",
            key="s",
        )

        menu_profiles = rumps.MenuItem(
            title="Profiles",
        )
        for menu_item in self._menu_profiles.values():
            menu_profiles.add(menu_item)

        self.menu = [
            menu_profiles,
            rumps.separator,
            self._menu_parrot,
            rumps.separator,
            self._menu_server,
            rumps.separator,
            self._menu_recording,
            self._menu_save_recording,
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
                    self._menu_parrot.set_callback(self._handle_toggle_parrot)
                    self._menu_recording.set_callback(self._handle_toggle_recording)

                    for menu_item in self._menu_profiles.values():
                        menu_item.state = 0
                        menu_item.set_callback(self._handle_toggle_profile)

                if last_state.active_profile != self._state.active_profile:
                    if last_state.active_profile:
                        self._menu_profiles[last_state.active_profile].state = 0

                    if self._state.active_profile:
                        self._menu_profiles[self._state.active_profile].state = 1

                self._menu_server.title = (
                    f"API: {self._state.server_url}"
                    if self._state.active_extension is ServerExtension
                    and self._state.server_url
                    else "API Disabled"
                )
                self._menu_parrot.state = (
                    1 if self._state.active_extension is ParrotExtension else 0
                )
                self._menu_recording.state = (
                    1 if self._state.recording is not None else 0
                )
                self._menu_save_recording.set_callback(
                    self._handle_save_recording if self._state.recording else None
                )

                profile = (
                    self._runtime.profiles.get(self._state.active_profile)
                    if self._state.active_profile
                    else None
                )

                label = profile.name if profile else self._TITLE

                if not profile:
                    icon = AppIcon.EAR
                else:
                    if self._state.active_extension is ParrotExtension:
                        icon = AppIcon.PARROT
                    else:
                        icon = profile.emoji or AppIcon.PROFILE

                title = f"{icon} {label}"

                if self._state.recording is not None:
                    title = f"{title} {AppIcon.RECORDING}"

                self.title = title

            case AppStatus.QUITING:
                if last_state.status == AppStatus.RUNNING:
                    self._menu_server.title = "Stopping Server"
                    self._menu_parrot.state = 0
                    self._menu_parrot.set_callback(None)
                    self._menu_recording.state = 0
                    self._menu_recording.set_callback(None)
                    self._menu_save_recording.set_callback(None)

                    for menu_item in self._menu_profiles.values():
                        menu_item.state = 0
                        menu_item.set_callback(None)

                self.title = f"{AppIcon.QUITING} {self._TITLE}"

    def _update_state(
        self,
        force_sync=False,
        enabled_recording: bool | None = None,
        recording_chunk: RawAudio | None = None,
        **kwargs: Unpack[AppState.Update],
    ) -> None:
        if self._state.status == AppStatus.QUITING:
            return

        with self._lock:
            if enabled_recording is not None:
                kwargs["recording"] = [] if enabled_recording else None

            if recording_chunk is not None and self._state.recording is not None:
                kwargs["recording"] = [*self._state.recording, recording_chunk]

            self._state = replace(self._state, **kwargs)

            if force_sync:
                self._sync_state(None)

    def _handle_toggle_profile(self, sender: rumps.MenuItem):
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

    def _handle_toggle_parrot(self, sender: rumps.MenuItem):
        match sender.state:
            case 1:
                self._set_activate_extension(ServerExtension)
            case 0:
                self._set_activate_extension(ParrotExtension)

    def _handle_toggle_recording(self, sender: rumps.MenuItem):
        match sender.state:
            case 1:
                self._update_state(recording=None)
            case 0:
                self._update_state(recording=[])

    def _handle_save_recording(self, _: rumps.MenuItem):
        if not self._state.recording:
            return

        # noinspection PyUnresolvedReferences
        from AppKit import NSApp, NSModalResponseOK, NSSavePanel

        NSApp.setActivationPolicy_(0)
        NSApp.activateIgnoringOtherApps_(True)

        panel = NSSavePanel.savePanel()
        panel.setFloatingPanel_(True)
        panel.orderFrontRegardless()
        panel.setTitle_("Save Recording")
        panel.setNameFieldStringValue_("recording.wav")
        panel.setCanCreateDirectories_(True)
        panel.setAllowedFileTypes_(["wav", "wave"])
        panel.center()

        response = panel.runModal()
        if response != NSModalResponseOK:
            return

        recording = self._state.recording
        self._update_state(recording=[])

        path: str = panel.URL().path()

        with suppress(Exception):
            AudioFile(Path(path)).write(RawAudio.concat(recording))

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

        if self._loop and self._shutdown_signal and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_signal.set)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        with suppress(Exception):
            from joblib.externals.loky import get_reusable_executor

            get_reusable_executor().shutdown(wait=True, kill_workers=True)

        with suppress(Exception):
            atexit._run_exitfuncs()
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
                self._state.active_extension is ServerExtension
            )
            await self._runtime.get_parrot_extension(
                self._state.active_extension is ParrotExtension
            )

            self._pipeline = pipeline

            async with TaskManager() as tasks:
                tasks.add_task(self._pipeline_loop())

                self._update_state(
                    status=AppStatus.RUNNING,
                    server_url=server_extension.url,
                    active_profile=profile.id
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
                    self._update_state(active_profile=profile_id)
                case ProfileDeactivated():
                    self._update_state(active_profile=None)
                case SynthesisReady(audio=audio):
                    self._update_state(recording_chunk=audio)

    def _set_activate_extension(self, extension: PipelineExtensionKey) -> None:
        self._update_state(active_extension=extension)

        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.set_active_extension(extension),
            self._loop,
        )

    def _pipeline_execute_command(self, cmd: PipelineCmd) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.execute_command(cmd),
            self._loop,
        )
