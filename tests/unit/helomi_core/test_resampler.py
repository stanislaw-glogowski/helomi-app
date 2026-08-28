from helomi_core.audio.domain import AudioFormat
from helomi_core.audio.resampler import AudioResampler
from tests.fixtures.audio import create_raw_audio


def test_resampler_same_sample_rate():
    """Verify resampling when input sample rate matches target sample rate."""
    fmt = AudioFormat.MONO_16
    resampler = AudioResampler(fmt)

    # 1024 samples at 16kHz -> exactly 2 blocks of 512 samples
    raw = create_raw_audio(sample_rate=16000, num_samples=1024)
    chunks = list(resampler.resample(raw, last=True))

    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.format == fmt
        assert len(chunk.samples) == fmt.block_size


def test_resampler_different_sample_rate():
    """Verify resampling when input sample rate differs from target sample rate."""
    fmt = AudioFormat.MONO_16
    resampler = AudioResampler(fmt)

    # 1 second of 48kHz audio (48000 samples) resamples to ~16000 samples (~31 blocks)
    raw = create_raw_audio(sample_rate=48000, duration=1.0)
    chunks = list(resampler.resample(raw, last=True))

    assert len(chunks) > 0
    total_samples = sum(len(c.samples) for c in chunks)
    # Total samples should be approximately 16000 (+/- filter delay adjustments)
    assert 15800 <= total_samples <= 16200


def test_resampler_streaming_chunks():
    """Verify resampler processing an iterable sequence of RawAudio chunks."""
    fmt = AudioFormat.MONO_16
    resampler = AudioResampler(fmt)

    raw_chunks = [
        create_raw_audio(sample_rate=44100, num_samples=1000) for _ in range(5)
    ]
    output_chunks = list(resampler.resample(raw_chunks))

    assert len(output_chunks) > 0
    for chunk in output_chunks:
        assert chunk.format == fmt


def test_resampler_reset():
    """Verify resampler reset clears stream buffers and cached streams."""
    fmt = AudioFormat.MONO_16
    resampler = AudioResampler(fmt)

    raw = create_raw_audio(sample_rate=48000, num_samples=500)
    # Incomplete chunk without last=True leaves residual in buffer
    list(resampler.resample(raw, last=False))

    resampler.reset()
    assert len(resampler._buffer) == 0
    assert len(resampler._streams) == 0
