import asyncio
import atexit
import threading
from contextlib import suppress
from dataclasses import dataclass, field, replace
from enum import StrEnum, auto
from pathlib import Path
from typing import ClassVar, TypedDict, Unpack

import rumps

from helomi_common import BaseComponent, TaskManager
from helomi_core import Runtime
from helomi_core.audio import AudioFile, RawAudio
from helomi_core.parrot import ParrotExtension
from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    PipelineExtension,
    PipelineExtensionKey,
    PipelineService,
    ProfileActivated,
    ProfileDeactivated,
    SynthesisReady,
)
from helomi_core.server import ServerExtension


class TrayStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    QUITING = auto()


class TryIcon(StrEnum):
    START = "🚀️"
    PARROT = "🦜"
    RECORD = "🎙️"
    ROBOT = "🤖"
    API = "🌐"
    EAR = "👂"
    EXIT = "💤"


@dataclass(frozen=True, slots=True)
class TrayState:
    class Update(TypedDict, total=False):
        status: TrayStatus
        profile_id: str | None
        extension_key: PipelineExtensionKey
        is_recording: bool
        recording: list[RawAudio]
        server_url: str | None

    status: TrayStatus = TrayStatus.STARTING
    is_recording: bool = False
    recording: list[RawAudio] = field(default_factory=list)
    profile_id: str | None = None
    extension_key: PipelineExtensionKey = ServerExtension
    server_url: str | None = None


class TrayApp(rumps.App, BaseComponent):
    _TITLE: ClassVar[str] = "Helomi"

    @classmethod
    def _render_title(
        cls,
        icon: TryIcon | str,
        label: str | None = None,
    ) -> str:
        return f"{icon} {label or cls._TITLE}"

    def __init__(self, runtime: Runtime) -> None:
        rumps.App.__init__(
            self,
            name=self._TITLE,
            title=self._render_title(TryIcon.START),
            quit_button=None,
        )
        BaseComponent.__init__(self)

        self._runtime = runtime

        self._pipeline: PipelineService | None = None

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._ready_signal: asyncio.Event | None = None
        self._shutdown_signal: asyncio.Event | None = None

        self._state = TrayState()
        self._last_state = TrayState()

        # menu

        self._menu_profiles: dict[str, rumps.MenuItem] = {
            profile.id: rumps.MenuItem(
                title=profile.name,
                key=str(index) if index < 9 else None,
            )
            for index, profile in enumerate(runtime.profiles)
        }

        menu_server = rumps.MenuItem(
            title=self._render_title(TryIcon.API, "API Disabled"),
            key="a",
        )
        menu_parrot = rumps.MenuItem(
            title=self._render_title(TryIcon.PARROT, "Parrot Mode"),
            key="p",
        )

        self._menu_recording = rumps.MenuItem(
            title="Recording",
            key="r",
        )

        self._menu_save = rumps.MenuItem(
            title="Save As …",
            key="s",
        )

        self._menu_extensions: dict[PipelineExtensionKey, rumps.MenuItem] = {
            ServerExtension: menu_server,
            ParrotExtension: menu_parrot,
        }

        menu_profiles = rumps.MenuItem(
            title="Profiles",
        )
        for menu_item in self._menu_profiles.values():
            menu_profiles.add(menu_item)

        self.menu = [
            menu_profiles,
            rumps.separator,
            menu_server,
            menu_parrot,
            rumps.separator,
            self._menu_recording,
            self._menu_save,
            rumps.separator,
            rumps.MenuItem(
                title="Quit",
                callback=self._handle_quit,
                key="q",
            ),
        ]

        self._lock = threading.Lock()

    def run(self, **options) -> None:
        self._before_run()
        super().run(**options)

    def quit(self) -> None:
        self._handle_quit(None)

    @rumps.timer(0.5)
    def _sync_ui(self, _):
        if self._last_state != self._state:
            last_state, self._last_state = self._last_state, self._state

            match self._state.status:
                case TrayStatus.RUNNING:
                    if last_state.status == TrayStatus.STARTING:
                        self._sync_menu(True)
                        self._sync_extension(self._state.extension_key, True)

                    if last_state.server_url != self._state.server_url:
                        title = self._render_title(
                            TryIcon.API,
                            self._state.server_url or "Disabled",
                        )
                        self._menu_extensions[ServerExtension].title = title

                    if last_state.extension_key is not self._state.extension_key:
                        self._sync_extension(last_state.extension_key, False)
                        self._sync_extension(self._state.extension_key, True)

                    if last_state.profile_id != self._state.profile_id:
                        self._sync_profile(last_state.profile_id, False)
                        self._sync_profile(self._state.profile_id, True)

                    self._sync_recording()
                    self._sync_title()

                case TrayStatus.QUITING:
                    if last_state.status == TrayStatus.RUNNING:
                        self._sync_menu(False)
                    self.title = self._render_title(TryIcon.EXIT)

    def _sync_menu(self, enabled: bool) -> None:
        extension_callback = self._handle_toggle_extension if enabled else None
        profile_callback = self._handle_toggle_profile if enabled else None

        for menu_item in self._menu_profiles.values():
            menu_item.set_callback(profile_callback)
        for menu_item in self._menu_extensions.values():
            menu_item.set_callback(extension_callback)

        if not enabled:
            self._menu_recording.state = 0
            self._menu_recording.set_callback(None)
            self._menu_save.set_callback(None)
        else:
            self._menu_recording.set_callback(self._handle_toggle_recording)

    def _sync_title(self) -> None:
        profile = (
            self._runtime.profiles.get(self._state.profile_id)
            if self._state.profile_id
            else None
        )

        if profile is None:
            icon = TryIcon.EAR
            label = None
        else:
            icon = profile.emoji if profile.emoji else TryIcon.ROBOT
            label = profile.name
            if self._state.extension_key is ParrotExtension:
                label = f"{label} {TryIcon.PARROT}"
            if self._state.is_recording:
                label = f"{label} {TryIcon.RECORD}"

        self.title = self._render_title(icon, label)

    def _sync_recording(self) -> None:
        self._menu_recording.state = 1 if self._state.is_recording else 0
        self._menu_save.set_callback(
            self._handle_save if self._state.recording else None
        )

    def _sync_extension(
        self,
        extension_key: type[PipelineExtension],
        active: bool,
    ) -> None:
        self._menu_extensions[extension_key].state = 1 if active else 0
        self._menu_extensions[extension_key].set_callback(
            self._handle_toggle_extension if not active else None
        )

    def _sync_profile(self, profile_id: str | None, active: bool) -> None:
        if profile_id is None:
            return
        self._menu_profiles[profile_id].state = 1 if active else 0

    def _handle_toggle_profile(self, sender: rumps.MenuItem):
        if sender.state == 1:
            self._pipeline_execute_command(DeactivateProfile())
            return

        for profile_id, menu_item in self._menu_profiles.items():
            if menu_item is sender:
                self._pipeline_execute_command(ActivateProfile(profile_id=profile_id))
                return

    def _handle_toggle_extension(self, sender: rumps.MenuItem):
        if self._loop is None:
            return

        for extension_key, menu_item in self._menu_extensions.items():
            if menu_item is sender:
                self._pipeline_set_activate_extension(extension_key)
                self._update_state(
                    extension_key=extension_key,
                )
                return

    def _handle_toggle_recording(self, _: rumps.MenuItem):
        if self._state.is_recording:
            self._update_state(is_recording=False)
        else:
            self._update_state(is_recording=True, recording=[])

    def _handle_save(self, _: rumps.MenuItem):
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
        self._update_state(status=TrayStatus.QUITING, force_sync=True)
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

    def _update_state(
        self,
        force_sync=False,
        audio: RawAudio | None = None,
        **kwargs: Unpack[TrayState.Update],
    ) -> None:
        if self._state.status == TrayStatus.QUITING:
            return

        with self._lock:
            if audio is not None and self._state.is_recording:
                kwargs["recording"] = [*self._state.recording, audio]

            self._state = replace(self._state, **kwargs)

            if force_sync:
                self._sync_ui(None)

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
        except Exception:
            self._logger.exception("Error in TrayApp runtime loop")
        finally:
            with suppress(Exception):
                loop.close()

    async def _runtime_loop(self) -> None:
        self._shutdown_signal = (shutdown_signal := asyncio.Event())

        async with self._runtime:
            pipeline = await self._runtime.get_pipeline_service()
            server_extension = await self._runtime.get_server_extension(
                self._state.extension_key is ServerExtension
            )
            await self._runtime.get_parrot_extension(
                self._state.extension_key is ParrotExtension
            )

            self._pipeline = pipeline

            async with TaskManager() as tasks:
                tasks.add_task(self._pipeline_loop())

                self._update_state(
                    status=TrayStatus.RUNNING,
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
                case SynthesisReady(audio=audio):
                    self._update_state(audio=audio)

    def _pipeline_set_activate_extension(self, key: PipelineExtensionKey) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.set_active_extension(key),
            self._loop,
        )

    def _pipeline_execute_command(self, cmd: PipelineCmd) -> None:
        if self._pipeline is None or self._loop is None or self._loop.is_closed():
            return

        asyncio.run_coroutine_threadsafe(
            self._pipeline.execute_command(cmd),
            self._loop,
        )
