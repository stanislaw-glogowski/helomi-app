import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"


def _get_imports(file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                parts = file_path.relative_to(SRC_DIR).parts[:-1]
                target = parts[: len(parts) - (node.level - 1)]
                module = (
                    f"{'.'.join(target)}.{node.module}"
                    if node.module
                    else ".".join(target)
                )
                imports.append(module)
            elif node.module:
                imports.append(node.module)
    return imports


def _assert_boundary(package: str, forbidden: tuple[str, ...]) -> None:
    files = list((SRC_DIR / package).rglob("*.py"))
    assert files, f"No files found in {package}"
    for file_path in files:
        for imported in _get_imports(file_path):
            assert not imported.startswith(forbidden), (
                f"Architecture violation: {file_path} imports {imported}"
            )


def test_dependency_direction() -> None:
    _assert_boundary(
        "helomi_foundation",
        ("helomi_runtime", "helomi_app", "helomi_cli", "helomi_tray"),
    )
    _assert_boundary(
        "helomi_runtime",
        ("helomi_app", "helomi_cli", "helomi_tray"),
    )
    _assert_boundary("helomi_app", ("helomi_cli", "helomi_tray"))
    _assert_boundary(
        "helomi_cli",
        ("helomi_foundation", "helomi_runtime", "helomi_tray"),
    )
    _assert_boundary(
        "helomi_tray",
        ("helomi_foundation", "helomi_runtime", "helomi_cli"),
    )


def test_obsolete_packages_are_removed() -> None:
    for relative in (
        "helomi_contracts",
        "helomi_app/common",
        "helomi_app/core",
        "helomi_app/pipeline",
        "helomi_app/profile",
        "helomi_app/reaction",
        "helomi_app/resources",
        "helomi_app/settings",
    ):
        assert not any((SRC_DIR / relative).glob("*.py")), relative
