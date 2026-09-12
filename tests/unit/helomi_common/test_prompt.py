from pathlib import Path

import pytest

from helomi_common import PromptReader


def test_prompt_reader_empty_or_missing_directory(tmp_path: Path) -> None:
    prompts = PromptReader._read_prompts(tmp_path)
    assert prompts == {}


def test_prompt_reader_read_prompts(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "simple.md").write_text(
        "You are a helpful assistant.", encoding="utf-8"
    )
    nested_dir = prompts_dir / "demo"
    nested_dir.mkdir()
    (nested_dir / "instructions.md").write_text(
        "Hello {{ name }}! Persona: {{ description }}.", encoding="utf-8"
    )

    result = PromptReader._read_prompts(
        tmp_path,
        params={"name": "Alexa", "description": "Helpful AI"},
    )

    assert result["simple"] == "You are a helpful assistant."
    assert result["demo/instructions"] == "Hello Alexa! Persona: Helpful AI."


def test_prompt_reader_empty_content_or_params(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    empty_file = prompts_dir / "empty.md"
    empty_file.write_text("", encoding="utf-8")

    no_params_file = prompts_dir / "no_params.md"
    no_params_file.write_text("Hello {{ name }}", encoding="utf-8")

    result = PromptReader._read_prompts(tmp_path, params=None)
    assert result["empty"] == ""
    assert result["no_params"] == "Hello {{ name }}"


def test_prompt_reader_missing_parameter_raises(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    file = prompts_dir / "test.md"
    file.write_text("Hello {{ missing }}", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing missing parameter"):
        PromptReader._read_prompts(tmp_path, params={"other": "val"})


def test_prompt_reader_empty_parameter_raises(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    file = prompts_dir / "test.md"
    file.write_text("Hello {{ }}", encoding="utf-8")

    with pytest.raises(ValueError, match="Empty parameter"):
        PromptReader._read_prompts(tmp_path, params={"other": "val"})
