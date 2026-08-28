import asyncio
import atexit
import queue
import threading
from contextlib import suppress
from typing import Any

import rumps

from helomi_core import Runtime
from helomi_core.resources import LocalCatalog, LocalStore
from helomi_core.server import Server, ServerSettings
from helomi_core.speech import (
    ProfileActivated,
    ProfileDeactivated,
    SpeechEvent,
    TranscriptionReady,
)


def _cleanup_external_resources() -> None:
    """Shut down worker pools and run exit hooks before AppKit terminates."""
    with suppress(Exception):
        from joblib.externals.loky import get_reusable_executor

        get_reusable_executor().shutdown(wait=True, kill_workers=True)

    with suppress(Exception):
        atexit._run_exitfuncs()


class HelomiTrayApp(rumps.App):
    def __init__(
        self,
        local_catalog: LocalCatalog | None = None,
        config: ServerSettings | None = None,
        start_service: bool = True,
    ) -> None:
        super().__init__(name="Helomi", title="⏳ Helomi", quit_button=None)

        if local_catalog is None:
            local_catalog = LocalStore()

        self._local_catalog = local_catalog
        self._runtime = Runtime(local_catalog)
        self._config = config or self._runtime.settings.server
        self._service: Server = self._runtime.get_server(config=self._config)

        self._parrot_mode = False
        self._interactive_menu_enabled = False
        self._active_profile_id: str | None = None
        self._ui_queue: queue.Queue[SpeechEvent | None] = queue.Queue()

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._service_ready = threading.Event()

        self._profile_items: dict[str, rumps.MenuItem] = {}
        self._deactivate_item: rumps.MenuItem | None = None
        self._parrot_item: rumps.MenuItem | None = None
        self._setup_menu()

        self._timer = rumps.Timer(self._on_timer_tick, 0.2)
        self._timer.start()

        if start_service:
            self._start_service_thread()

    @property
    def config(self) -> ServerSettings:
        return self._config

    @property
    def parrot_mode(self) -> bool:
        return self._parrot_mode

    @property
    def interactive_menu_enabled(self) -> bool:
        return self._interactive_menu_enabled

    @property
    def active_profile_id(self) -> str | None:
        return self._active_profile_id

    @property
    def service(self) -> Server:
        return self._service

    @property
    def server(self) -> Server:
        return self._service

    def _setup_menu(self) -> None:
        # 1. Profiles Submenu
        profiles_menu = rumps.MenuItem("Profiles")
        for p_id, profile in self._runtime.profiles.items():
            item = rumps.MenuItem(title=profile.name, callback=self.on_select_profile)
            self._profile_items[p_id] = item
            profiles_menu.add(item)

        profiles_menu.add(rumps.separator)
        self._deactivate_item = rumps.MenuItem(
            title="No profile (Listening)", callback=self.on_deactivate_profile
        )
        profiles_menu.add(self._deactivate_item)

        # 2. Parrot mode item
        self._parrot_item = rumps.MenuItem(
            title="🦜 Parrot Mode", callback=self.on_toggle_parrot_mode
        )

        # 3. Server info & Quit items
        api_info = rumps.MenuItem(
            f"🌐 API: http://{self._config.host}:{self._config.port}"
        )
        quit_item = rumps.MenuItem("Quit", callback=self.on_quit)

        self.menu = [
            profiles_menu,
            self._parrot_item,
            rumps.separator,
            api_info,
            rumps.separator,
            quit_item,
        ]

        self._disable_interactive_menu_items()

    def _disable_interactive_menu_items(self) -> None:
        self._interactive_menu_enabled = False
        for item in self._profile_items.values():
            item.set_callback(None)
        if self._deactivate_item is not None:
            self._deactivate_item.set_callback(None)
        if self._parrot_item is not None:
            self._parrot_item.set_callback(None)

    def _enable_interactive_menu_items(self) -> None:
        self._interactive_menu_enabled = True
        for item in self._profile_items.values():
            item.set_callback(self.on_select_profile)
        if self._deactivate_item is not None:
            self._deactivate_item.set_callback(self.on_deactivate_profile)
        if self._parrot_item is not None:
            self._parrot_item.set_callback(self.on_toggle_parrot_mode)

    def _start_service_thread(self) -> None:
        thread = threading.Thread(
            target=self._run_service_loop,
            daemon=True,
            name="helomi-tray-speech",
        )
        self._thread = thread
        thread.start()

    def _run_service_loop(self) -> None:
        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)

        self._loop = loop
        self._shutdown_event = asyncio.Event()
        self._service.add_listener(self._on_service_event)

        async def _runner() -> None:
            async with self._service:
                self._service_ready.set()
                # Signal ready to UI
                self._ui_queue.put(None)
                if self._shutdown_event is not None:
                    await self._shutdown_event.wait()

        try:
            loop.run_until_complete(_runner())
        finally:
            loop.close()

    def _on_service_event(self, event: SpeechEvent) -> None:
        self._ui_queue.put(event)

    def _on_timer_tick(self, _sender: Any = None) -> None:
        while not self._ui_queue.empty():
            try:
                event = self._ui_queue.get_nowait()
                self._handle_event(event)
            except queue.Empty:
                break

    def _handle_event(self, event: SpeechEvent | None) -> None:
        if not self._interactive_menu_enabled:
            self._enable_interactive_menu_items()

        match event:
            case None:
                self._update_profile_checkmarks()
                self._update_title()

            case ProfileActivated(profile_id=pid):
                self._active_profile_id = pid
                self._update_profile_checkmarks()
                self._update_title()

            case ProfileDeactivated():
                self._active_profile_id = None
                self._update_profile_checkmarks()
                self._update_title()

            case TranscriptionReady(text=text):
                if self._parrot_mode and text.strip():
                    self._trigger_parrot_say(text.strip())

    def _trigger_parrot_say(self, text: str) -> None:
        if self._loop and not self._loop.is_closed():
            profile_id = (
                self._active_profile_id or self._runtime.settings.profile.default
            )
            asyncio.run_coroutine_threadsafe(
                self._service.say_text(text, profile_id),
                self._loop,
            )

    def _update_profile_checkmarks(self) -> None:
        for p_id, item in self._profile_items.items():
            item.state = 1 if p_id == self._active_profile_id else 0
        if self._deactivate_item is not None:
            self._deactivate_item.state = 1 if self._active_profile_id is None else 0

    def _update_title(self) -> None:
        if self._active_profile_id:
            profile = self._runtime.profiles.get(self._active_profile_id)
            name = profile.name if profile else self._active_profile_id
            prefix = "🦜" if self._parrot_mode else "🟢"
            self.title = f"{prefix} {name}"
        else:
            prefix = "🦜" if self._parrot_mode else "👂"
            self.title = f"{prefix} Helomi"

    def on_select_profile(self, sender: rumps.MenuItem) -> None:
        for p_id, item in self._profile_items.items():
            if item is sender:
                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._service.activate_profile(p_id),
                        self._loop,
                    )
                break

    def on_deactivate_profile(self, _sender: rumps.MenuItem) -> None:
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self._service.deactivate_profile(),
                self._loop,
            )

    def on_toggle_parrot_mode(self, sender: rumps.MenuItem) -> None:
        self._parrot_mode = not self._parrot_mode
        sender.state = 1 if self._parrot_mode else 0
        self._update_title()

    def on_quit(self, _sender: Any = None) -> None:
        self.title = "⏳ Quitting..."
        self._disable_interactive_menu_items()
        if self._timer is not None:
            self._timer.stop()

        if self._loop and self._shutdown_event and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown_event.set)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        _cleanup_external_resources()
        rumps.quit_application()
