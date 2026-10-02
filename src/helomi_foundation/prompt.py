import re
from pathlib import Path
from typing import ClassVar


class PromptReader:
    """Load Markdown prompts and resolve their template parameters."""

    _PROMPTS_DIR: ClassVar[str] = "prompts"
    _PROMPT_PARAM_PATTERN: ClassVar[str] = r"\{\{\s*(.*?)\s*\}\}"

    @classmethod
    def _read_prompts(
        cls,
        root_path: Path,
        params: dict[str, str] | None = None,
    ) -> dict[str, str]:
        base_path = root_path / cls._PROMPTS_DIR
        values = params or {}
        return {
            path.relative_to(base_path).with_suffix("").as_posix(): cls._read_prompt(
                path, values
            )
            for path in base_path.rglob("*.md")
            if path.is_file()
        }

    @classmethod
    def _read_prompt(cls, path: Path, params: dict[str, str]) -> str:
        content = path.read_text(encoding="utf-8")
        if not params or not content:
            return content

        def replace_tag(match: re.Match[str]) -> str:
            key = match.group(1)
            if not key:
                raise ValueError(f"Empty prompt parameter: {path}")
            if key not in params:
                raise ValueError(f"Missing prompt parameter {key!r}: {path}")
            return params[key]

        return re.sub(cls._PROMPT_PARAM_PATTERN, replace_tag, content)
