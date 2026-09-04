from pathlib import Path

import pytest

from helomi_common.collections import DeepMergeDict
from helomi_common.fs.config import ConfigFile, ConfigKind


def test_config_file_kind_detection(tmp_path: Path) -> None:
    yaml_file = ConfigFile(tmp_path / "settings.yml")
    assert yaml_file.kind == ConfigKind.YAML

    json_file = ConfigFile(tmp_path / "settings.json")
    assert json_file.kind == ConfigKind.JSON

    with pytest.raises(ValueError, match="Unsupported file type"):
        ConfigFile(tmp_path / "settings.txt")


def test_config_file_is_config(tmp_path: Path) -> None:
    yaml_path = tmp_path / "test.yml"
    yaml_path.touch()
    assert ConfigFile.is_config(yaml_path)

    json_path = tmp_path / "test.json"
    json_path.touch()
    assert ConfigFile.is_config(json_path)

    txt_path = tmp_path / "test.txt"
    txt_path.touch()
    assert not ConfigFile.is_config(txt_path)


def test_config_file_read_write_yaml(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg = ConfigFile(cfg_path)
    data = DeepMergeDict({"app": {"name": "helomi", "port": 8080}})
    cfg.write(data)

    read_data = cfg.read()
    assert isinstance(read_data, DeepMergeDict)
    assert read_data["app"]["name"] == "helomi"
    assert read_data["app"]["port"] == 8080


def test_config_file_read_write_json(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg = ConfigFile(cfg_path)
    data = DeepMergeDict({"version": 1, "features": ["audio", "stt"]})
    cfg.write(data)

    read_data = cfg.read()
    assert isinstance(read_data, DeepMergeDict)
    assert read_data["version"] == 1
    assert read_data["features"] == ["audio", "stt"]


def test_config_file_prepare_data_path_resolution(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg = ConfigFile(cfg_path)
    model_file = tmp_path / "model.onnx"
    model_file.touch()

    data = DeepMergeDict({"model": "path://model.onnx", "url": "http://localhost:8000"})
    cfg.write(data)

    read_data = cfg.read()
    assert read_data["model"] == model_file
    assert read_data["url"] == "http://localhost:8000"


def test_config_file_read_configs_override_hierarchy(tmp_path: Path) -> None:
    base = tmp_path / "settings.yml"
    base.write_text("port: 8000\nhost: localhost\n", encoding="utf-8")

    override = tmp_path / "settings.override.yml"
    override.write_text("port: 9000\n", encoding="utf-8")

    data = ConfigFile.read_configs(tmp_path / "settings")
    assert data is not None
    assert data["port"] == 9000
    assert data["host"] == "localhost"


def test_config_file_read_configs_none_if_missing(tmp_path: Path) -> None:
    data = ConfigFile.read_configs(tmp_path / "nonexistent")
    assert data is None
