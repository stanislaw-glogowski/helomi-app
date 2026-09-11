import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Self

import AppKit
import objc
import PyObjCTools.AppHelper

from helomi_core.audio import AudioFile, RawAudio
from helomi_core.pipeline import PipelineEvent, SynthesisReadyEvent
from helomi_core.tts import TTS_TAGS

from ..dialogs import SaveFileDialog
from .base import BaseWindow


class RoundedLayoutManager(AppKit.NSLayoutManager):
    """Layout manager drawing rounded pill backgrounds for attributed text."""

    def fillBackgroundRectArray_count_forCharacterRange_color_(
        self, rect_array, count, char_range, color
    ):
        for rect in rect_array:
            pill_rect = AppKit.NSInsetRect(rect, 0.5, 0.5)
            path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                pill_rect, 5.0, 5.0
            )
            color.setFill()
            path.fill()
        return rect_array


class TagButton(AppKit.NSButton):
    """Custom button rendered as a rounded capsule chip with accent background."""

    def drawRect_(self, dirty_rect):
        bounds = self.bounds()
        pill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, 9.0, 9.0
        )
        if self.isHighlighted():
            AppKit.NSColor.controlAccentColor().colorWithAlphaComponent_(0.3).setFill()
        else:
            AppKit.NSColor.controlAccentColor().colorWithAlphaComponent_(0.14).setFill()
        pill.fill()

        title = self.title()
        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(11.0),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.controlAccentColor(),
        }
        size = title.sizeWithAttributes_(attrs)
        x = (bounds.size.width - size.width) / 2.0
        y = (bounds.size.height - size.height) / 2.0
        title.drawAtPoint_withAttributes_(AppKit.NSMakePoint(x, y), attrs)


class TagButtonsContainer(AppKit.NSView):
    """Container view laying out tag buttons in wrapped flow lines."""

    buttons: list[AppKit.NSButton]

    def isFlipped(self) -> bool:
        return True

    def resizeSubviewsWithOldSize_(self, old_size: AppKit.NSSize) -> None:
        objc.super(TagButtonsContainer, self).resizeSubviewsWithOldSize_(old_size)
        self.relayout_buttons()

    def relayout_buttons(self) -> None:
        bounds_width = self.bounds().size.width
        if bounds_width <= 0:
            bounds_width = 520.0

        btn_h = 20.0
        h_gap = 5.0
        v_gap = 4.0
        x = 0.0
        y = 0.0

        attrs = {AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(11.0)}
        for btn in getattr(self, "buttons", []):
            title = btn.title()
            size = title.sizeWithAttributes_(attrs)
            w = max(34.0, size.width + 16.0)
            if x + w > bounds_width and x > 0:
                x = 0.0
                y += btn_h + v_gap
            btn.setFrame_(AppKit.NSMakeRect(x, y, w, btn_h))
            x += w + h_gap


class ComposeTextView(AppKit.NSTextView):
    send_action: Callable[[], None] | None = None

    def _find_tag_range(self, text: str, pos: int) -> tuple[int, int] | None:
        """Return (start, end) range of an emotion tag at or immediately before pos."""
        if pos <= 0 or pos > len(text):
            return None

        # 1. Cursor immediately after ']'
        if text[pos - 1] == "]":
            start = pos - 1
            while start > 0 and text[start - 1] not in (" ", "\n", "\t", "]"):
                start -= 1
                if text[start] == "[":
                    tag = text[start:pos]
                    if tag in TTS_TAGS:
                        return start, pos
                    break

        # 2. Cursor inside tag (between '[' and ']')
        start = pos
        while start > 0 and text[start - 1] not in (" ", "\n", "\t", "]"):
            start -= 1
            if text[start] == "[":
                end = pos
                while end < len(text) and text[end] not in (" ", "\n", "\t", "["):
                    if text[end] == "]":
                        end += 1
                        tag = text[start:end]
                        if tag in TTS_TAGS:
                            return start, end
                        break
                    end += 1
                break

        return None

    def _handle_backspace_tag(self) -> bool:
        """If cursor encounters a tag, delete the entire tag in one backspace."""
        sel = self.selectedRange()
        if sel.length > 0:
            return False

        text = self.string()
        tag_range = self._find_tag_range(text, sel.location)
        if tag_range is not None:
            start, end = tag_range
            r = AppKit.NSMakeRange(start, end - start)
            if self.shouldChangeTextInRange_replacementString_(r, ""):
                self.replaceCharactersInRange_withString_(r, "")
                self.didChangeText()
                return True

        return False

    def deleteBackward_(self, sender):
        """Handle backspace selector with tag-aware deletion."""
        if self._handle_backspace_tag():
            return
        objc.super(ComposeTextView, self).deleteBackward_(sender)

    def performKeyEquivalent_(self, event):
        """Handle standard edit key equivalents and custom shortcuts."""
        flags = event.modifierFlags()
        if flags & AppKit.NSEventModifierFlagCommand:
            char_ign = (event.charactersIgnoringModifiers() or "").lower()
            if char_ign == "v":
                self.paste_(None)
                return True
            if char_ign == "c":
                self.copy_(None)
                return True
            if char_ign == "x":
                self.cut_(None)
                return True
            if char_ign == "a":
                self.selectAll_(None)
                return True
            if char_ign == "z":
                um = self.undoManager()
                if flags & AppKit.NSEventModifierFlagShift:
                    if um and um.canRedo():
                        um.redo()
                        return True
                else:
                    if um and um.canUndo():
                        um.undo()
                        return True
            if char_ign == "w":
                win = self.window()
                if win:
                    win.performClose_(None)
                return True
            chars = event.characters() or ""
            if chars in ("\r", "\n"):
                if hasattr(self, "send_action") and self.send_action:
                    self.send_action()
                return True

        return objc.super(ComposeTextView, self).performKeyEquivalent_(event)

    def keyDown_(self, event):
        """Handle keyboard shortcuts as fallback and tag-aware backspace."""
        flags = event.modifierFlags()
        if flags & AppKit.NSEventModifierFlagCommand:
            char_ign = (event.charactersIgnoringModifiers() or "").lower()
            if char_ign == "v":
                self.paste_(None)
                return
            if char_ign == "c":
                self.copy_(None)
                return
            if char_ign == "x":
                self.cut_(None)
                return
            if char_ign == "a":
                self.selectAll_(None)
                return
            if char_ign == "z":
                um = self.undoManager()
                if flags & AppKit.NSEventModifierFlagShift:
                    if um and um.canRedo():
                        um.redo()
                else:
                    if um and um.canUndo():
                        um.undo()
                return
            if char_ign == "w":
                win = self.window()
                if win:
                    win.performClose_(None)
                return
            chars = event.characters() or ""
            if chars in ("\r", "\n"):
                if hasattr(self, "send_action") and self.send_action:
                    self.send_action()
                return

        chars = event.characters() or ""
        if chars == "\x7f" and not (flags & AppKit.NSEventModifierFlagCommand):
            if self._handle_backspace_tag():
                return

        objc.super(ComposeTextView, self).keyDown_(event)


class ComposeTextViewDelegate(AppKit.NSObject):
    tags: Iterable[str]
    on_text_change: Callable[[], None] | None

    def __new__(
        cls,
        tags: Iterable[str],
        on_text_change: Callable[[], None] | None = None,
    ) -> Self:
        instance = cls.alloc().init()
        assert instance is not None
        instance.tags = tags
        instance.on_text_change = on_text_change
        return instance

    def highlight_tags(self, tv: AppKit.NSTextView) -> None:
        """Apply rounded background and accent colors to emotion tags."""
        text = tv.string()
        ts = tv.textStorage()
        if ts is None:
            return

        full_len = len(text)
        if full_len == 0:
            return

        full_range = AppKit.NSMakeRange(0, full_len)
        ts.removeAttribute_range_(AppKit.NSBackgroundColorAttributeName, full_range)
        ts.addAttribute_value_range_(
            AppKit.NSForegroundColorAttributeName,
            AppKit.NSColor.textColor(),
            full_range,
        )

        tag_bg = AppKit.NSColor.controlAccentColor().colorWithAlphaComponent_(0.2)
        tag_fg = AppKit.NSColor.controlAccentColor()

        for tag in self.tags:
            start = 0
            while True:
                idx = text.find(tag, start)
                if idx == -1:
                    break
                r = AppKit.NSMakeRange(idx, len(tag))
                ts.addAttribute_value_range_(
                    AppKit.NSBackgroundColorAttributeName, tag_bg, r
                )
                ts.addAttribute_value_range_(
                    AppKit.NSForegroundColorAttributeName, tag_fg, r
                )
                start = idx + len(tag)

        tv.setTypingAttributes_(
            {
                AppKit.NSFontAttributeName: tv.font()
                or AppKit.NSFont.systemFontOfSize_(14.0),
                AppKit.NSForegroundColorAttributeName: AppKit.NSColor.textColor(),
            }
        )

    def textDidChange_(self, notification):
        """Highlight emotion tags with rounded pill styling and notify change."""
        tv = notification.object()
        self.highlight_tags(tv)

        if hasattr(self, "on_text_change") and self.on_text_change:
            self.on_text_change()


class TTSWindow(BaseWindow):
    close_btn: AppKit.NSButton
    save_btn: AppKit.NSButton
    tag_buttons: list[AppKit.NSButton]
    tag_container: TagButtonsContainer
    _get_profile_id: Callable[[], str | None] | None

    def __init__(
        self,
        on_send: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        get_profile_id: Callable[[], str | None] | None = None,
    ) -> None:
        self._on_send = on_send
        self._get_profile_id = get_profile_id
        self._current_audio: RawAudio | None = None
        self._current_profile_id: str | None = None
        self._current_timestamp: datetime | None = None
        self.tag_buttons = []
        super().__init__(
            title="Text to Speech",
            size=AppKit.NSMakeSize(560, 410),
            min_size=AppKit.NSMakeSize(480, 360),
            on_close=on_close,
        )

    @classmethod
    def create(
        cls,
        on_send: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        get_profile_id: Callable[[], str | None] | None = None,
    ) -> Self:
        return cls(on_send=on_send, on_close=on_close, get_profile_id=get_profile_id)

    def _build_ui(self) -> None:
        content_view = self.window.contentView()

        # Top instruction label
        hint_label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 378, 520, 20)
        )
        hint_label.setEditable_(False)
        hint_label.setBordered_(False)
        hint_label.setDrawsBackground_(False)
        hint_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        hint_label.setFont_(AppKit.NSFont.systemFontOfSize_(12.0))
        hint_label.setStringValue_("Press ⌘Enter to speak.")
        hint_label.setAutoresizingMask_(
            AppKit.NSViewMinYMargin | AppKit.NSViewWidthSizable
        )
        content_view.addSubview_(hint_label)

        # Scrollable text editor
        self.scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 180, 520, 190)
        )
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setBorderType_(AppKit.NSBezelBorder)
        self.scroll_view.setDrawsBackground_(True)
        self.scroll_view.setBackgroundColor_(AppKit.NSColor.textBackgroundColor())
        self.scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )

        content_size = self.scroll_view.contentSize()

        self.layout_manager = RoundedLayoutManager.alloc().init()
        self.text_storage = AppKit.NSTextStorage.alloc().init()
        self.text_storage.addLayoutManager_(self.layout_manager)

        text_container = AppKit.NSTextContainer.alloc().initWithContainerSize_(
            AppKit.NSMakeSize(content_size.width, 1e7)
        )
        text_container.setWidthTracksTextView_(True)
        self.layout_manager.addTextContainer_(text_container)

        self.text_view = ComposeTextView.alloc().initWithFrame_textContainer_(
            AppKit.NSMakeRect(0, 0, content_size.width, content_size.height),
            text_container,
        )
        self.text_view.setMinSize_(AppKit.NSMakeSize(0.0, content_size.height))
        self.text_view.setMaxSize_(AppKit.NSMakeSize(1e7, 1e7))
        self.text_view.setVerticallyResizable_(True)
        self.text_view.setHorizontallyResizable_(False)
        self.text_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)

        self.text_view.setRichText_(False)
        self.text_view.setTextColor_(AppKit.NSColor.textColor())
        self.text_view.setBackgroundColor_(AppKit.NSColor.textBackgroundColor())
        self.text_view.setInsertionPointColor_(AppKit.NSColor.textColor())
        self.text_view.setDrawsBackground_(True)

        self.text_view.setAutomaticQuoteSubstitutionEnabled_(False)
        self.text_view.setAutomaticDashSubstitutionEnabled_(False)
        self.text_view.setAutomaticTextReplacementEnabled_(False)
        self.text_view.setAutomaticSpellingCorrectionEnabled_(False)
        self.text_view.setFont_(AppKit.NSFont.systemFontOfSize_(14.0))
        self.text_view.setTextContainerInset_(AppKit.NSMakeSize(8.0, 8.0))
        self.text_view.setAllowsUndo_(True)

        self.delegate = ComposeTextViewDelegate(
            tags=TTS_TAGS,
            on_text_change=self._handle_text_change,
        )
        self.text_view.setDelegate_(self.delegate)
        self.text_view.send_action = self.do_send

        self.scroll_view.setDocumentView_(self.text_view)
        content_view.addSubview_(self.scroll_view)

        # Tag buttons container with wrapped lines directly below text editor
        self.tag_container = TagButtonsContainer.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 52, 520, 120)
        )
        self.tag_container.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewMaxYMargin
        )
        self.tag_container.buttons = []
        self.tag_buttons = []

        for tag, desc in TTS_TAGS.items():
            btn = TagButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 10, 20))
            btn.setTitle_(tag)
            btn.setToolTip_(desc)
            btn.setTarget_(self)
            btn.setAction_("tagButtonClicked:")
            self.tag_container.addSubview_(btn)
            self.tag_container.buttons.append(btn)
            self.tag_buttons.append(btn)

        self.tag_container.relayout_buttons()
        content_view.addSubview_(self.tag_container)

        # Focus editor
        self.focus_view = self.text_view

        # Status label on the bottom left
        self.status_label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 18, 110, 20)
        )
        self.status_label.setEditable_(False)
        self.status_label.setBordered_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self.status_label.setStringValue_("Ready")
        self.status_label.setAutoresizingMask_(AppKit.NSViewMaxYMargin)
        content_view.addSubview_(self.status_label)

        # "Close" button
        self.close_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(135, 14, 80, 32)
        )
        self.close_btn.setTitle_("Close")
        self.close_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        self.close_btn.setTarget_(self)
        self.close_btn.setAction_("closeClicked:")
        self.close_btn.setAutoresizingMask_(
            AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin
        )
        content_view.addSubview_(self.close_btn)

        # "Save to …" button
        self.save_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(225, 14, 95, 32)
        )
        self.save_btn.setTitle_("Save to …")
        self.save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        self.save_btn.setTarget_(self)
        self.save_btn.setAction_("saveClicked:")
        self.save_btn.setEnabled_(False)
        self.save_btn.setAutoresizingMask_(
            AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin
        )
        content_view.addSubview_(self.save_btn)

        # "Clear" button
        clear_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(330, 14, 80, 32)
        )
        clear_btn.setTitle_("Clear")
        clear_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        clear_btn.setTarget_(self)
        clear_btn.setAction_("clearClicked:")
        clear_btn.setAutoresizingMask_(
            AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin
        )
        content_view.addSubview_(clear_btn)

        # "Speak" button
        speak_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(420, 14, 120, 32)
        )
        speak_btn.setTitle_("Speak (⌘↵)")
        speak_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        speak_btn.setKeyEquivalent_("\r")
        speak_btn.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand)
        speak_btn.setTarget_(self)
        speak_btn.setAction_("sendClicked:")
        speak_btn.setAutoresizingMask_(
            AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin
        )
        content_view.addSubview_(speak_btn)

    def _handle_text_change(self) -> None:
        if self.status_label.stringValue() in ("Sent", "Cleared"):
            self.status_label.setStringValue_("Ready")

    def handle_event(self, event: PipelineEvent) -> None:
        if isinstance(event, SynthesisReadyEvent):
            self.on_synthesis_ready(event)

    def on_synthesis_ready(self, event: SynthesisReadyEvent) -> None:
        self._current_audio = event.audio
        self._current_profile_id = event.profile_id
        self._current_timestamp = datetime.now()
        if self._current_audio is not None:
            if threading.current_thread() is threading.main_thread():
                self._enable_save()
            else:
                PyObjCTools.AppHelper.callAfter(self._enable_save)

    def _enable_save(self) -> None:
        self.save_btn.setEnabled_(True)
        if self.status_label.stringValue() == "Speaking…":
            self.status_label.setStringValue_("Ready")

    def tagButtonClicked_(self, sender: AppKit.NSButton) -> None:
        tag = sender.title()
        self.insert_tag(tag)

    def insert_tag(self, tag: str) -> None:
        """Insert emotion tag at current cursor position."""
        sel = self.text_view.selectedRange()
        text = self.text_view.string()
        pos = sel.location

        prefix = " " if (pos > 0 and text[pos - 1] not in (" ", "\n", "\t")) else ""
        suffix = " " if (pos >= len(text) or text[pos] not in (" ", "\n", "\t")) else ""
        insert_str = f"{prefix}{tag}{suffix}"

        self.text_view.insertText_replacementRange_(insert_str, sel)
        self.delegate.highlight_tags(self.text_view)
        self.window.makeFirstResponder_(self.text_view)

    def do_send(self) -> None:
        """Dispatch the typed text to the send callback."""
        text = self.text_view.string().strip()
        if not text:
            return
        self._current_audio = None
        self._current_profile_id = None
        self._current_timestamp = None
        self.save_btn.setEnabled_(False)
        self.status_label.setStringValue_("Speaking…")
        try:
            if self._on_send:
                self._on_send(text)
            self.status_label.setStringValue_("Sent")
        except Exception as err:
            self.status_label.setStringValue_(f"Error: {err}")

    def do_save(self) -> None:
        """Prompt save dialog and write current synthesis audio to file."""
        if not self._current_audio:
            return

        profile = (
            self._current_profile_id
            or (self._get_profile_id() if self._get_profile_id else None)
            or "tts"
        )
        timestamp = (self._current_timestamp or datetime.now()).strftime(
            "%Y%m%d_%H%M%S"
        )
        default_name = f"{profile}_{timestamp}.wav"

        path = SaveFileDialog(
            title="Save Synthesis",
            default_name=default_name,
            allowed_types=["wav", "wave"],
        ).open()
        if path is None:
            return

        try:
            AudioFile(path).write(self._current_audio)
            self.status_label.setStringValue_(f"Saved: {path.name}")
        except Exception as err:
            self.status_label.setStringValue_(f"Error: {err}")

    def clear(self) -> None:
        """Clear the compose text view and reset status."""
        self.text_view.setString_("")
        self.delegate.highlight_tags(self.text_view)
        self._current_audio = None
        self._current_profile_id = None
        self._current_timestamp = None
        self.save_btn.setEnabled_(False)
        self.status_label.setStringValue_("Cleared")
        self.window.makeFirstResponder_(self.text_view)

    def sendClicked_(self, _: object = None) -> None:
        self.do_send()

    def clearClicked_(self, _: object = None) -> None:
        self.clear()

    def saveClicked_(self, _: object = None) -> None:
        self.do_save()

    def closeClicked_(self, _: object = None) -> None:
        self.close()
