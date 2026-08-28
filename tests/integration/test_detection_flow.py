import pytest

from helomi_core.detection.domain import (
    ConversationEnded,
    DetectionMode,
    ProfileDetected,
    UtteranceContinued,
    UtteranceDetected,
)
from helomi_core.detection.worker import DetectionWorker
from helomi_core.turn import TurnPrediction, TurnStatus
from tests.fixtures.audio import create_audio_chunk, create_raw_audio
from tests.fixtures.mocks import (
    MockTurnAdapter,
    MockVADAdapter,
    MockWakeWordAdapter,
)


@pytest.mark.asyncio
async def test_full_detection_flow_lifecycle():
    """Integration test: Audio -> Resampler -> VAD -> WakeWord -> Turn -> Timeout."""
    vad_adapter = MockVADAdapter(default_detected=True)
    wakeword_adapter = MockWakeWordAdapter()
    turn_adapter = MockTurnAdapter()

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=wakeword_adapter,
    )

    async with worker:
        # Phase 1: In PROFILE mode, simulate wake-word detection
        wakeword_adapter.matched = "gizmo"
        raw_audio_wake = create_raw_audio(sample_rate=16000, num_samples=512)
        events_wake = [ev async for ev in worker.detect(raw_audio_wake)]

        assert len(events_wake) == 1
        assert isinstance(events_wake[0], ProfileDetected)
        assert events_wake[0].profile_id == "gizmo"
        assert worker.current_mode == DetectionMode.UTTERANCE

        # Phase 2: In UTTERANCE mode, user begins speaking (continued)
        turn_adapter.next_prediction = TurnPrediction(status=TurnStatus.CONTINUED)
        raw_audio_speech = create_raw_audio(sample_rate=16000, num_samples=512)
        events_cont = [ev async for ev in worker.detect(raw_audio_speech)]

        assert len(events_cont) == 1
        assert isinstance(events_cont[0], UtteranceContinued)

        # Phase 3: User finishes speaking (completed turn)
        completed_chunk = create_audio_chunk(sample_rate=16000, num_samples=512)
        turn_adapter.next_prediction = TurnPrediction(
            status=TurnStatus.COMPLETED,
            audio=completed_chunk,
            score=0.95,
        )
        events_done = [ev async for ev in worker.detect(raw_audio_speech)]

        assert len(events_done) == 1
        assert isinstance(events_done[0], UtteranceDetected)
        assert events_done[0].audio == completed_chunk

        # Phase 4: Inactivity timeout triggers conversation end and resets mode
        turn_adapter.next_prediction = TurnPrediction(status=TurnStatus.TIMEOUT)
        events_timeout = [ev async for ev in worker.detect(raw_audio_speech)]

        assert len(events_timeout) == 1
        assert isinstance(events_timeout[0], ConversationEnded)
        assert worker.current_mode == DetectionMode.PROFILE
