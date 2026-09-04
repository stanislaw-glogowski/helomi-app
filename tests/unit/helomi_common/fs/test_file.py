from pathlib import Path
from typing import ClassVar

from helomi_common.fs.file import AbstractFile


class DummyFile(AbstractFile):
    _SUFFIXES: ClassVar[list[str]] = [".dummy", ".dm"]


class SuffixlessFile(AbstractFile):
    pass


def test_abstract_file_default_suffix(tmp_path: Path) -> None:
    f = DummyFile(tmp_path / "test")
    assert f.name == "test.dummy"
    assert f.path == tmp_path / "test.dummy"
    assert str(f) == str(tmp_path / "test.dummy")
    assert repr(f) == str(tmp_path / "test.dummy")
    assert not f.exists

    # When suffix is already given
    f2 = DummyFile(tmp_path / "test.dm")
    assert f2.name == "test.dm"
    assert f2.path == tmp_path / "test.dm"


def test_abstract_file_suffixless(tmp_path: Path) -> None:
    f = SuffixlessFile(tmp_path / "myfile")
    assert f.name == "myfile"
    assert f.path == tmp_path / "myfile"


def test_abstract_file_as_dir(tmp_path: Path) -> None:
    f = DummyFile(tmp_path / "archive.dummy")
    target_dir = f.as_dir()
    assert target_dir == tmp_path / "archive"
    assert not target_dir.exists()

    # ensure="exists"
    dir_exists = f.as_dir(ensure="exists")
    assert dir_exists.is_dir()

    # ensure="exists" when dir already exists does not raise FileExistsError
    dir_exists_again = f.as_dir(ensure="exists")
    assert dir_exists_again.is_dir()

    # ensure="empty"
    (dir_exists / "child.txt").write_text("hello", encoding="utf-8")
    assert (dir_exists / "child.txt").exists()
    emptied_dir = f.as_dir(ensure="empty")
    assert emptied_dir.is_dir()
    assert not (emptied_dir / "child.txt").exists()
