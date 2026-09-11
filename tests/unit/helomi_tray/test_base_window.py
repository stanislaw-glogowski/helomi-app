from unittest.mock import MagicMock

import AppKit

from helomi_tray.app.windows.base import BaseWindow, _ensure_edit_menu


def test_ensure_edit_menu():
    """Verify _ensure_edit_menu creates and retains standard Edit menu."""
    app = AppKit.NSApplication.sharedApplication()
    _ensure_edit_menu()
    assert app.mainMenu() is not None
    menu = app.mainMenu()
    _ensure_edit_menu()
    assert app.mainMenu() is menu


def test_base_window_lifecycle_and_policy():
    """Verify BaseWindow initializes window, activates, deactivates, and callbacks."""
    closed = False

    def on_close():
        nonlocal closed
        closed = True

    class CustomWindow(BaseWindow):
        def _build_ui(self):
            self.built = True

    win = CustomWindow(
        title="Test Window",
        size=AppKit.NSMakeSize(500, 300),
        min_size=AppKit.NSMakeSize(400, 200),
        on_close=on_close,
    )
    assert win is not None
    assert win.built is True
    assert win.window.title() == "Test Window"
    assert win.window.canBecomeKeyWindow() is True

    mock_focus = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 10, 10))
    win.focus_view = mock_focus

    # 1. show() activates and focuses while keeping accessory policy
    win.show()
    app = AppKit.NSApplication.sharedApplication()
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory

    # 2. close() deactivates and triggers on_close
    win.close()
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory
    assert closed is True

    # 3. windowWillClose_ deactivates and triggers on_close
    closed = False
    win.windowWillClose_(None)
    assert app.activationPolicy() == AppKit.NSApplicationActivationPolicyAccessory
    assert closed is True

    # 4. close without on_close callback does not crash
    win._on_close = None
    win.close()
    win.windowWillClose_(None)

    # 5. deactivate with hide_window=False does not orderOut_
    with MagicMock() as mock_window:
        win.window = mock_window
        win.deactivate(hide_window=False)
        mock_window.orderOut_.assert_not_called()

    # 6. _delegate forwards windowWillClose_ to BaseWindow
    closed = False
    win._on_close = on_close
    win._delegate.windowWillClose_(None)
    assert closed is True

    # 7. _delegate without owner does not crash
    win._delegate._owner = None
    win._delegate.windowWillClose_(None)
