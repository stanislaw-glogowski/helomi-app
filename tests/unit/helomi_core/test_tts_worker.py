import pytest

from helomi_core.tts import TTSChunk, TTSProfile, TTSRequest, TTSWorker
from tests.fixtures.audio import create_raw_audio
from tests.fixtures.mocks import MockTTSAdapter


@pytest.mark.asyncio
async def test_tts_worker_synthesize_flow():
    """Verify TTSWorker synthesizes text into a stream of audio chunks."""
    raw1 = create_raw_audio(sample_rate=16000, duration=0.05)
    raw2 = create_raw_audio(sample_rate=16000, duration=0.05)

    adapter = MockTTSAdapter(chunks=[TTSChunk(audio=raw1), TTSChunk(audio=raw2)])
    worker = TTSWorker(adapter)
    profile = TTSProfile.model_validate({"adapter": "voxcpm2", "voxcpm2": {}})
    request = TTSRequest(text="Hello from Helomi")

    async with worker:
        results = [c async for c in worker.synthesize(request, profile)]

    assert len(results) == 2
    assert results[0].audio == raw1
    assert results[1].audio == raw2


@pytest.mark.asyncio
async def test_tts_worker_error_handling():
    """Verify TTSWorker propagates exceptions raised by adapter during synthesis."""
    adapter = MockTTSAdapter(chunks=[RuntimeError("Synthesis failure")])
    worker = TTSWorker(adapter)
    profile = TTSProfile.model_validate({"adapter": "voxcpm2", "voxcpm2": {}})
    request = TTSRequest(text="Hello")

    async with worker:
        with pytest.raises(RuntimeError, match="Synthesis failure"):
            async for _ in worker.synthesize(request, profile):
                pass


def test_tts_request_raw_text() -> None:
    """Verify TTSRequest.raw_text strips vocal delivery tags."""
    request = TTSRequest(text="Hello, world! [laughter] How are you? [breath]")
    assert request.raw_text == "Hello, world! How are you?"

    request_clean = TTSRequest(text="Just normal text.")
    assert request_clean.raw_text == "Just normal text."

    request_only_tags = TTSRequest(text="[sigh]")
    assert request_only_tags.raw_text == ""
