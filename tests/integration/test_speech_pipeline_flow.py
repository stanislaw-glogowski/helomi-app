import asyncio
from unittest.mock import patch

import pytest

from helomi_core.runtime import Runtime
from helomi_core.stt import STTChunk
from helomi_core.tts import TTSChunk
from helomi_speech.domain import (
    ProfileActivated,
    ProfileDeactivated,
    SayText,
)
from helomi_speech.pipeline import SpeechPipeline
from tests.fixtures.audio import create_audio_chunk, create_raw_audio
from tests.fixtures.mocks import (
    MockAudioDriver,
    MockLocalCatalog,
    MockSTTAdapter,
    MockTTSAdapter,
    MockTurnAdapter,
    MockVADAdapter,
    MockWakeWordAdapter,
)


@pytest.mark.asyncio
async def test_speech_pipeline_end_to_end_flow(mock_catalog: MockLocalCatalog):
    """Integration test: SpeechPipeline end-to-end event loops and message passing."""
    audio_driver = MockAudioDriver()
    turn_adapter = MockTurnAdapter()
    vad_adapter = MockVADAdapter()
    wakeword_adapter = MockWakeWordAdapter()
    stt_adapter = MockSTTAdapter(chunks=[STTChunk(text="turn on the light")])
    synth_raw = create_raw_audio(sample_rate=16000, duration=0.05)
    tts_adapter = MockTTSAdapter(chunks=[TTSChunk(audio=synth_raw)])

    with (
        patch("helomi_core.runtime.get_audio_driver", return_value=audio_driver),
        patch("helomi_core.runtime.get_turn_adapter", return_value=turn_adapter),
        patch("helomi_core.runtime.get_vad_adapter", return_value=vad_adapter),
        patch(
            "helomi_core.runtime.get_wakeword_adapter", return_value=wakeword_adapter
        ),
        patch("helomi_core.runtime.get_stt_adapter", return_value=stt_adapter),
        patch("helomi_core.runtime.get_tts_adapter", return_value=tts_adapter),
    ):
        runtime = Runtime(mock_catalog)
        pipeline = SpeechPipeline(runtime)

        received_events = []

        async def collect_events():
            async for event in pipeline.subscribe():
                received_events.append(event)

        async with pipeline:
            sub_task = asyncio.create_task(collect_events())
            await asyncio.sleep(0.02)

            # 1. Simulate Profile Activation via WakeWord
            await pipeline.activate_profile("default")
            await asyncio.sleep(0.02)

            assert len(received_events) >= 1
            assert isinstance(received_events[-1], ProfileActivated)

            # 2. Simulate Speech-to-Text input directly through loop queue
            speech_chunk = create_audio_chunk(sample_rate=16000, num_samples=512)
            # Enqueue UtteranceDetected into STT queue via detection loop logic
            pipeline._detection_queue.put_nowait(speech_chunk.to_raw())
            await asyncio.sleep(0.05)

            # 3. Publish SayText command to trigger TTS & Audio playback
            await pipeline.publish(SayText(text="I have turned on the light"))
            await asyncio.sleep(0.05)

            # Verify TTS playback occurred
            assert len(audio_driver.played_audio) > 0
            assert audio_driver.played_audio[0] == synth_raw

            # 4. Deactivate Profile
            await pipeline.deactivate_profile()
            await asyncio.sleep(0.02)

            assert isinstance(received_events[-1], ProfileDeactivated)

        sub_task.cancel()
        await asyncio.gather(sub_task, return_exceptions=True)
