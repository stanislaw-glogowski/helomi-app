from AppKit import NSAlert, NSAlertFirstButtonReturn, NSAlertStyleWarning

from .base import BaseDialog


class ConfirmDialog(BaseDialog):
    """Native confirmation dialog for actions that end an active call."""

    def __init__(self, title: str, message: str, confirm_title: str = "Continue"):
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_title = confirm_title

    def open(self) -> bool:
        with self._activate():
            alert = NSAlert.alloc().init()
            alert.setAlertStyle_(NSAlertStyleWarning)
            alert.setMessageText_(self._title)
            alert.setInformativeText_(self._message)
            alert.addButtonWithTitle_(self._confirm_title)
            alert.addButtonWithTitle_("Cancel")
            return alert.runModal() == NSAlertFirstButtonReturn
