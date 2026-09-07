import asyncio
from unittest.mock import patch

import pytest

from helomi_core.pipeline import (
    ActivateProfile,
    DeactivateProfile,
    PipelineEvent,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    TranscriptionReady,
)
from helomi_core.pipeline.service import PipelineRequest
from helomi_core.runtime import Runtime
from helomi_core.stt import STTChunk, STTRequest
from helomi_core.tts import TTSChunk
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
    """Integration test: PipelineService end-to-end event loops and message passing."""
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
            "helomi_core.runtime.get_wakeword_adapter",
            return_value=wakeword_adapter,
        ),
        patch("helomi_core.runtime.get_stt_adapter", return_value=stt_adapter),
        patch("helomi_core.runtime.get_tts_adapter", return_value=tts_adapter),
    ):
        runtime = Runtime(mock_catalog)

        async with runtime:
            pipeline = await runtime.get_pipeline_service()

            received_events: list[PipelineEvent] = []

            async def collect_events():
                async for event in pipeline.subscribe_event():
                    received_events.append(event)

            sub_task = asyncio.create_task(collect_events())
            await asyncio.sleep(0.02)

            # 1. Simulate Profile Activation
            await pipeline.execute_command(ActivateProfile(profile_id="alexa"))
            await asyncio.sleep(0.05)

            assert len(received_events) >= 1
            assert isinstance(received_events[-1], ProfileActivated)
            assert received_events[-1].profile_id == "alexa"

            # 2. Simulate Speech-to-Text input directly through queue
            speech_chunk = create_audio_chunk(sample_rate=16000, num_samples=512)
            pipeline._stt_queue.put_nowait(
                PipelineRequest(
                    data=STTRequest(audio=speech_chunk.to_raw()),
                )
            )
            await asyncio.sleep(0.05)

            transcription_events = [
                e for e in received_events if isinstance(e, TranscriptionReady)
            ]
            assert len(transcription_events) >= 1
            assert transcription_events[-1].text == "turn on the light"

            # 3. Publish SayText command to trigger TTS & Audio playback
            await pipeline.execute_command(SayText(text="I have turned on the light"))
            await asyncio.sleep(0.05)

            # Verify TTS playback occurred
            assert len(audio_driver.played_audio) > 0
            assert audio_driver.played_audio[0] == synth_raw

            # 4. Deactivate Profile
            await pipeline.execute_command(DeactivateProfile())
            await asyncio.sleep(0.05)

            assert isinstance(received_events[-1], ProfileDeactivated)

            sub_task.cancel()
            await asyncio.gather(sub_task, return_exceptions=True)
