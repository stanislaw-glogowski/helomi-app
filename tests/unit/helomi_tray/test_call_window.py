from unittest.mock import MagicMock

import AppKit

from helomi_app import (
    ConversationState,
    ConversationStateChangedEvent,
    ResponseMode,
    ResponseModeChangedEvent,
    TranscriptionReadyEvent,
)
from helomi_tray.app.windows import CallWindow


def test_call_window_updates_and_callbacks():
    monitoring = MagicMock()
    open_tts = MagicMock()
    end_call = MagicMock()
    closed = MagicMock()
    window = CallWindow(
        caller="*******6789",
        profile_name="Alexa",
        response_mode=ResponseMode.PARROT,
        monitoring=True,
        on_monitoring_change=monitoring,
        on_open_tts=open_tts,
        on_end_call=end_call,
        on_close=closed,
    )
    assert (
        CallWindow.create(
            caller="****1234",
            profile_name="Alexa",
            response_mode=ResponseMode.API,
            monitoring=False,
            on_monitoring_change=monitoring,
            on_open_tts=open_tts,
            on_end_call=end_call,
        ).window.title()
        == "Call"
    )

    window._started_at -= 65
    window.refresh_duration()
    assert window.duration_label.stringValue() == "01:05"
    window.set_monitoring(False)
    assert window.monitoring_button.state() == 0

    window.handle_event(TranscriptionReadyEvent(profile_id="alexa", text="First line"))
    window.handle_event(TranscriptionReadyEvent(profile_id="alexa", text="Second line"))
    assert window.transcript.string() == "First line\nSecond line"
    window.handle_event(
        ConversationStateChangedEvent(
            state=ConversationState.SPEAKING,
            previous_state=ConversationState.LISTENING,
        )
    )
    assert window.state_label.stringValue() == "State: speaking"
    window.handle_event(
        ResponseModeChangedEvent(
            mode=ResponseMode.OPERATOR,
            previous_mode=ResponseMode.PARROT,
        )
    )
    assert window.mode_label.stringValue() == "Response mode: operator"

    window.monitoring_button.setState_(1)
    window.monitoringClicked_(None)
    monitoring.assert_called_once_with(True)
    window.openTTSClicked_(None)
    open_tts.assert_called_once()
    window.endCallClicked_(None)
    end_call.assert_called_once()

    window.show()
    assert (
        AppKit.NSApplication.sharedApplication().activationPolicy()
        != AppKit.NSApplicationActivationPolicyRegular
    )
    window.close()
    closed.assert_called_once()
