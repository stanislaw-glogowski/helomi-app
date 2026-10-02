import pytest

from helomi_runtime.detection import (
    ConversationEndedEvent,
    DetectionMode,
    DetectionWorker,
    TurnPrediction,
    TurnStatus,
    UtteranceContinuedEvent,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)
from tests.fixtures.audio import create_audio_chunk, create_raw_audio
from tests.fixtures.mocks import (
    MockTurnAdapter,
    MockVADAdapter,
    MockWakeWordAdapter,
)


@pytest.mark.asyncio
async def test_detection_worker_mode_and_wakeword_trigger():
    """Verify DetectionWorker transitions to UTTERANCE upon WakeWord match."""
    vad_adapter = MockVADAdapter(default_detected=True)
    turn_adapter = MockTurnAdapter()
    wakeword_adapter = MockWakeWordAdapter(matched="default")

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=wakeword_adapter,
    )
    assert worker.current_mode == DetectionMode.WAKEWORD

    raw = create_raw_audio(sample_rate=16000, num_samples=1024)

    async with worker:
        results = [r async for r in worker.detect(raw)]
        assert len(results) > 0
        assert any(
            isinstance(r, WakeWordDetectedEvent) and r.profile_id == "default"
            for r in results
        )
        assert worker.current_mode == DetectionMode.UTTERANCE


@pytest.mark.asyncio
async def test_detection_worker_wakeword_in_utterance_mode():
    """Verify wakeword is not omitted while in UTTERANCE mode."""
    vad_adapter = MockVADAdapter(default_detected=True)
    turn_adapter = MockTurnAdapter()
    wakeword_adapter = MockWakeWordAdapter(matched="alexa")

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=wakeword_adapter,
    )

    async with worker:
        await worker.set_mode(DetectionMode.UTTERANCE)
        assert worker.current_mode == DetectionMode.UTTERANCE

        raw = create_raw_audio(sample_rate=16000, num_samples=1024)
        results = [r async for r in worker.detect(raw)]

        assert any(
            isinstance(r, WakeWordDetectedEvent) and r.profile_id == "alexa"
            for r in results
        )


@pytest.mark.asyncio
async def test_detection_worker_turn_started():
    """Verify DetectionWorker yields UtteranceStarted when speech begins."""
    vad_adapter = MockVADAdapter(default_detected=True)
    turn_adapter = MockTurnAdapter(prediction=TurnPrediction(status=TurnStatus.STARTED))

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=None,
    )

    raw = create_raw_audio(sample_rate=16000, num_samples=512)

    async with worker:
        results = [r async for r in worker.detect(raw)]

    assert len(results) > 0
    assert any(isinstance(r, UtteranceStartedEvent) for r in results)


@pytest.mark.asyncio
async def test_detection_worker_utterance_detection():
    """Verify DetectionWorker in UTTERANCE mode yields UtteranceDetected."""
    vad_adapter = MockVADAdapter(default_detected=True)
    completed_chunk = create_audio_chunk(sample_rate=16000, num_samples=512)
    turn_adapter = MockTurnAdapter(
        prediction=TurnPrediction(
            status=TurnStatus.COMPLETED,
            audio=completed_chunk,
            score=0.9,
        )
    )

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=None,
    )
    assert worker.current_mode == DetectionMode.UTTERANCE

    raw = create_raw_audio(sample_rate=16000, num_samples=512)

    async with worker:
        results = [r async for r in worker.detect(raw)]

    assert len(results) > 0
    assert any(
        isinstance(r, UtteranceDetectedEvent) and r.audio == completed_chunk
        for r in results
    )


@pytest.mark.asyncio
async def test_detection_worker_turn_continuation():
    """Verify DetectionWorker yields UtteranceContinued when speech turn continues."""
    vad_adapter = MockVADAdapter(default_detected=True)
    turn_adapter = MockTurnAdapter(
        prediction=TurnPrediction(status=TurnStatus.CONTINUED)
    )

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=None,
    )

    raw = create_raw_audio(sample_rate=16000, num_samples=512)

    async with worker:
        results = [r async for r in worker.detect(raw)]

    assert len(results) > 0
    assert any(isinstance(r, UtteranceContinuedEvent) for r in results)


@pytest.mark.asyncio
async def test_detection_worker_timeout_and_conversation_ended():
    """Verify DetectionWorker yields ConversationEnded on TurnStatus.TIMEOUT."""
    vad_adapter = MockVADAdapter(default_detected=False)
    turn_adapter = MockTurnAdapter(prediction=TurnPrediction(status=TurnStatus.TIMEOUT))
    wakeword_adapter = MockWakeWordAdapter(matched=None)

    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=wakeword_adapter,
    )

    raw = create_raw_audio(sample_rate=16000, num_samples=512)

    async with worker:
        # Force switch to UTTERANCE mode while worker is open
        await worker.set_mode(DetectionMode.UTTERANCE)
        assert worker.current_mode == DetectionMode.UTTERANCE

        results = [r async for r in worker.detect(raw)]

    assert any(isinstance(r, ConversationEndedEvent) for r in results)
    assert worker.current_mode == DetectionMode.WAKEWORD


@pytest.mark.asyncio
async def test_detection_worker_change_mode_noop():
    """Verify change_mode is a no-op when setting identical mode."""
    vad_adapter = MockVADAdapter()
    turn_adapter = MockTurnAdapter()
    worker = DetectionWorker(
        turn_adapter=turn_adapter,
        vad_adapter=vad_adapter,
        wakeword_adapter=None,
    )
    async with worker:
        # Already in UTTERANCE mode
        await worker.set_mode(DetectionMode.UTTERANCE)
        assert worker.current_mode == DetectionMode.UTTERANCE
