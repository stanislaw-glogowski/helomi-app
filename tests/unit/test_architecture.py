import ast
from pathlib import Path


def _get_imports_from_file(file_path: Path) -> list[str]:
    """Parse a python file and extract all imported module names."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_helomi_common_has_no_inward_dependencies() -> None:
    """helomi_common must have ZERO internal project dependencies."""
    common_dir = Path("src/helomi_common")
    for py_file in common_dir.rglob("*.py"):
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith(
                (
                    "helomi_core",
                    "helomi_cli",
                    "helomi_tray",
                )
            ), f"Architecture violation: {py_file} illegally imports {imp}"


def test_helomi_core_does_not_import_higher_layers() -> None:
    """helomi_core must not import from cli or tray."""
    core_dir = Path("src/helomi_core")
    for py_file in core_dir.rglob("*.py"):
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith(("helomi_cli", "helomi_tray")), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )


def test_helomi_cli_does_not_import_tray() -> None:
    """helomi_cli must not import from helomi_tray."""
    cli_dir = Path("src/helomi_cli")
    for py_file in cli_dir.rglob("*.py"):
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith("helomi_tray"), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )


def test_helomi_tray_does_not_import_cli() -> None:
    """helomi_tray must not import from helomi_cli."""
    tray_dir = Path("src/helomi_tray")
    for py_file in tray_dir.rglob("*.py"):
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith("helomi_cli"), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )
