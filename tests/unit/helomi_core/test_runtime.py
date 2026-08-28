from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helomi_core.runtime import Runtime
from tests.fixtures.mocks import MockLocalCatalog


def test_runtime_initialization_and_profile_selection(
    mock_catalog: MockLocalCatalog,
):
    """Verify Runtime initializes settings, profiles, and resolves profile by id."""
    runtime = Runtime(mock_catalog)
    assert runtime.settings.profile.default == "default"
    assert runtime.settings.audio.adapter == "avfaudio"
    assert "default" in runtime.profiles

    profile = runtime.get_profile("default")
    assert profile.id == "default"
    assert profile.name == "Default"

    # Default profile resolution when no ID provided
    resolved = runtime.get_profile()
    assert resolved.id == "default"

    with pytest.raises(ValueError, match="Profile not found: unknown"):
        runtime.get_profile("unknown")


def test_runtime_fallback_default_profile(
    sample_settings_dict: dict,
    sample_profiles_dict: dict,
    tmp_path: Path,
):
    """Verify Runtime falls back to first profile when default is empty."""
    sample_settings_dict["profile"]["default"] = ""

    catalog = MockLocalCatalog(
        root_path=tmp_path,
        settings_data=sample_settings_dict,
        profiles_data=sample_profiles_dict,
    )
    runtime = Runtime(catalog)
    assert runtime.get_profile().id == "default"


def test_runtime_worker_creation(mock_catalog: MockLocalCatalog):
    """Verify Runtime factory methods construct worker instances."""
    with (
        patch("helomi_core.runtime.get_audio_driver") as mock_get_audio,
        patch("helomi_core.runtime.get_turn_adapter") as mock_get_turn,
        patch("helomi_core.runtime.get_vad_adapter") as mock_get_vad,
        patch("helomi_core.runtime.get_wakeword_adapter") as mock_get_wakeword,
        patch("helomi_core.runtime.get_stt_adapter") as mock_get_stt,
        patch("helomi_core.runtime.get_tts_adapter") as mock_get_tts,
    ):
        mock_get_audio.return_value = MagicMock()
        mock_get_turn.return_value = MagicMock()
        mock_get_vad.return_value = MagicMock()
        mock_get_wakeword.return_value = MagicMock()
        mock_get_stt.return_value = MagicMock()
        mock_get_tts.return_value = MagicMock()

        runtime = Runtime(mock_catalog)

        audio_driver = runtime.get_audio_driver()
        assert audio_driver is not None

        det_worker = runtime.get_detection_worker()
        assert det_worker is not None

        stt_worker = runtime.get_stt_worker()
        assert stt_worker is not None

        tts_worker = runtime.get_tts_worker()
        assert tts_worker is not None

        with (
            patch("helomi_core.speech.SpeechPipeline") as mock_pipeline_cls,
            patch("helomi_core.server.Server") as mock_server_cls,
        ):
            pipeline = runtime.get_speech_pipeline()
            mock_pipeline_cls.assert_called_once_with(runtime)
            assert pipeline is not None

            server = runtime.get_server()
            mock_server_cls.assert_called_once_with(
                runtime=runtime,
                config=runtime.settings.server,
                auto_server=True,
            )
            assert server is not None
