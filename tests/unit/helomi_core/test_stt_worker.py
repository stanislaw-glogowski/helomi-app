import pytest

from helomi_core.stt import (
    STTChunk,
    STTRequest,
    STTResponse,
    STTWorker,
)
from helomi_core.stt.config import STTProfile
from tests.fixtures.audio import create_audio_chunk
from tests.fixtures.mocks import MockSTTAdapter


def test_stt_response_from_chunks():
    """Verify STTResponse aggregates chunks into a single concatenated text string."""
    assert STTResponse.from_chunks([]) is None

    chunks = [STTChunk(text="Hello"), STTChunk(text="world")]
    response = STTResponse.from_chunks(chunks)
    assert response is not None
    assert response.text == "Hello world"


@pytest.mark.asyncio
async def test_stt_worker_transcribe_flow():
    """Verify STTWorker transcribes audio sequence and emits response."""
    adapter = MockSTTAdapter(
        chunks=[STTChunk(text="Testing"), STTChunk(text="transcription")]
    )
    worker = STTWorker(adapter)
    profile = STTProfile.model_validate({"adapter": "parakeet", "parakeet": {}})

    chunk = create_audio_chunk(sample_rate=16000, duration=0.1)
    request = STTRequest(audio=chunk)

    async with worker:
        results = [r async for r in worker.transcribe(request, profile)]

    assert len(results) == 3
    assert isinstance(results[0], STTChunk)
    assert results[0].text == "Testing"
    assert isinstance(results[1], STTChunk)
    assert results[1].text == "transcription"
    assert isinstance(results[2], STTResponse)
    assert results[2].text == "Testing transcription"


@pytest.mark.asyncio
async def test_stt_worker_error_handling():
    """Verify STTWorker propagates exceptions raised by adapter during transcription."""
    adapter = MockSTTAdapter(chunks=[ValueError("Adapter transcription error")])
    worker = STTWorker(adapter)
    profile = STTProfile.model_validate({"adapter": "parakeet", "parakeet": {}})

    chunk = create_audio_chunk(sample_rate=16000, duration=0.1)
    request = STTRequest(audio=chunk)

    async with worker:
        with pytest.raises(ValueError, match="Adapter transcription error"):
            async for _ in worker.transcribe(request, profile):
                pass
