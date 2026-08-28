from pathlib import Path
from typing import ClassVar

import pytest

from helomi_core.resources.files import (
    AbstractFile,
    ConfigData,
    ConfigFile,
    ConfigKind,
    TextFile,
    WAVFile,
)
from tests.fixtures.audio import create_audio_chunk


class CustomFile(AbstractFile):
    _SUFFIXES: ClassVar[list[str]] = [".custom", ".cst"]


def test_abstract_file_properties_and_as_dir(tmp_path: Path):
    """Verify AbstractFile name, path, exists, and as_dir operations."""
    file_path = tmp_path / "sample"
    custom_file = CustomFile(file_path)

    # Automatically attaches default suffix .custom
    assert custom_file.name == "sample.custom"
    assert custom_file.path == tmp_path / "sample.custom"
    assert not custom_file.exists

    # Create directory with as_dir
    dir_path = custom_file.as_dir(ensure="exists")
    assert dir_path.is_dir()
    assert dir_path.name == "sample"

    # Clean directory with ensure="empty"
    (dir_path / "temp.txt").write_text("content")
    empty_dir = custom_file.as_dir(ensure="empty")
    assert not (empty_dir / "temp.txt").exists()


def test_config_data_deep_extend():
    """Verify ConfigData recursive dictionary merging."""
    base = ConfigData(
        {
            "audio": {"channels": 1, "rate": 16000},
            "profile": "default",
        }
    )
    override = {
        "audio": {"rate": 48000},
        "extra": "value",
    }
    merged = base.extend(override)

    assert merged["audio"]["channels"] == 1
    assert merged["audio"]["rate"] == 48000
    assert merged["profile"] == "default"
    assert merged["extra"] == "value"


def test_config_file_yaml_read_write_and_uri_resolution(tmp_path: Path):
    """Verify ConfigFile reading, writing YAML, and resolving path:// URIs."""
    txt_file = tmp_path / "prompt.txt"
    txt_file.write_text("Custom prompt content", encoding="utf-8")

    yaml_file = tmp_path / "config.yml"
    config = ConfigFile(yaml_file)
    assert config.kind == ConfigKind.YAML

    data = ConfigData(
        {
            "name": "Test",
            "prompt_path": "path://prompt.txt",
            "prompt_text": "path://txt://prompt.txt",
        }
    )
    config.write(data)

    read_data = config.read()
    assert read_data["name"] == "Test"
    assert read_data["prompt_path"] == tmp_path / "prompt.txt"
    assert read_data["prompt_text"] == "Custom prompt content"


def test_config_file_json_read_write(tmp_path: Path):
    """Verify ConfigFile reading and writing JSON files."""
    json_path = tmp_path / "config.json"
    config = ConfigFile(json_path)
    assert config.kind == ConfigKind.JSON

    data = ConfigData({"key": "value", "items": [1, 2, 3]})
    config.write(data)

    read_data = config.read()
    assert read_data == data


def test_config_file_unsupported_extension(tmp_path: Path):
    """Verify ConfigFile raises ValueError on unsupported extensions."""
    invalid_path = tmp_path / "config.unknown"
    with pytest.raises(ValueError, match="Unsupported file type"):
        ConfigFile(invalid_path)


def test_config_file_read_configs_with_overrides(tmp_path: Path):
    """Verify read_configs combines base config and .override config."""
    base_file = tmp_path / "settings.yml"
    base_file.write_text("adapter: parakeet\nrate: 16000\n", encoding="utf-8")

    override_file = tmp_path / "settings.override.yml"
    override_file.write_text("rate: 44100\n", encoding="utf-8")

    loaded = ConfigFile.read_configs(tmp_path, "settings")
    assert loaded is not None
    assert loaded["adapter"] == "parakeet"
    assert loaded["rate"] == 44100
    assert loaded["root_path"] == tmp_path


def test_text_file_read_write(tmp_path: Path):
    """Verify TextFile read and write operations."""
    file_path = tmp_path / "notes.txt"
    text_file = TextFile(file_path)

    text_file.write("Hello TextFile")
    assert text_file.read() == "Hello TextFile"


def test_wav_file_read_write(tmp_path: Path):
    """Verify WAVFile writing and reading 16-bit PCM audio."""
    wav_path = tmp_path / "test.wav"
    wav_file = WAVFile(wav_path)

    original_chunk = create_audio_chunk(sample_rate=16000, duration=0.1)
    wav_file.write(original_chunk, normalize=True)

    raw_read = wav_file.read()
    assert raw_read.format.sample_rate == 16000
    assert raw_read.format.channels == 1
    assert len(raw_read.data) == len(original_chunk.samples) * 2
