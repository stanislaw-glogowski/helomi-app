import numpy as np
import pytest

from helomi_core.audio.domain import (
    AudioChunk,
    AudioFormat,
    AudioMode,
    RawAudio,
)


def test_audio_mode_properties_and_verification():
    """Verify AudioMode flags, compatibility checks, and validation logic."""
    assert AudioMode.INPUT.has_input
    assert not AudioMode.INPUT.has_output
    assert AudioMode.OUTPUT.has_output
    assert not AudioMode.OUTPUT.has_input
    assert AudioMode.DUPLEX.has_input
    assert AudioMode.DUPLEX.has_output

    assert AudioMode.DUPLEX.supports(AudioMode.INPUT)
    assert AudioMode.DUPLEX.supports(AudioMode.OUTPUT)
    assert AudioMode.DUPLEX.supports(AudioMode.DUPLEX)
    assert not AudioMode.INPUT.supports(AudioMode.OUTPUT)

    AudioMode.DUPLEX.verify(AudioMode.INPUT)
    with pytest.raises(RuntimeError, match="Expected audio mode: duplex, got input"):
        AudioMode.INPUT.verify(AudioMode.DUPLEX)


def test_audio_format_validation_and_block_size():
    """Verify AudioFormat constraints on sample rate and channels."""
    fmt = AudioFormat(sample_rate=16000, channels=1)
    assert fmt.sample_rate == 16000
    assert fmt.channels == 1
    assert fmt.block_size == 512  # round(16000 * 0.032)

    with pytest.raises(ValueError, match="Sample rate must be greater than 0"):
        AudioFormat(sample_rate=0, channels=1)

    with pytest.raises(ValueError, match="Only mono audio is supported"):
        AudioFormat(sample_rate=16000, channels=2)


def test_audio_format_singletons():
    """Verify predefined AudioFormat singletons."""
    assert AudioFormat.MONO_16.sample_rate == 16000
    assert AudioFormat.MONO_44.sample_rate == 44100
    assert AudioFormat.MONO_48.sample_rate == 48000


def test_raw_audio_operations():
    """Verify RawAudio concatenation and operator overloads."""
    fmt = AudioFormat.MONO_16
    raw1 = RawAudio(format=fmt, data=b"\x01\x02")
    raw2 = RawAudio(format=fmt, data=b"\x03\x04")

    combined = raw1 + raw2
    assert combined.data == b"\x01\x02\x03\x04"
    assert combined.format == fmt

    assert RawAudio.concat([raw1]) == raw1
    assert RawAudio.concat([raw1, raw2]).data == b"\x01\x02\x03\x04"

    with pytest.raises(ValueError, match="Empty sequence of chunks"):
        RawAudio.concat([])


def test_audio_chunk_conversions():
    """Verify AudioChunk conversions to and from RawAudio and PCM byte buffers."""
    fmt = AudioFormat.MONO_16
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    chunk = AudioChunk(format=fmt, samples=samples)

    # Roundtrip through RawAudio
    raw = chunk.to_raw()
    chunk_restored = AudioChunk.from_raw(raw)
    assert np.allclose(chunk.samples, chunk_restored.samples)

    # PCM conversion without normalization
    sample_width, pcm_bytes = chunk.to_pcm(normalize=False)
    assert sample_width == 2
    assert len(pcm_bytes) == len(samples) * 2

    # PCM conversion with normalization
    sample_width_norm, pcm_bytes_norm = chunk.to_pcm(normalize=True)
    assert sample_width_norm == 2
    assert len(pcm_bytes_norm) == len(samples) * 2


def test_audio_chunk_operations():
    """Verify AudioChunk concatenation and operator overloads."""
    fmt = AudioFormat.MONO_16
    chunk1 = AudioChunk(format=fmt, samples=np.array([1.0, 2.0], dtype=np.float32))
    chunk2 = AudioChunk(format=fmt, samples=np.array([3.0, 4.0], dtype=np.float32))

    combined = chunk1 + chunk2
    assert np.array_equal(combined.samples, np.array([1.0, 2.0, 3.0, 4.0]))

    assert AudioChunk.concat([chunk1]) == chunk1

    with pytest.raises(ValueError, match="Empty sequence of chunks"):
        AudioChunk.concat([])


def test_audio_chunk_to_mlx():
    """Verify AudioChunk conversion to MLX array."""
    fmt = AudioFormat.MONO_16
    chunk = AudioChunk(format=fmt, samples=np.array([0.1, 0.2], dtype=np.float32))
    mlx_arr = chunk.to_mlx()
    assert mlx_arr is not None
