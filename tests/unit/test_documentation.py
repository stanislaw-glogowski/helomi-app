import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from helomi_app import ApplicationCommand, CommandResult

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DOCS = [
    ROOT / "README.md",
    *(ROOT / "docs").glob("*.md"),
    ROOT / "demo" / "README.md",
]


def test_local_documentation_links_exist() -> None:
    link_pattern = re.compile(r"\[[^]]+]\(([^)]+)\)")
    for document in PUBLIC_DOCS:
        for target in link_pattern.findall(document.read_text(encoding="utf-8")):
            path = target.split("#", 1)[0]
            if not path or "://" in path:
                continue
            assert (document.parent / path).exists(), (
                f"Broken link in {document}: {target}"
            )


def test_current_documentation_omits_obsolete_architecture_names() -> None:
    obsolete = (
        "helomi_common",
        "helomi_core",
        "helomi_app.common",
        "helomi_app.core",
        "PipelineService",
        "ParrotExtension",
        "ServerExtension",
    )
    for document in PUBLIC_DOCS:
        content = document.read_text(encoding="utf-8")
        for name in obsolete:
            assert name not in content, f"Obsolete name {name!r} in {document}"


def test_api_json_examples_match_public_command_models() -> None:
    content = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    examples = [
        json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", content, re.S)
    ]
    command_adapter = TypeAdapter(ApplicationCommand)

    for example in examples:
        if "type" in example:
            command_adapter.validate_python(example)
        elif "accepted" in example:
            CommandResult.model_validate(example)
