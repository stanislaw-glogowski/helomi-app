import numpy as np

from helomi_core.audio import AudioChunk, AudioFormat
from helomi_core.turn import TurnPrediction, TurnSettings, TurnStatus


def test_turn_status_enum():
    """Verify TurnStatus string values."""
    assert TurnStatus.STARTED == "started"
    assert TurnStatus.COMPLETED == "completed"
    assert TurnStatus.CONTINUED == "continued"
    assert TurnStatus.TIMEOUT == "timeout"


def test_turn_prediction_dataclass():
    """Verify TurnPrediction attributes."""
    fmt = AudioFormat.MONO_16
    chunk = AudioChunk(format=fmt, samples=np.zeros(512, dtype=np.float32))
    pred = TurnPrediction(status=TurnStatus.COMPLETED, audio=chunk, score=0.95)

    assert pred.status == TurnStatus.COMPLETED
    assert pred.audio == chunk
    assert pred.score == 0.95


def test_turn_settings():
    """Verify TurnSettings default adapter and parsing."""
    settings = TurnSettings.model_validate({"adapter": "smart_turn", "smart_turn": {}})
    assert settings.adapter == "smart_turn"
