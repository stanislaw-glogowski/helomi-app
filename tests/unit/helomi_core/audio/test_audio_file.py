from pathlib import Path

from helomi_core.audio.domain import AudioFile, AudioFormat
from tests.fixtures.audio import create_audio_chunk, create_raw_audio


def test_audio_file_read_write(tmp_path: Path) -> None:
    file_path = tmp_path / "recording.wav"
    audio_file = AudioFile(file_path)

    chunk = create_audio_chunk(sample_rate=16000, duration=0.1)
    audio_file.write(chunk, normalize=True)

    assert file_path.exists()
    raw = audio_file.read()
    assert raw.format == AudioFormat.MONO_16
    assert len(raw.data) == len(chunk.samples) * 2

    # Test writing raw audio directly
    raw_input = create_raw_audio(sample_rate=16000, duration=0.05)
    audio_file.write(raw_input)
    raw_read = audio_file.read()
    assert len(raw_read.data) == len(raw_input.data) // 2
