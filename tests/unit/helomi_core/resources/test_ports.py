from pathlib import Path

from helomi_core.resources.ports import ResourceCatalog


class DummyCatalog(ResourceCatalog):
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root_path(self) -> Path:
        return self._root


def test_resource_catalog_build_path(tmp_path: Path) -> None:
    catalog = DummyCatalog(tmp_path)

    # assets
    assert catalog.build_path("assets") == tmp_path / "assets"
    assert catalog.build_path("assets", "p1") == tmp_path / "profiles" / "p1" / "assets"

    # models
    assert catalog.build_path("models") == tmp_path / "models"
    assert catalog.build_path("models", "p1") == tmp_path / "profiles" / "p1" / "models"

    # profiles
    assert catalog.build_path("profiles") == tmp_path / "profiles"
    assert catalog.build_path("profiles", "p1") == tmp_path / "profiles" / "p1"

    # fallback
    assert catalog.build_path("other") == tmp_path  # type: ignore[arg-type]
