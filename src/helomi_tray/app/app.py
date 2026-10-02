import asyncio
import threading
import webbrowser
from concurrent.futures import Future
from contextlib import suppress
from dataclasses import replace
from typing import ClassVar, Unpack

import PyObjCTools.AppHelper
import rumps

from helomi_app import (
    ActivateProfileCommand,
    ActivationSource,
    Application,
    ApplicationCommand,
    CallEndedEvent,
    CallStartedEvent,
    ConversationOptionsChangedEvent,
    ConversationStateChangedEvent,
    DeactivateProfileCommand,
    DriverChangedEvent,
    EndConversationCommand,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    ResponseMode,
    ResponseModeChangedEvent,
    SayTextCommand,
    SetConversationOptionsCommand,
    SetMonitoringCommand,
    SetResponseModeCommand,
    SwitchDriverCommand,
)

from .dialogs import ConfirmDialog
from .icons import AppIcon
from .menu import MenuGroup, MenuItem
from .state import TrayState, TrayStatus
from .windows import CallWindow, TTSWindow


class TrayApplication(rumps.App):
    """macOS tray client for the public Helomi application façade."""

    _TITLE: ClassVar[str] = "Helomi"

    def __init__(self, application: Application):
        super().__init__(name=self._TITLE, title=self._TITLE, quit_button=None)
        self._application = application
        settings = application.app_settings
        self._state = TrayState(
            response_mode=settings.response_mode,
            persistent_profile=settings.conversation.persistent_profile,
            reactions=settings.conversation.reactions,
            room_voice=settings.conversation.room_voice,
            wakeword=settings.conversation.wakeword,
            active_driver_id=application.settings.audio.initial_driver,
        )
        self._last_state = TrayState()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown_signal: asyncio.Event | None = None
        self._start_icon = AppIcon.Start()
        self._lock = threading.Lock()
        self._tts_window: TTSWindow | None = None
        self._call_window: CallWindow | None = None
        self._previous_mode = settings.response_mode

        with suppress(Exception):
            import AppKit

            AppKit.NSApplication.sharedApplication().setActivationPolicy_(
                AppKit.NSApplicationActivationPolicyAccessory
            )

        self._menu_profiles = MenuGroup(title="Profiles")
        for index, profile in enumerate(application.profiles):
            self._menu_profiles.add_action(
                MenuItem(
                    id=profile.id,
                    key=str(index + 1) if index < 9 else None,
                    title=profile.name,
                    callback=self._on_profile_click,
                    checked=False,
                )
            )

        self._menu_drivers = MenuGroup(title="Audio Driver")
        for driver_id in application.settings.audio.drivers:
            self._menu_drivers.add_action(
                MenuItem(
                    id=driver_id,
                    title=driver_id,
                    callback=self._on_driver_click,
                    checked=driver_id == self._state.active_driver_id,
                )
            )

        self._menu_modes = MenuGroup(title="Response Mode")
        for mode, title, key in (
            (ResponseMode.API, "API", "a"),
            (ResponseMode.PARROT, "Parrot", "p"),
        ):
            self._menu_modes.add_action(
                MenuItem(
                    id=mode.value,
                    title=title,
                    key=key,
                    callback=self._on_mode_click,
                    checked=mode == self._state.response_mode,
                )
            )

        self._menu_settings = MenuGroup(title="Settings")
        for option_id, title in (
            ("persistent_profile", "Persistent Profile"),
            ("wakeword", "Wake Word"),
            ("reactions", "Reactions"),
            ("room_voice", "Room Voice"),
        ):
            self._menu_settings.add_action(
                MenuItem(
                    id=option_id,
                    title=title,
                    callback=self._on_setting_click,
                )
            )

        self._menu_tts = MenuItem(
            id="tts_window",
            title="Text-to-Speech",
            key="t",
            callback=self._on_tts_click,
        )
        self._menu_server = MenuItem(
            id="api_docs",
            title="Starting API",
            callback=self._on_server_click,
        )
        self.menu = [
            self._menu_profiles,
            self._menu_drivers,
            rumps.separator,
            self._menu_tts,
            self._menu_modes,
            rumps.separator,
            self._menu_server,
            self._menu_settings,
            rumps.separator,
            rumps.MenuItem(title="Quit", callback=self._on_quit_click, key="q"),
        ]

    def run(self, **options):
        self._before_run()
        super().run(**options)

    def quit(self):
        self._on_quit_click(None)

    @rumps.timer(0.1)
    def _animate_start_icon(self, sender: rumps.Timer | None = None):
        if self._state.status != TrayStatus.STARTING:
            if sender:
                sender.stop()
            return
        self.title = f"{self._start_icon} {self._TITLE}"

    @rumps.timer(0.5)
    def _sync_state(self, _sender: rumps.Timer | None = None):
        state = self._state
        if self._call_window is not None:
            self._call_window.refresh_duration()
        if self._last_state == state:
            return
        previous, self._last_state = self._last_state, state

        if state.status == TrayStatus.QUITTING:
            self._menu_profiles.set_enabled(False)
            self._menu_drivers.set_enabled(False)
            self._menu_modes.set_enabled(False)
            self._menu_settings.set_enabled(False)
            self._menu_tts.set_enabled(False)
            self._menu_server.set_enabled(False)
            self.title = f"{AppIcon.QUITTING} {self._TITLE}"
            return
        if state.status != TrayStatus.RUNNING:
            return

        profile = (
            self._application.profiles.get(state.profile_id)
            if state.profile_id is not None
            else None
        )
        active_info = next(
            (
                driver_descriptor
                for driver_descriptor in state.driver_descriptors
                if driver_descriptor.id == state.active_driver_id
            ),
            None,
        )
        manual_profiles = bool(
            active_info and active_info.capabilities.manual_profile_selection
        )
        self._menu_profiles.set_enabled(manual_profiles)
        self._menu_drivers.set_enabled(True)
        self._menu_modes.set_enabled(True)
        self._menu_settings.set_enabled(True)
        self._menu_tts.set_enabled(profile is not None)

        for driver_descriptor in state.driver_descriptors:
            action = self._menu_drivers.get_action(driver_descriptor.id)
            action.title = driver_descriptor.name
            action.set_checked(driver_descriptor.id == state.active_driver_id)
            action.set_enabled(
                driver_descriptor.id == state.active_driver_id
                or driver_descriptor.capabilities.manual_profile_selection
            )

        for mode in (ResponseMode.API, ResponseMode.PARROT):
            self._menu_modes.get_action(mode.value).set_checked(
                state.response_mode == mode
            )

        for option in (
            "persistent_profile",
            "wakeword",
            "reactions",
            "room_voice",
        ):
            action = self._menu_settings.get_action(option)
            action.set_checked(getattr(state, option))
            if option == "room_voice":
                action.set_enabled(
                    bool(
                        profile
                        and profile.has_room_voice
                        and active_info
                        and active_info.capabilities.room_voice
                    )
                )
            elif option == "wakeword":
                action.set_enabled(
                    self._application.settings.detection.wakeword is not None
                )
            else:
                action.set_enabled(True)

        if previous.profile_id != state.profile_id:
            if previous.profile_id is not None:
                self._menu_profiles.get_action(previous.profile_id).set_checked(False)
            if state.profile_id is not None:
                self._menu_profiles.get_action(state.profile_id).set_checked(True)

        mode_icon = {
            ResponseMode.API: None,
            ResponseMode.PARROT: AppIcon.PARROT_MODE,
            ResponseMode.OPERATOR: AppIcon.TTS_MODE,
        }[state.response_mode]
        if state.remote_session:
            icon = mode_icon or AppIcon.PHONE_ACTIVE
        elif mode_icon:
            icon = mode_icon
        elif profile:
            icon = profile.emoji
        elif state.wakeword:
            icon = AppIcon.WAKEWORD_ACTIVE
        else:
            icon = AppIcon.WAKEWORD_IDLE
        label = profile.name if profile else self._TITLE
        self.title = f"{icon} {label}"
        if profile and state.room_voice and profile.has_room_voice:
            self.title = f"{self.title} {AppIcon.ROOM_VOICE}"

        self._menu_server.title = (
            "API Documentation" if state.api_url else "API Unavailable"
        )
        self._menu_server.set_enabled(state.api_url is not None)

    def _update_state(self, **kwargs: Unpack[TrayState.Update]):
        if self._state.status == TrayStatus.QUITTING:
            return
        with self._lock:
            self._state = replace(self._state, **kwargs)

    def _on_profile_click(self, sender: MenuItem):
        command: ApplicationCommand
        if sender.checked:
            command = DeactivateProfileCommand()
        else:
            command = ActivateProfileCommand(
                profile_id=sender.id,
                source=ActivationSource.TRAY,
            )
        self._execute(command)

    def _on_driver_click(self, sender: MenuItem):
        if sender.id == self._state.active_driver_id:
            return
        end_remote = False
        if self._state.remote_session:
            end_remote = ConfirmDialog(
                "End active call?",
                "Switching the audio driver will end the current call.",
                "End Call and Switch",
            ).open()
            if not end_remote:
                return
        self._execute(
            SwitchDriverCommand(
                driver_id=sender.id,
                end_remote_session=end_remote,
            )
        )

    def _on_mode_click(self, sender: MenuItem):
        self._execute(SetResponseModeCommand(mode=ResponseMode(sender.id)))

    def _on_setting_click(self, sender: MenuItem):
        values: dict[str, bool] = {sender.id: not sender.checked}
        self._execute(SetConversationOptionsCommand(**values))  # type: ignore[arg-type]

    def _on_server_click(self, _sender: MenuItem):
        if self._state.api_url:
            webbrowser.open(self._state.api_url)

    def _on_tts_click(self, _sender: MenuItem | None = None):
        if self._tts_window is not None:
            self._tts_window.close()
            return
        self._previous_mode = self._state.response_mode
        self._execute(SetResponseModeCommand(mode=ResponseMode.OPERATOR))
        self._tts_window = TTSWindow(
            on_send=self._handle_tts_send,
            on_close=self._handle_tts_closed,
            get_profile_id=lambda: self._state.profile_id,
        )
        self._tts_window.show()

    def _handle_tts_closed(self):
        if self._tts_window is None:
            return
        self._tts_window = None
        self._execute(SetResponseModeCommand(mode=self._previous_mode))

    def _handle_tts_send(self, text: str):
        self._execute(
            SayTextCommand(
                text=text,
                mode=ResponseMode.OPERATOR,
                profile_id=self._state.profile_id,
            )
        )

    def _open_call_window(self, event: CallStartedEvent):
        if self._call_window is not None:
            self._call_window.close()
        profile = self._application.profiles.get(event.profile_id)
        if profile is None:
            raise RuntimeError(f"Profile not found: {event.profile_id}")
        self._call_window = CallWindow(
            caller=event.caller,
            profile_name=profile.name,
            response_mode=self._state.response_mode,
            monitoring=event.monitoring,
            on_monitoring_change=self._set_monitoring,
            on_open_tts=lambda: self._on_tts_click(None),
            on_end_call=self._end_call,
            on_close=self._handle_call_closed,
        )
        self._call_window.show()

    def _handle_call_closed(self):
        self._call_window = None

    def _set_monitoring(self, enabled: bool):
        self._update_state(monitoring=enabled)
        self._execute(SetMonitoringCommand(enabled=enabled))

    def _end_call(self):
        self._execute(EndConversationCommand())

    def _on_quit_click(self, sender: rumps.MenuItem | None = None):
        if sender is not None:
            sender.set_callback(None)
        with self._lock:
            self._state = replace(self._state, status=TrayStatus.QUITTING)
        self._sync_state(None)
        rumps.Timer(self._handle_exit, 0.1).start()

    def _handle_exit(self, sender: rumps.Timer):
        sender.stop()
        if self._tts_window is not None:
            self._tts_window.deactivate()
            self._tts_window = None
        if self._call_window is not None:
            self._call_window.deactivate()
            self._call_window = None
        if self._loop and self._shutdown_signal and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_signal.set)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        rumps.quit_application()

    def _before_run(self):
        self._thread = threading.Thread(
            target=self._thread_worker,
            daemon=True,
            name="helomi-tray-runtime",
        )
        self._thread.start()

    def _thread_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._runtime_loop())
        except asyncio.CancelledError, KeyboardInterrupt:
            pass
        finally:
            with suppress(Exception):
                loop.close()

    async def _runtime_loop(self):
        self._shutdown_signal = asyncio.Event()
        async with self._application:
            router = self._application.audio_router
            options = self._application.options
            self._update_state(
                status=TrayStatus.RUNNING,
                response_mode=self._application.response_mode,
                conversation_state=self._application.state,
                profile_id=(
                    profile.id
                    if (profile := self._application.active_profile) is not None
                    else None
                ),
                api_url=(
                    self._application.server.docs_url
                    if self._application.server is not None
                    else None
                ),
                persistent_profile=options.persistent_profile,
                reactions=options.reactions,
                room_voice=options.room_voice,
                wakeword=options.wakeword,
                active_driver_id=router.active_driver_id,
                driver_descriptors=router.driver_descriptors,
                remote_session=router.is_remote_session,
                monitoring=router.monitoring_enabled,
            )
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._event_loop())
                await self._shutdown_signal.wait()

    async def _event_loop(self):
        async for event in self._application.subscribe_events():
            match event:
                case ProfileActivatedEvent(profile_id=profile_id):
                    self._update_state(profile_id=profile_id)
                case ProfileDeactivatedEvent():
                    self._update_state(profile_id=None)
                case DriverChangedEvent(driver_id=driver_id):
                    driver_descriptor = next(
                        driver_descriptor
                        for driver_descriptor in self._state.driver_descriptors
                        if driver_descriptor.id == driver_id
                    )
                    self._update_state(
                        active_driver_id=driver_id,
                        remote_session=driver_descriptor.capabilities.remote_session,
                    )
                case CallStartedEvent(monitoring=monitoring):
                    self._update_state(remote_session=True, monitoring=monitoring)
                    PyObjCTools.AppHelper.callAfter(self._open_call_window, event)
                case CallEndedEvent():
                    self._update_state(remote_session=False)
                    if self._call_window is not None:
                        PyObjCTools.AppHelper.callAfter(self._call_window.close)
                case ResponseModeChangedEvent(mode=mode):
                    self._update_state(response_mode=mode)
                case ConversationStateChangedEvent(state=state):
                    self._update_state(conversation_state=state)
                case ConversationOptionsChangedEvent() as options:
                    self._update_state(
                        persistent_profile=options.persistent_profile,
                        reactions=options.reactions,
                        room_voice=options.room_voice,
                        wakeword=options.wakeword,
                    )
            if self._tts_window is not None:
                PyObjCTools.AppHelper.callAfter(self._tts_window.handle_event, event)
            if self._call_window is not None:
                PyObjCTools.AppHelper.callAfter(self._call_window.handle_event, event)

    def _execute(self, command: ApplicationCommand) -> Future | None:
        if self._loop is None or self._loop.is_closed():
            return None
        return asyncio.run_coroutine_threadsafe(
            self._application.execute_command(command),
            self._loop,
        )
