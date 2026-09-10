from collections.abc import Generator
from contextlib import contextmanager

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
)


class BaseDialog:
    """Base class for native macOS dialogs with automatic activation policy handling."""

    @contextmanager
    def _activate(self) -> Generator[None]:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        try:
            yield
        finally:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
