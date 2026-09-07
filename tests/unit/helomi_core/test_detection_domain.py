import numpy as np

from helomi_core.audio import AudioChunk, AudioFormat
from helomi_core.detection.domain import (
    ConversationEnded,
    DetectionMode,
    ProfileDetected,
    UtteranceContinued,
    UtteranceDetected,
    UtteranceStarted,
)


def test_detection_mode_enum():
    """Verify DetectionMode enum values."""
    assert DetectionMode.PROFILE == 1
    assert DetectionMode.UTTERANCE == 2


def test_detection_event_dataclasses():
    """Verify detection event dataclasses."""
    prof_ev = ProfileDetected(profile_id="default")
    assert prof_ev.profile_id == "default"

    start_ev = UtteranceStarted()
    assert isinstance(start_ev, UtteranceStarted)

    cont_ev = UtteranceContinued()
    assert isinstance(cont_ev, UtteranceContinued)

    end_ev = ConversationEnded()
    assert isinstance(end_ev, ConversationEnded)

    fmt = AudioFormat.MONO_16
    chunk = AudioChunk(format=fmt, samples=np.zeros(512, dtype=np.float32))
    utt_ev = UtteranceDetected(audio=chunk)
    assert utt_ev.audio == chunk
