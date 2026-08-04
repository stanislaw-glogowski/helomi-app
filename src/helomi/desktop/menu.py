from __future__ import annotations

import threading

from .runtime import DesktopRuntime
from .state import DesktopMode, DesktopSnapshot


class MenuBarApp:
    def __init__(self) -> None:
        import rumps

        self._rumps = rumps
        self._runtime = DesktopRuntime()
        self._snapshot = DesktopSnapshot(DesktopMode.READY, detail="Loading profiles…")
        self._quit_requested = False
        self._app = rumps.App("Helomi", quit_button=None)
        self._timer = rumps.Timer(self._drain_updates, 0.1)

    def run(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Helomi desktop must run on the macOS main thread")
        self._runtime.start()
        self._timer.start()
        self._render()
        self._app.run()

    def _drain_updates(self, _timer: object) -> None:
        if snapshot := self._runtime.drain():
            self._snapshot = snapshot
            self._render()
        if self._quit_requested and self._runtime.terminated:
            self._runtime.join()
            self._rumps.quit_application()

    def _render(self) -> None:
        rumps = self._rumps
        snapshot = self._snapshot
        status = rumps.MenuItem(snapshot.mode.value)
        status.set_callback(None)
        if snapshot.detail:
            detail = rumps.MenuItem(snapshot.detail)
            detail.set_callback(None)
        else:
            detail = None

        profiles = rumps.MenuItem("Profiles")
        for entry in snapshot.profiles:
            title = entry.name
            if entry.id == snapshot.default_profile_id:
                title += " (default)"
            if entry.profile is None:
                title += " — unavailable"
            item = rumps.MenuItem(title)
            item.state = entry.id == snapshot.selected_profile_id
            item.set_callback(
                self._select_profile(entry.id)
                if entry.profile is not None and snapshot.profiles_enabled
                else None
            )
            profiles.add(item)

        items: list[object] = [status]
        if detail is not None:
            items.append(detail)
        items.append(profiles)
        if snapshot.retry_enabled:
            retry = rumps.MenuItem("Retry")
            retry.set_callback(
                lambda _: self._runtime.start_profile(
                    snapshot.selected_profile_id or "", retry=True
                )
            )
            items.append(retry)
        items.extend([None, rumps.MenuItem("Quit Helomi", callback=self._quit)])
        self._app.menu.clear()
        self._app.menu.update(items)

    def _select_profile(self, profile_id: str):
        return lambda _: self._runtime.start_profile(profile_id)

    def _quit(self, _item: object) -> None:
        if self._quit_requested:
            return
        self._quit_requested = True
        self._runtime.shutdown()
