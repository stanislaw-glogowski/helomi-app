from collections.abc import Callable
from typing import Any

from .item import MenuItem


class MenuAction(MenuItem):
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
            id=id,
            checked=checked,
        )
        self._callback = lambda _: callback(self)
        self._enabled = enabled

        if enabled:
            self.set_callback(self._callback)

    @property
    def enabled(self) -> bool:
        return self._enabled

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
