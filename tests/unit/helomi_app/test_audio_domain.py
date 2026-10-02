from pathlib import Path

import numpy as np
import pytest

from helomi_runtime.audio import AudioChunk, AudioFile, AudioFormat, RawAudio
from helomi_runtime.audio.codec import (
    float32_to_int16,
    int16_to_float32,
    int16_to_mulaw,
    mulaw_to_float32,
)


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


def test_audio_formats_conversion_concat_and_validation(tmp_path: Path):
    assert AudioFormat.MONO_16.block_size == 512
    with pytest.raises(ValueError, match="greater than 0"):
        AudioFormat(0)
    with pytest.raises(ValueError, match="Only mono"):
        AudioFormat(16_000, 2)

    pcm = np.array([-32768, 0, 32767], dtype=np.int16).tobytes()
    raw = RawAudio.from_int16(pcm, AudioFormat.MONO_16)
    assert len(raw.data) == 12
    assert len(raw.to_int16()) == 6
    chunk = AudioChunk.from_int16(pcm, AudioFormat.MONO_16)
    assert chunk.to_raw() == raw
    assert chunk.to_bytes() == raw.data

    assert RawAudio.concat([raw]) is raw
    assert AudioChunk.concat([chunk]) is chunk
    assert (raw + raw).data == raw.data * 2
    assert len((chunk + chunk).samples) == 6
    with pytest.raises(ValueError, match="Empty sequence"):
        RawAudio.concat([])
    with pytest.raises(ValueError, match="Empty sequence"):
        AudioChunk.concat([])

    output = AudioFile(tmp_path / "audio")
    output.write(raw)
    assert output.path.suffix == ".wav"
    restored = output.read()
    assert restored.format == AudioFormat.MONO_16
    output.write(chunk)
    assert output.read().format.sample_rate == 16_000


def test_codec_empty_odd_and_clipping_paths():
    assert mulaw_to_float32(b"") == b""
    assert int16_to_mulaw(b"") == b""
    assert int16_to_mulaw(b"\x00") == b""
    assert len(int16_to_mulaw(b"\x00\x00\xff")) == 1
    samples = np.array([-2.0, 0.0, 2.0], dtype=np.float64)
    encoded = float32_to_int16(samples)
    decoded = np.frombuffer(int16_to_float32(encoded), dtype=np.float32)
    assert decoded[0] == pytest.approx(-1.0)
    assert decoded[-1] == pytest.approx(1.0)
