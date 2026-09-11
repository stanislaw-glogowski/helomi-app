from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helomi_core.audio import AudioChunk, AudioFormat
from helomi_core.vad import VADPrediction
from helomi_core.vad.config import VADSettings
from helomi_core.vad.silero_vad.config import SileroVADMLXConfig, SileroVADONNXConfig
from helomi_core.vad.silero_vad.mlx_adapter import SileroVADMLXAdapter
from helomi_core.vad.silero_vad.onnx_adapter import SileroVADONNXAdapter


def test_vad_prediction_dataclass():
    """Verify VADPrediction fields and defaults."""
    pred = VADPrediction(detected=True, score=0.88)
    assert pred.detected is True
    assert pred.score == 0.88


def test_vad_settings():
    """Verify VADSettings default adapter and parsing."""
    settings = VADSettings.model_validate({"adapter": "silero_vad", "silero_vad": {}})
    assert settings.adapter == "silero_vad"
    assert isinstance(settings.silero_vad, SileroVADMLXConfig)


def test_silero_vad_mlx_adapter_lifecycle(tmp_path: Path):
    """Verify SileroVADMLXAdapter lifecycle, predictions, reset and error handling."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    with patch(
        "helomi_common.validation.hf.snapshot_download", return_value=str(model_dir)
    ):
        config = SileroVADMLXConfig(
            engine="mlx",
            model_id="mlx-community/silero-vad",
            threshold=0.6,
        )

    adapter = SileroVADMLXAdapter(config)
    chunk = AudioChunk(
        format=AudioFormat.MONO_16,
        samples=MagicMock(),
    )

    # 1. Require model before open raises RuntimeError
    with pytest.raises(RuntimeError, match="MLX SileroVAD model is not loaded"):
        adapter.predict(chunk)

    with pytest.raises(RuntimeError, match="MLX SileroVAD model is not loaded"):
        adapter.reset()

    # 2. Open adapter
    mock_mlx_model = MagicMock()
    mock_prob = MagicMock()
    mock_prob.item.return_value = 0.85
    mock_mlx_model.feed.return_value = (mock_prob, "state_1")

    with patch("mlx_audio.vad.load", return_value=mock_mlx_model) as mock_load:
        adapter.open()
        mock_load.assert_called_once_with(model_dir)

        # Predict
        pred = adapter.predict(chunk)
        assert pred.detected is True
        assert pred.score == 0.85
        assert adapter._state == "state_1"

        # Below threshold
        mock_prob.item.return_value = 0.3
        pred_low = adapter.predict(chunk)
        assert pred_low.detected is False
        assert pred_low.score == 0.3

        # Reset
        adapter.reset()
        assert adapter._state is None

        # Close
        adapter.close()
        assert adapter._model is None


def test_silero_vad_onnx_adapter_lifecycle(tmp_path: Path):
    """Verify SileroVADONNXAdapter lifecycle, predictions, reset and error handling."""
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    config = SileroVADONNXConfig(
        engine="onnx",
        model_path=model_file,
        threshold=0.5,
    )
    adapter = SileroVADONNXAdapter(config)
    chunk = AudioChunk(
        format=AudioFormat.MONO_16,
        samples=MagicMock(),
    )

    # 1. Require model before open raises RuntimeError
    with pytest.raises(RuntimeError, match="ONNX SileroVAD model is not loaded"):
        adapter.predict(chunk)

    # 2. Open adapter
    mock_onnx_model = MagicMock()
    mock_pred = MagicMock()
    mock_pred.item.return_value = 0.75
    mock_onnx_model.predict.return_value = mock_pred

    with patch(
        "helomi_core.vad.silero_vad.onnx_adapter.VAD", return_value=mock_onnx_model
    ) as mock_vad_cls:
        adapter.open()
        mock_vad_cls.assert_called_once_with(model_path=str(model_file))

        # Predict
        pred = adapter.predict(chunk)
        assert pred.detected is True
        assert pred.score == 0.75

        # Reset
        adapter.reset()
        mock_onnx_model.reset_states.assert_called_once()

        # Close
        adapter.close()
        assert adapter._model is None
