import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Self

import AppKit
import objc
import PyObjCTools.AppHelper

from helomi_core.audio import AudioFile, RawAudio
from helomi_core.pipeline import PipelineEvent, SynthesisReady
from helomi_core.tts import TTS_TAGS

from ..dialogs import SaveFileDialog
from .base import BaseWindow


class ComposeTextView(AppKit.NSTextView):
    send_action: Callable[[], None] | None = None

    def rangeForUserCompletion(self):
        """Return the range starting from '[' to the cursor position for completion."""
        selected_range = self.selectedRange()
        text = self.string()
        pos = selected_range.location

        if text and pos > 0:
            if text[pos - 1] == "]":
                return objc.super(ComposeTextView, self).rangeForUserCompletion()

            start = pos
            while start > 0 and text[start - 1] not in (" ", "\n", "\t", "]"):
                start -= 1
                if text[start] == "[":
                    return AppKit.NSMakeRange(start, pos - start)

        return objc.super(ComposeTextView, self).rangeForUserCompletion()

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
        """Handle keyboard shortcuts as fallback."""
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

        objc.super(ComposeTextView, self).keyDown_(event)


class ComposeTextViewDelegate(AppKit.NSObject):
    tags: Iterable[str]
    on_text_change: Callable[[], None] | None
    _last_len: int

    def __new__(
        cls,
        tags: Iterable[str],
        on_text_change: Callable[[], None] | None = None,
    ) -> Self:
        instance = cls.alloc().init()
        assert instance is not None
        instance.tags = tags
        instance.on_text_change = on_text_change
        instance._last_len = 0
        return instance

    def textView_completions_forPartialWordRange_indexOfSelectedItem_(
        self, text_view, words, char_range, index
    ):
        """Filter TTS emotion tags matching the typed token starting with '['."""
        text = text_view.string()
        loc = char_range.location
        length = char_range.length
        partial = text[loc : loc + length]

        if partial.startswith("["):
            matches = [t for t in self.tags if t.lower().startswith(partial.lower())]
            return matches, -1

        return words or [], -1

    def textDidChange_(self, notification):
        """Automatically trigger completions when '[' is typed, and notify change."""
        tv = notification.object()
        text = tv.string()
        new_len = len(text)
        pos = tv.selectedRange().location
        if new_len > getattr(self, "_last_len", 0) and pos > 0 and text[pos - 1] == "[":
            tv.complete_(None)
        self._last_len = new_len

        if hasattr(self, "on_text_change") and self.on_text_change:
            self.on_text_change()


class TTSWindow(BaseWindow):
    close_btn: AppKit.NSButton
    save_btn: AppKit.NSButton
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
        super().__init__(
            title="Text to Speech",
            size=AppKit.NSMakeSize(560, 320),
            min_size=AppKit.NSMakeSize(480, 240),
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
            AppKit.NSMakeRect(20, 285, 520, 20)
        )
        hint_label.setEditable_(False)
        hint_label.setBordered_(False)
        hint_label.setDrawsBackground_(False)
        hint_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        hint_label.setFont_(AppKit.NSFont.systemFontOfSize_(12.0))
        hint_label.setStringValue_(
            "Type '[' to insert emotion tags. Press ⌘Enter to speak."
        )
        hint_label.setAutoresizingMask_(
            AppKit.NSViewMinYMargin | AppKit.NSViewWidthSizable
        )
        content_view.addSubview_(hint_label)

        # Scrollable text editor
        self.scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 58, 520, 222)
        )
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setBorderType_(AppKit.NSBezelBorder)
        self.scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )

        content_size = self.scroll_view.contentSize()
        self.text_view = ComposeTextView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, content_size.width, content_size.height)
        )
        self.text_view.setMinSize_(AppKit.NSMakeSize(0.0, content_size.height))
        self.text_view.setMaxSize_(AppKit.NSMakeSize(1e7, 1e7))
        self.text_view.setVerticallyResizable_(True)
        self.text_view.setHorizontallyResizable_(False)
        self.text_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)

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

        text_container = self.text_view.textContainer()
        text_container.setContainerSize_(AppKit.NSMakeSize(content_size.width, 1e7))
        text_container.setWidthTracksTextView_(True)
        self.scroll_view.setDocumentView_(self.text_view)
        content_view.addSubview_(self.scroll_view)

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
        if isinstance(event, SynthesisReady):
            self.on_synthesis_ready(event)

    def on_synthesis_ready(self, event: SynthesisReady) -> None:
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
        self.delegate._last_len = 0
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
