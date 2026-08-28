import pytest

from helomi_core.audio import AudioFormat, AudioResampler
from tests.fixtures.audio import create_raw_audio
from tests.fixtures.mocks import MockAudioDriver


@pytest.mark.asyncio
async def test_audio_capture_and_resampling_pipeline():
    """Integration test: Audio capture stream -> AudioResampler generation."""
    # Generate 3 input chunks at 48kHz (each 0.1s -> 4800 samples)
    input_chunks = [
        create_raw_audio(sample_rate=48000, duration=0.1, freq=220.0),
        create_raw_audio(sample_rate=48000, duration=0.1, freq=440.0),
        create_raw_audio(sample_rate=48000, duration=0.1, freq=880.0),
    ]

    driver = MockAudioDriver(incoming_chunks=input_chunks)
    target_format = AudioFormat.MONO_16
    resampler = AudioResampler(target_format)

    captured_raw = []
    async with driver:
        async for chunk in driver.capture():
            captured_raw.append(chunk)
            if len(captured_raw) == 3:
                break

    assert len(captured_raw) == 3

    # Resample captured stream
    resampled_chunks = list(resampler.resample(captured_raw))

    assert len(resampled_chunks) > 0
    for chunk in resampled_chunks:
        assert chunk.format == target_format
        # Check conversion to PCM byte buffer
        width, pcm = chunk.to_pcm()
        assert width == 2
        assert len(pcm) == len(chunk.samples) * 2
