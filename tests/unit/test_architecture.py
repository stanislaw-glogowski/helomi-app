import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"


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
    common_dir = SRC_DIR / "helomi_common"
    py_files = list(common_dir.rglob("*.py"))
    assert len(py_files) > 0, "No files found in helomi_common"
    for py_file in py_files:
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
    core_dir = SRC_DIR / "helomi_core"
    py_files = list(core_dir.rglob("*.py"))
    assert len(py_files) > 0, "No files found in helomi_core"
    for py_file in py_files:
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith(("helomi_cli", "helomi_tray")), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )


def test_helomi_cli_does_not_import_tray() -> None:
    """helomi_cli must not import from helomi_tray."""
    cli_dir = SRC_DIR / "helomi_cli"
    py_files = list(cli_dir.rglob("*.py"))
    assert len(py_files) > 0, "No files found in helomi_cli"
    for py_file in py_files:
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith("helomi_tray"), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )


def test_helomi_tray_does_not_import_cli() -> None:
    """helomi_tray must not import from helomi_cli."""
    tray_dir = SRC_DIR / "helomi_tray"
    py_files = list(tray_dir.rglob("*.py"))
    assert len(py_files) > 0, "No files found in helomi_tray"
    for py_file in py_files:
        imports = _get_imports_from_file(py_file)
        for imp in imports:
            assert not imp.startswith("helomi_cli"), (
                f"Architecture violation: {py_file} illegally imports {imp}"
            )
