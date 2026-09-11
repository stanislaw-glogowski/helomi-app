from collections.abc import Callable
from typing import Any, Self

import AppKit

from helomi_core.pipeline import PipelineEvent


class _WindowDelegate(AppKit.NSObject):
    """Internal delegate bridging Cocoa window events to BaseWindow."""

    _owner: BaseWindow | None = None

    def __new__(cls, owner: BaseWindow) -> Self:
        instance = cls.alloc().init()
        assert instance is not None
        instance._owner = owner
        return instance

    def windowWillClose_(self, notification: Any) -> None:
        if self._owner is not None:
            self._owner.windowWillClose_(notification)


def _ensure_edit_menu() -> None:
    app = AppKit.NSApplication.sharedApplication()
    if app.mainMenu() is not None:
        return

    main_menu = AppKit.NSMenu.alloc().init()

    # Application menu
    app_menu_item = AppKit.NSMenuItem.alloc().init()
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu_item.setSubmenu_(app_menu)
    main_menu.addItem_(app_menu_item)

    # Edit menu
    edit_menu_item = AppKit.NSMenuItem.alloc().init()
    edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Undo", "undo:", "z")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
    edit_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
    edit_menu_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_menu_item)

    app.setMainMenu_(main_menu)


class BaseWindow:
    """Base class for native macOS floating tool windows."""

    window: AppKit.NSPanel
    focus_view: AppKit.NSView | None = None
    _on_close: Callable[[], None] | None = None
    _delegate: _WindowDelegate

    def __init__(
        self,
        title: str,
        size: AppKit.NSSize,
        min_size: AppKit.NSSize,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._on_close = on_close
        self.focus_view = None

        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable
        )
        self.window = (
            AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                AppKit.NSMakeRect(0, 0, size.width, size.height),
                style,
                AppKit.NSBackingStoreBuffered,
                False,
            )
        )
        self.window.setTitle_(title)
        self.window.setMinSize_(min_size)
        self.window.setReleasedWhenClosed_(False)
        self.window.setFloatingPanel_(True)
        self.window.setBecomesKeyOnlyIfNeeded_(False)
        self._delegate = _WindowDelegate(self)
        self.window.setDelegate_(self._delegate)
        self.window.center()

        self._build_ui()

    def _build_ui(self) -> None:
        """Subclasses construct their subviews here."""
        pass

    def handle_event(self, event: PipelineEvent) -> None:
        """Handle incoming pipeline events. Subclasses can override."""
        pass

    def activate(self) -> None:
        """Order window front and set focus keeping accessory activation policy."""
        _ensure_edit_menu()
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        app.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.window.orderFrontRegardless()
        if self.focus_view is not None:
            self.window.makeFirstResponder_(self.focus_view)

    def deactivate(self, hide_window: bool = True) -> None:
        """Optionally hide the window and ensure accessory policy."""
        if hide_window and hasattr(self, "window") and self.window is not None:
            self.window.orderOut_(None)
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def show(self) -> None:
        """Show window with elevated activation policy."""
        self.activate()

    def close(self) -> None:
        """Hide window, restore accessory activation policy, and trigger on_close."""
        self.deactivate(hide_window=True)
        if self._on_close:
            self._on_close()

    def windowWillClose_(self, notification: Any) -> None:
        """Handle window closed by user and restore accessory policy."""
        self.deactivate(hide_window=False)
        if self._on_close:
            self._on_close()
