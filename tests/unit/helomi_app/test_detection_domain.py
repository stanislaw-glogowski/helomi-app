import numpy as np

from helomi_app.core.audio import AudioChunk, AudioFormat
from helomi_app.core.detection import (
    ConversationEndedEvent,
    DetectionMode,
    UtteranceContinuedEvent,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)


def test_detection_mode_enum():
    """Verify DetectionMode enum values."""
    assert DetectionMode.WAKEWORD == 1
    assert DetectionMode.UTTERANCE == 2


def test_detection_event_dataclasses():
    """Verify detection event dataclasses."""
    wake_ev = WakeWordDetectedEvent(profile_id="default")
    assert wake_ev.profile_id == "default"

    start_ev = UtteranceStartedEvent()
    assert isinstance(start_ev, UtteranceStartedEvent)

    cont_ev = UtteranceContinuedEvent()
    assert isinstance(cont_ev, UtteranceContinuedEvent)

    end_ev = ConversationEndedEvent()
    assert isinstance(end_ev, ConversationEndedEvent)

    fmt = AudioFormat.MONO_16
    chunk = AudioChunk(format=fmt, samples=np.zeros(512, dtype=np.float32))
    utt_ev = UtteranceDetectedEvent(audio=chunk)
    assert utt_ev.audio == chunk
