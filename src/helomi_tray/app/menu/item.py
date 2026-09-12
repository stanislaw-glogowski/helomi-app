from collections.abc import Callable
from typing import Any

import rumps


class MenuItem(rumps.MenuItem):
    def __init__(
        self,
        title: str,
        callback: Callable[..., Any],
        key: str | None = None,
        id: str | None = None,
        checked: bool = False,
        enabled: bool = False,
    ) -> None:
        super().__init__(
            title=title,
            key=key,
        )
        self._id = id
        self._callback = lambda _: callback(self)
        self._enabled = enabled
        if enabled:
            self.set_callback(self._callback)

        if checked:
            self.state = 1

    @property
    def id(self) -> str:
        if self._id is None:
            raise ValueError("Menu item has no id")
        return self._id

    @property
    def checked(self) -> bool:
        return self.state == 1

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_checked(self, checked: bool | None) -> bool:
        if checked is None:
            checked = not self.checked
        elif checked == self.checked:
            return self.checked

        self.state = 1 if checked else 0

        return checked

    def set_enabled(self, enabled: bool | None = True) -> bool:
        if enabled is None:
            enabled = not self._enabled
        elif enabled == self._enabled:
            return self._enabled

        self._enabled = enabled

        if enabled:
            self.set_callback(self._callback)
        else:
            self.set_callback(None)

        return enabled
