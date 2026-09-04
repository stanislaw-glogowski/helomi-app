import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.config.profile import Profile
from helomi_app.pipeline.domain import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    SayText,
)
from helomi_app.pipeline.service import PipelineService
from helomi_core.audio import AudioDriver
from helomi_core.detection import (
    DetectionWorker,
)
from helomi_core.stt import STTWorker
from helomi_core.tts import TTSWorker


@pytest.fixture
def mock_profiles():
    prof1 = MagicMock(spec=Profile)
    prof1.id = "prof1"
    prof1.name = "Profile One"
    prof1.stt = MagicMock()
    prof1.tts = MagicMock()

    prof2 = MagicMock(spec=Profile)
    prof2.id = "prof2"
    prof2.name = "Profile Two"
    prof2.stt = MagicMock()
    prof2.tts = MagicMock()

    catalog = MagicMock()

    def _get_profile(k: str | None):
        return prof1 if k in ("prof1", None) else prof2

    catalog.get = MagicMock(side_effect=_get_profile)
    catalog.__iter__ = MagicMock(return_value=iter([prof1, prof2]))
    return catalog


@pytest.fixture
def mock_service(mock_profiles):
    audio_driver = MagicMock(spec=AudioDriver)
    audio_driver.start_room_voice = AsyncMock()
    audio_driver.stop_room_voice = AsyncMock()
    audio_driver.play = MagicMock()

    async def empty_capture():
        if False:
            yield None

    audio_driver.capture = empty_capture

    det_worker = MagicMock(spec=DetectionWorker)
    det_worker.change_mode = AsyncMock()

    stt_worker = MagicMock(spec=STTWorker)
    tts_worker = MagicMock(spec=TTSWorker)

    service = PipelineService(
        profiles=mock_profiles,
        audio_driver=audio_driver,
        detection_worker=det_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    return service, audio_driver, det_worker, stt_worker, tts_worker


@pytest.mark.asyncio
async def test_pipeline_service_activation_flow(mock_service) -> None:
    service, audio_driver, det_worker, _, _ = mock_service
    assert service.active_profile is None

    # First activation
    res = await service.execute(ActivateProfile(profile_id="prof1"))
    assert res is True
    assert service.active_profile.id == "prof1"
    audio_driver.start_room_voice.assert_called_once()
    det_worker.change_mode.assert_called_once()

    # Re-activating the same profile returns False
    res = await service.execute(ActivateProfile(profile_id="prof1"))
    assert res is False

    # Switching to prof2
    res = await service.execute(ActivateProfile(profile_id="prof2"))
    assert res is True
    assert service.active_profile.id == "prof2"

    # Deactivating profile
    res = await service.execute(DeactivateProfile())
    assert res is True
    assert service.active_profile is None
    audio_driver.stop_room_voice.assert_called_once()

    # Deactivating when already None returns False
    res = await service.execute(DeactivateProfile())
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_say_text(mock_service) -> None:
    service, _, _, _, _ = mock_service

    # SayText when active profile is None automatically activates default profile
    res = await service.execute(SayText(text="Hello world"))
    assert res is True
    assert service.active_profile.id == "prof1"
    assert not service._tts_queue.empty()

    # SayText with mismatching profile returns False
    res = await service.execute(SayText(text="Mismatch", profile_id="prof2"))
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_subscribe_and_close(mock_service) -> None:
    service, _, _, _, _ = mock_service
    events = []

    async def listener():
        async for evt in service.subscribe():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    await service.execute(ActivateProfile(profile_id="prof1"))
    await asyncio.sleep(0.01)

    assert len(events) == 1
    assert isinstance(events[0], ProfileActivated)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
