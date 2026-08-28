import numpy as np

from helomi_core.audio import AudioChunk, AudioFormat, RawAudio


def generate_sine_wave(
    sample_rate: int = 16000,
    duration: float = 1.0,
    freq: float = 440.0,
    num_samples: int | None = None,
) -> np.ndarray:
    """Generate a floating point sine wave array with float32 precision."""
    if num_samples is None:
        num_samples = int(sample_rate * duration)
    t = np.linspace(0, num_samples / sample_rate, num_samples, endpoint=False)
    samples = 0.5 * np.sin(2 * np.pi * freq * t)
    return samples.astype(np.float32)


def create_audio_chunk(
    sample_rate: int = 16000,
    duration: float = 1.0,
    freq: float = 440.0,
    num_samples: int | None = None,
) -> AudioChunk:
    """Create an AudioChunk containing synthetic sine wave audio."""
    samples = generate_sine_wave(
        sample_rate=sample_rate,
        duration=duration,
        freq=freq,
        num_samples=num_samples,
    )
    return AudioChunk(
        format=AudioFormat(sample_rate=sample_rate, channels=1),
        samples=samples,
    )


def create_raw_audio(
    sample_rate: int = 16000,
    duration: float = 1.0,
    freq: float = 440.0,
    num_samples: int | None = None,
) -> RawAudio:
    """Create a RawAudio object containing synthetic sine wave audio."""
    chunk = create_audio_chunk(
        sample_rate=sample_rate,
        duration=duration,
        freq=freq,
        num_samples=num_samples,
    )
    return chunk.to_raw()


def create_silence_chunk(
    sample_rate: int = 16000,
    duration: float = 1.0,
    num_samples: int | None = None,
) -> AudioChunk:
    """Create an AudioChunk containing digital silence (zeros)."""
    if num_samples is None:
        num_samples = int(sample_rate * duration)
    samples = np.zeros(num_samples, dtype=np.float32)
    return AudioChunk(
        format=AudioFormat(sample_rate=sample_rate, channels=1),
        samples=samples,
    )


def create_silence_raw_audio(
    sample_rate: int = 16000,
    duration: float = 1.0,
    num_samples: int | None = None,
) -> RawAudio:
    """Create a RawAudio object containing digital silence."""
    return create_silence_chunk(
        sample_rate=sample_rate,
        duration=duration,
        num_samples=num_samples,
    ).to_raw()


def create_noise_chunk(
    sample_rate: int = 16000,
    duration: float = 1.0,
    num_samples: int | None = None,
    scale: float = 0.05,
) -> AudioChunk:
    """Create an AudioChunk containing uniform random noise."""
    if num_samples is None:
        num_samples = int(sample_rate * duration)
    samples = np.random.uniform(-scale, scale, num_samples).astype(np.float32)
    return AudioChunk(
        format=AudioFormat(sample_rate=sample_rate, channels=1),
        samples=samples,
    )


def create_noise_raw_audio(
    sample_rate: int = 16000,
    duration: float = 1.0,
    num_samples: int | None = None,
    scale: float = 0.05,
) -> RawAudio:
    """Create a RawAudio object containing uniform random noise."""
    return create_noise_chunk(
        sample_rate=sample_rate,
        duration=duration,
        num_samples=num_samples,
        scale=scale,
    ).to_raw()
