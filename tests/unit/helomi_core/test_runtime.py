from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_core.runtime import Runtime
from tests.fixtures.mocks import MockAudioDriver, MockResourceCatalog


@pytest.mark.asyncio
async def test_runtime_initialization_and_components(temp_helomi_store: Path) -> None:
    catalog = MockResourceCatalog(temp_helomi_store)
    runtime = Runtime(catalog)

    assert runtime.resources is catalog
    assert runtime.settings.profile.default == "default"
    assert len(runtime.profiles) == 1

    with (
        patch("helomi_core.runtime.get_audio_driver", return_value=MockAudioDriver()),
        patch("helomi_core.runtime.get_stt_adapter") as mock_stt,
        patch("helomi_core.runtime.get_tts_adapter") as mock_tts,
        patch("helomi_core.runtime.get_turn_adapter") as mock_turn,
        patch("helomi_core.runtime.get_vad_adapter") as mock_vad,
        patch("helomi_core.runtime.get_wakeword_adapter") as mock_ww,
    ):
        mock_stt.return_value = MagicMock()
        mock_tts.return_value = MagicMock()
        mock_turn.return_value = MagicMock()
        mock_vad.return_value = MagicMock()
        mock_ww.return_value = MagicMock()

        audio = await runtime.get_audio_driver()
        assert audio is not None

        stt = await runtime.get_stt_worker()
        assert stt is not None

        tts = await runtime.get_tts_worker()
        assert tts is not None

        det = await runtime.get_detection_worker()
        assert det is not None

        pipeline = await runtime.get_pipeline_service()
        assert pipeline is not None

        parrot = await runtime.get_parrot_extension()
        assert parrot is not None

        server = await runtime.get_server_extension()
        assert server is not None


@pytest.mark.asyncio
async def test_runtime_context_manager(temp_helomi_store: Path) -> None:
    catalog = MockResourceCatalog(temp_helomi_store)
    runtime = Runtime(catalog)

    dummy_cm = MagicMock()
    dummy_cm.__aenter__ = AsyncMock(return_value=dummy_cm)
    dummy_cm.__aexit__ = AsyncMock(return_value=None)

    async with runtime:
        await runtime._get_component(type(dummy_cm), lambda: dummy_cm)
        dummy_cm.__aenter__.assert_called_once()

    dummy_cm.__aexit__.assert_called_once()
