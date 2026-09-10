from pathlib import Path

from AppKit import NSModalResponseOK, NSSavePanel

from .base import BaseDialog


class SaveFileDialog(BaseDialog):
    def __init__(
        self,
        title: str,
        default_name: str | None = None,
        allowed_types: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._default_name = default_name
        self._allowed_types = allowed_types

    def open(self) -> Path | None:
        with self._activate():
            panel = NSSavePanel.savePanel()
            panel.setFloatingPanel_(True)
            panel.orderFrontRegardless()
            panel.setTitle_(self._title)
            panel.setCanCreateDirectories_(True)
            panel.center()

            if self._default_name:
                panel.setNameFieldStringValue_(self._default_name)

            if self._allowed_types:
                panel.setAllowedFileTypes_(self._allowed_types)

            response = panel.runModal()
            if response != NSModalResponseOK:
                return None

            url = panel.URL()
            if url is None:
                return None
            return Path(url.path())
