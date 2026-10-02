from collections.abc import Callable
from time import monotonic
from typing import Self

import AppKit

from helomi_app import (
    ApplicationEvent,
    ConversationStateChangedEvent,
    ResponseMode,
    ResponseModeChangedEvent,
    TranscriptionReadyEvent,
)

from .base import BaseWindow


def _label(frame, value: str, *, size: float = 13.0):
    label = AppKit.NSTextField.alloc().initWithFrame_(frame)
    label.setEditable_(False)
    label.setBordered_(False)
    label.setDrawsBackground_(False)
    label.setFont_(AppKit.NSFont.systemFontOfSize_(size))
    label.setStringValue_(value)
    return label


class CallWindow(BaseWindow):
    """Independent view of an active remote call."""

    def __init__(
        self,
        *,
        caller: str,
        profile_name: str,
        response_mode: ResponseMode,
        monitoring: bool,
        on_monitoring_change: Callable[[bool], None],
        on_open_tts: Callable[[], None],
        on_end_call: Callable[[], None],
        on_close: Callable[[], None] | None = None,
    ):
        self._caller = caller
        self._profile_name = profile_name
        self._response_mode = response_mode
        self._monitoring = monitoring
        self._on_monitoring_change = on_monitoring_change
        self._on_open_tts = on_open_tts
        self._on_end_call = on_end_call
        self._started_at = monotonic()
        super().__init__(
            title="Call",
            size=AppKit.NSMakeSize(500, 390),
            min_size=AppKit.NSMakeSize(440, 340),
            on_close=on_close,
        )

    @classmethod
    def create(cls, **kwargs) -> Self:
        return cls(**kwargs)

    def _build_ui(self):
        content = self.window.contentView()
        self.caller_label = _label(
            AppKit.NSMakeRect(20, 348, 460, 24),
            self._caller,
            size=18.0,
        )
        content.addSubview_(self.caller_label)

        self.profile_label = _label(
            AppKit.NSMakeRect(20, 320, 220, 20),
            f"Profile: {self._profile_name}",
        )
        content.addSubview_(self.profile_label)
        self.state_label = _label(
            AppKit.NSMakeRect(250, 320, 110, 20),
            "State: listening",
        )
        content.addSubview_(self.state_label)
        self.duration_label = _label(
            AppKit.NSMakeRect(370, 320, 110, 20),
            "00:00",
        )
        self.duration_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(self.duration_label)

        self.mode_label = _label(
            AppKit.NSMakeRect(20, 292, 300, 20),
            f"Response mode: {self._response_mode.value}",
        )
        content.addSubview_(self.mode_label)

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 82, 460, 198)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(AppKit.NSBezelBorder)
        self.transcript = AppKit.NSTextView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, 460, 198)
        )
        self.transcript.setEditable_(False)
        self.transcript.setString_("Waiting for the caller…")
        scroll.setDocumentView_(self.transcript)
        content.addSubview_(scroll)

        self.monitoring_button = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 25, 130, 32)
        )
        self.monitoring_button.setButtonType_(AppKit.NSSwitchButton)
        self.monitoring_button.setTitle_("Monitoring")
        self.monitoring_button.setState_(1 if self._monitoring else 0)
        self.monitoring_button.setTarget_(self)
        self.monitoring_button.setAction_("monitoringClicked:")
        content.addSubview_(self.monitoring_button)

        tts_button = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(240, 23, 100, 34)
        )
        tts_button.setTitle_("Open TTS")
        tts_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        tts_button.setTarget_(self)
        tts_button.setAction_("openTTSClicked:")
        content.addSubview_(tts_button)

        end_button = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(350, 23, 130, 34)
        )
        end_button.setTitle_("End Call")
        end_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        end_button.setTarget_(self)
        end_button.setAction_("endCallClicked:")
        content.addSubview_(end_button)

    def refresh_duration(self):
        elapsed = max(0, int(monotonic() - self._started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.duration_label.setStringValue_(f"{minutes:02d}:{seconds:02d}")

    def set_monitoring(self, enabled: bool):
        self._monitoring = enabled
        self.monitoring_button.setState_(1 if enabled else 0)

    def handle_event(self, event: ApplicationEvent):
        match event:
            case TranscriptionReadyEvent(text=text):
                current = self.transcript.string()
                prefix = "" if current == "Waiting for the caller…" else f"{current}\n"
                self.transcript.setString_(f"{prefix}{text}")
                self.transcript.scrollRangeToVisible_(
                    AppKit.NSMakeRange(len(self.transcript.string()), 0)
                )
            case ConversationStateChangedEvent(state=state):
                self.state_label.setStringValue_(f"State: {state.value}")
            case ResponseModeChangedEvent(mode=mode):
                self._response_mode = mode
                self.mode_label.setStringValue_(f"Response mode: {mode.value}")

    def monitoringClicked_(self, _sender):
        enabled = self.monitoring_button.state() == 1
        self._monitoring = enabled
        self._on_monitoring_change(enabled)

    def openTTSClicked_(self, _sender):
        self._on_open_tts()

    def endCallClicked_(self, _sender):
        self._on_end_call()
