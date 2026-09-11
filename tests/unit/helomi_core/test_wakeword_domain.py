from unittest.mock import MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

from helomi_core.audio import AudioChunk, AudioFormat
from helomi_core.wakeword import (
    WakeWordPrediction,
    get_wakeword_adapter,
)
from helomi_core.wakeword.config import (
    WakeWordProfile,
    WakeWordSettings,
)
from helomi_core.wakeword.openwakeword.adapter import OpenWakeWordAdapter
from helomi_core.wakeword.openwakeword.config import (
    OpenWakeWordConfig,
    OpenWakeWordOptions,
)


def test_wakeword_prediction_dataclass():
    """Verify WakeWordPrediction structure."""
    pred = WakeWordPrediction(matched="default", scores={"default": 0.92})
    assert pred.matched == "default"
    assert pred.scores["default"] == 0.92


def test_wakeword_settings_and_profile(tmp_path):
    """Verify WakeWordSettings and WakeWordProfile parsing with patience."""
    emb_file = tmp_path / "embedding.onnx"
    emb_file.touch()
    mel_file = tmp_path / "melspec.onnx"
    mel_file.touch()
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    settings = WakeWordSettings.model_validate(
        {
            "adapter": "openwakeword",
            "openwakeword": {
                "embedding_path": str(emb_file),
                "melspec_path": str(mel_file),
            },
        }
    )
    assert settings.adapter == "openwakeword"
    assert settings.openwakeword is not None
    assert settings.openwakeword.patience == 2

    profile = WakeWordProfile.model_validate(
        {
            "adapter": "openwakeword",
            "openwakeword": {
                "model_path": str(model_file),
                "patience": 3,
            },
        }
    )
    assert profile.adapter == "openwakeword"
    assert profile.openwakeword is not None
    assert profile.openwakeword.patience == 3


def test_wakeword_patience_validation(tmp_path):
    """Verify patience validation requires value >= 1."""
    emb_file = tmp_path / "embedding.onnx"
    emb_file.touch()
    mel_file = tmp_path / "melspec.onnx"
    mel_file.touch()
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    with pytest.raises(ValidationError):
        OpenWakeWordConfig(
            embedding_path=emb_file,
            melspec_path=mel_file,
            patience=0,
        )

    with pytest.raises(ValidationError):
        OpenWakeWordOptions(
            model_path=model_file,
            patience=0,
        )


def test_openwakeword_adapter_patience_logic(tmp_path):
    """Verify OpenWakeWordAdapter patience multi-frame verification logic."""
    emb_file = tmp_path / "embedding.onnx"
    emb_file.touch()
    mel_file = tmp_path / "melspec.onnx"
    mel_file.touch()
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    config = OpenWakeWordConfig(
        embedding_path=emb_file,
        melspec_path=mel_file,
        threshold=0.75,
        patience=2,
        frame_size=1280,
    )
    words = {
        "gizmo": OpenWakeWordOptions(
            model_path=model_file,
            threshold=0.75,
            patience=2,
        ),
        "viki": OpenWakeWordOptions(
            model_path=model_file,
            threshold=0.75,
            patience=2,
        ),
    }

    adapter = OpenWakeWordAdapter(config, words)
    mock_model = MagicMock()
    adapter._model = mock_model
    adapter._profile_mapping = {"hey_gizmo": "gizmo", "hey_viki": "viki"}

    chunk = AudioChunk(
        format=AudioFormat.MONO_16,
        samples=np.zeros(1280, dtype=np.float32),
    )

    # Frame 1: Gizmo and Viki both spike once -> no match due to patience=2
    mock_model.predict.return_value = {"hey_gizmo": 0.80, "hey_viki": 0.82}
    pred1 = adapter.predict(chunk, voice_detected=True)
    assert pred1.matched is None
    assert pred1.scores["gizmo"] == 0.80
    assert pred1.scores["viki"] == 0.82

    # Frame 2: Gizmo stays above threshold (0.85), but Viki drops (0.30)
    # Gizmo reaches consecutive frames = 2 -> match!
    mock_model.predict.return_value = {"hey_gizmo": 0.85, "hey_viki": 0.30}
    pred2 = adapter.predict(chunk, voice_detected=True)
    assert pred2.matched == "gizmo"
    assert pred2.scores["gizmo"] == 0.85
    assert pred2.scores["viki"] == 0.30

    # Frame 3: Gizmo drops below threshold (0.40) -> consecutive counter resets to 0
    mock_model.predict.return_value = {"hey_gizmo": 0.40, "hey_viki": 0.20}
    pred3 = adapter.predict(chunk, voice_detected=True)
    assert pred3.matched is None

    # Reset clears frame counters
    adapter.reset()
    mock_model.reset.assert_called_once()
    assert len(adapter._consecutive_frames) == 0


def test_get_wakeword_adapter_none_inputs():
    """Verify get_wakeword_adapter returns None when inputs are missing."""
    assert get_wakeword_adapter(None, None) is None
    assert get_wakeword_adapter(WakeWordSettings(), None) is None
    assert get_wakeword_adapter(None, {}) is None
