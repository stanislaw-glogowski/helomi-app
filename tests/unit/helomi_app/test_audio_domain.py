import numpy as np

from helomi_app.core.audio import AudioChunk, AudioFormat, RawAudio


def test_audio_mulaw_roundtrip():
    """Verify from_mulaw and to_mulaw on RawAudio and AudioChunk."""
    fmt = AudioFormat.MONO_16
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    chunk = AudioChunk(format=fmt, samples=samples)

    mulaw_bytes = chunk.to_mulaw()
    assert isinstance(mulaw_bytes, bytes)
    assert len(mulaw_bytes) == len(samples)

    # RawAudio from_mulaw
    raw = RawAudio.from_mulaw(mulaw_bytes, fmt)
    assert isinstance(raw, RawAudio)
    assert raw.format == fmt
    assert len(raw.data) == len(samples) * 4  # float32 = 4 bytes per sample

    # AudioChunk from_mulaw
    recovered_chunk = AudioChunk.from_mulaw(mulaw_bytes, fmt)
    assert isinstance(recovered_chunk, AudioChunk)
    assert recovered_chunk.format == fmt
    assert len(recovered_chunk.samples) == len(samples)
