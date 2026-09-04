import os
from pathlib import Path
from unittest.mock import patch

from platformdirs import user_data_dir

from helomi_app.resources.user import UserData


def test_user_data_explicit_root(tmp_path: Path) -> None:
    ud = UserData(tmp_path)
    assert ud.root_path == tmp_path


def test_user_data_home_env_var(tmp_path: Path) -> None:
    custom_dir = tmp_path / "custom_helomi"
    custom_dir.mkdir()
    with patch.dict(os.environ, {"HELOMI_HOME": str(custom_dir)}):
        ud = UserData()
        assert ud.root_path == custom_dir


def test_user_data_local_dir_discovery(tmp_path: Path) -> None:
    helomi_dir = tmp_path / ".helomi"
    helomi_dir.mkdir()
    sub_dir = tmp_path / "sub" / "deep"
    sub_dir.mkdir(parents=True)

    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.cwd", return_value=sub_dir):
            ud = UserData()
            assert ud.root_path == helomi_dir


def test_user_data_fallback(tmp_path: Path) -> None:
    non_helomi_dir = tmp_path / "plain"
    non_helomi_dir.mkdir()

    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.cwd", return_value=non_helomi_dir):
            with patch.object(Path, "is_dir", return_value=False):
                ud = UserData()
                assert ud.root_path == Path(user_data_dir("HelomiApp"))
