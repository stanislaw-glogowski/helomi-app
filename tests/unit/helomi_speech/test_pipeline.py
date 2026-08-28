import asyncio
from unittest.mock import patch

import pytest

from helomi_core.runtime import Runtime
from helomi_speech.domain import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    SayText,
)
from helomi_speech.pipeline import SpeechPipeline
from tests.fixtures.mocks import (
    MockAudioDriver,
    MockLocalCatalog,
    MockSTTAdapter,
    MockTTSAdapter,
    MockTurnAdapter,
    MockVADAdapter,
    MockWakeWordAdapter,
)


@pytest.fixture
def test_pipeline(mock_catalog: MockLocalCatalog) -> SpeechPipeline:
    """Create a SpeechPipeline instance backed by mocked runtime workers."""
    with (
        patch("helomi_core.runtime.get_audio_driver") as mock_get_audio,
        patch("helomi_core.runtime.get_turn_adapter") as mock_get_turn,
        patch("helomi_core.runtime.get_vad_adapter") as mock_get_vad,
        patch("helomi_core.runtime.get_wakeword_adapter") as mock_get_wakeword,
        patch("helomi_core.runtime.get_stt_adapter") as mock_get_stt,
        patch("helomi_core.runtime.get_tts_adapter") as mock_get_tts,
    ):
        mock_get_audio.return_value = MockAudioDriver()
        mock_get_turn.return_value = MockTurnAdapter()
        mock_get_vad.return_value = MockVADAdapter()
        mock_get_wakeword.return_value = MockWakeWordAdapter()
        mock_get_stt.return_value = MockSTTAdapter()
        mock_get_tts.return_value = MockTTSAdapter()

        runtime = Runtime(mock_catalog)
        pipeline = SpeechPipeline(runtime)
        return pipeline


@pytest.mark.asyncio
async def test_speech_pipeline_profile_activation_lifecycle(
    test_pipeline: SpeechPipeline,
):
    """Verify activating, re-activating, and deactivating profiles."""
    pipeline = test_pipeline
    assert pipeline.active_profile is None

    # First activation
    activated = await pipeline.activate_profile("default")
    assert activated is True
    assert pipeline.active_profile is not None
    assert pipeline.active_profile.id == "default"

    # Activating same profile again should return False
    re_activated = await pipeline.activate_profile("default")
    assert re_activated is False

    # Deactivation
    deactivated = await pipeline.deactivate_profile()
    assert deactivated is True
    assert pipeline.active_profile is None

    # Deactivating when already None returns False
    re_deactivated = await pipeline.deactivate_profile()
    assert re_deactivated is False


@pytest.mark.asyncio
async def test_speech_pipeline_say_text_and_publish(test_pipeline: SpeechPipeline):
    """Verify publishing commands to SpeechPipeline."""
    pipeline = test_pipeline

    # Publish ActivateProfile
    res_act = await pipeline.publish(ActivateProfile(profile_id="default"))
    assert res_act is True
    assert pipeline.active_profile is not None

    # Publish SayText
    res_say = await pipeline.publish(SayText(text="Hello from test"))
    assert res_say is True
    assert pipeline._tts_requests.qsize() == 1

    # Publish DeactivateProfile
    res_deact = await pipeline.publish(DeactivateProfile())
    assert res_deact is True
    assert pipeline.active_profile is None


@pytest.mark.asyncio
async def test_speech_pipeline_subscriptions_and_close(test_pipeline: SpeechPipeline):
    """Verify subscriber receives events and unblocks upon pipeline close."""
    pipeline = test_pipeline
    received_events = []

    async def subscriber():
        async for event in pipeline.subscribe():
            received_events.append(event)

    sub_task = asyncio.create_task(subscriber())
    # Allow subscriber queue registration
    await asyncio.sleep(0.01)

    await pipeline.activate_profile("default")
    await asyncio.sleep(0.01)

    assert len(received_events) == 1
    assert isinstance(received_events[0], ProfileActivated)

    # Closing pipeline sends None to subscriber to terminate iterator
    await pipeline._do_close()
    await sub_task


@pytest.mark.asyncio
async def test_speech_pipeline_loops(test_pipeline: SpeechPipeline):
    """Verify internal loops process detection, STT, and TTS requests."""
    pipeline = test_pipeline

    from helomi_core.stt import STTRequest
    from helomi_core.tts import TTSRequest
    from helomi_speech.domain import SpeechRequest
    from tests.fixtures.audio import create_audio_chunk

    sub_events = []

    async with pipeline:
        await pipeline.activate_profile("default")

        async def sub():
            async for ev in pipeline.subscribe():
                sub_events.append(ev)

        t = asyncio.create_task(sub())
        await asyncio.sleep(0.02)

        # 1. Test STT processing
        chunk = create_audio_chunk(sample_rate=16000, duration=0.05)
        stt_req = SpeechRequest(
            profile_id="default",
            data=STTRequest(audio=chunk),
            trace_id="test_trace",
        )
        pipeline._stt_requests.put_nowait(stt_req)
        await asyncio.sleep(0.05)

        assert any(e.type == "transcription_ready" for e in sub_events)

        # 2. Test TTS processing
        tts_req = SpeechRequest(
            profile_id="default",
            data=TTSRequest(text="Hello loop"),
        )
        pipeline._tts_requests.put_nowait(tts_req)
        await asyncio.sleep(0.05)

        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
