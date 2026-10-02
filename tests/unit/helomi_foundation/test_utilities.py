import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub.errors import HFValidationError, LocalEntryNotFoundError
from pydantic import ValidationError

from helomi_foundation import ConfigFile, ConfigFormat, DeepMergeDict, TextFile
from helomi_foundation.logger import LogLevel, configure_logger
from helomi_foundation.logger.formatter import pretty_log_formatter
from helomi_foundation.logger.proxy import TaggedStreamProxy
from helomi_foundation.prompt import PromptReader
from helomi_foundation.validation import HFModel


def test_deep_merge_and_file_helpers(tmp_path: Path):
    base = DeepMergeDict({"nested": {"left": 1}, "value": 1})
    assert base.merged_with() == base
    merged = base.merged_with({"nested": {"right": 2}, "value": 3})
    assert merged == {"nested": {"left": 1, "right": 2}, "value": 3}
    assert base["value"] == 1

    text = TextFile(tmp_path / "folder" / "note")
    assert text.path.suffix == ".txt"
    assert text.name == "note.txt"
    assert not text.exists
    text.write("hello")
    assert text.exists and text.read() == "hello"
    assert str(text) == repr(text) == str(text.path)


def test_config_file_formats_resolution_and_candidates(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TOKEN", "secret")
    yaml_file = ConfigFile(tmp_path / "settings.yml")
    assert yaml_file.kind == ConfigFormat.YAML
    yaml_file.write(
        {
            "token": "env://TOKEN",
            "path": "path://asset.bin",
            "items": ["custom://unchanged", 1],
        }
    )
    data = yaml_file.read()
    assert data["token"] == "secret"
    assert data["path"] == (tmp_path / "asset.bin").resolve()
    assert data["items"] == ["custom://unchanged", 1]
    assert ConfigFile.is_config(yaml_file.path)
    assert not ConfigFile.is_config(tmp_path / "missing.yml")
    assert ConfigFile._find_candidates(yaml_file.path) == [yaml_file.path]

    json_file = ConfigFile(tmp_path / "other.json")
    json_file.write({"unicode": "żółw"})
    assert json_file.kind == ConfigFormat.JSON
    assert json_file.read()["unicode"] == "żółw"

    (tmp_path / "empty.yml").write_text("", encoding="utf-8")
    assert ConfigFile(tmp_path / "empty.yml").read() == {}
    (tmp_path / "list.yml").write_text("- item\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be an object"):
        ConfigFile(tmp_path / "list.yml").read()
    with pytest.raises(ValueError, match="Unsupported"):
        ConfigFile(tmp_path / "settings.toml")


def test_config_base_override_and_duplicate_errors(tmp_path: Path):
    assert ConfigFile.read_merged(tmp_path / "missing") is None
    ConfigFile(tmp_path / "config.yml").write({"one": 1, "nested": {"a": 1}})
    ConfigFile(tmp_path / "config.override.json").write({"two": 2, "nested": {"b": 2}})
    assert ConfigFile.read_merged(tmp_path / "config") == {
        "one": 1,
        "two": 2,
        "nested": {"a": 1, "b": 2},
    }

    ConfigFile(tmp_path / "config.yaml").write({"duplicate": True})
    with pytest.raises(ValueError, match="Multiple configuration files"):
        ConfigFile.read_merged(tmp_path / "config")
    (tmp_path / "config.yaml").unlink()
    ConfigFile(tmp_path / "config.override.yml").write({"duplicate": True})
    with pytest.raises(ValueError, match="Multiple override files"):
        ConfigFile.read_merged(tmp_path / "config")


def test_prompt_reader_nested_templates_and_errors(tmp_path: Path):
    prompt_dir = tmp_path / "prompts" / "nested"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "hello.md").write_text("Hello {{ name }}", encoding="utf-8")
    (prompt_dir / "empty.md").write_text("", encoding="utf-8")
    prompts = PromptReader._read_prompts(tmp_path, {"name": "Alexa"})
    assert prompts == {"nested/hello": "Hello Alexa", "nested/empty": ""}
    assert PromptReader._read_prompt(prompt_dir / "hello.md", {}) == "Hello {{ name }}"

    (prompt_dir / "bad.md").write_text("{{ missing }}", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing prompt parameter"):
        PromptReader._read_prompt(prompt_dir / "bad.md", {"name": "Alexa"})
    (prompt_dir / "bad.md").write_text("{{ }}", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty prompt parameter"):
        PromptReader._read_prompt(prompt_dir / "bad.md", {"name": "Alexa"})


def test_log_formatter_and_tagged_stream_proxy():
    assert "component.ctx" in pretty_log_formatter(
        {"extra": {"component": "component", "context": "ctx"}}
    )
    assert "one.two" in pretty_log_formatter(
        {"extra": {"context": ["one", None, "two", ""]}}
    )
    assert "<cyan>" not in pretty_log_formatter({"extra": {}})

    stream = io.StringIO()
    proxy = TaggedStreamProxy(stream)
    assert proxy.write("hidden") == len("hidden")
    proxy.writelines([TaggedStreamProxy.tag("visible"), "hidden"])
    proxy.flush()
    assert stream.getvalue() == "visible"
    proxy.write("Traceback (most recent call last): details")
    proxy.write(" now visible")
    assert "now visible" in stream.getvalue()
    assert proxy.isatty() is False
    assert proxy.errors is None
    assert proxy.encoding is None
    with pytest.raises(io.UnsupportedOperation):
        proxy.fileno()
    assert proxy.getvalue() == stream.getvalue()

    unfiltered = io.StringIO()
    assert TaggedStreamProxy(unfiltered, skip_untagged=False).write("plain") == 5
    assert unfiltered.getvalue() == "plain"


def test_configure_logger_selects_formatter_and_sink():
    sink = io.StringIO()
    custom = MagicMock(return_value="formatted")
    original = sys.stderr
    with (
        patch("helomi_foundation.logger.configure.loguru.logger") as logger,
        patch.object(sys, "stderr", original),
    ):
        assert configure_logger(LogLevel.INFO, custom, sink, False) is logger
    logger.remove.assert_called_once()
    add = logger.add.call_args
    assert add.args[0] is sink
    assert add.kwargs["level"] == "INFO"
    rendered = add.kwargs["format"]({"extra": {}})
    assert "formatted" in rendered


def test_hugging_face_model_resolution(tmp_path: Path):
    with patch(
        "helomi_foundation.validation.hf.snapshot_download",
        return_value=str(tmp_path),
    ):
        model = HFModel("namespace/model")
        assert model.id == "namespace/model"
        assert model.namespace == "namespace"
        assert model.name == "model"
        assert model.path == tmp_path
        assert str(model) == model.id
        assert HFModel.model_validate(model) is model
        assert HFModel.model_validate({"id": "plain"}).namespace is None

    with pytest.raises(ValidationError, match="valid Hugging Face"):
        HFModel.model_validate({"name": "missing id"})
    for error, message in (
        (LocalEntryNotFoundError("missing"), "not found in the local cache"),
        (HFValidationError("invalid"), "Invalid Hugging Face model ID"),
        (RuntimeError("offline"), "Failed to resolve local Hugging Face model"),
    ):
        with patch(
            "helomi_foundation.validation.hf.snapshot_download", side_effect=error
        ):
            with pytest.raises(ValidationError, match=message):
                HFModel("bad")


def test_deferred_references_preserve_base_and_override_sources(tmp_path, monkeypatch):
    ConfigFile(tmp_path / "settings.yml").write(
        {"base": ["path://base.bin"], "inactive": "env://HELOMI_UNUSED_REFERENCE"}
    )
    ConfigFile(tmp_path / "settings.override.yml").write(
        {"override": "env://HELOMI_OVERRIDE_REFERENCE"}
    )
    data = ConfigFile.read_merged(tmp_path / "settings", resolve_references=False)
    data.pop("inactive")
    monkeypatch.setenv("HELOMI_OVERRIDE_REFERENCE", "value")
    resolved = ConfigFile.resolve_references(data)
    assert resolved == {"base": [tmp_path / "base.bin"], "override": "value"}
    assert data != resolved


def test_missing_deferred_reference_reports_original_override(tmp_path):
    ConfigFile(tmp_path / "settings.yml").write({})
    ConfigFile(tmp_path / "settings.override.yml").write(
        {"nested": {"token": "env://HELOMI_MISSING_DEFERRED_REFERENCE"}}
    )
    data = ConfigFile.read_merged(tmp_path / "settings", resolve_references=False)
    with pytest.raises(ValueError) as raised:
        ConfigFile.resolve_references(data)
    assert "settings.override.yml" in str(raised.value)
    assert "nested.token" in str(raised.value)
