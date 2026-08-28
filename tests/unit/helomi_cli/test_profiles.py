from unittest.mock import MagicMock, patch

from helomi_cli.profiles.cmd import run_profiles_cmd
from helomi_core.resources import LocalCatalog


def test_run_profiles_cmd_all():
    """Verify run_profiles_cmd prints all profiles when profile_id is None."""
    catalog = MagicMock(spec=LocalCatalog)
    mock_runtime = MagicMock()
    p1 = MagicMock()
    p1.id = "p1"
    p1.model_dump_json.return_value = '{"id": "p1"}'
    p2 = MagicMock()
    p2.id = "p2"
    p2.model_dump_json.return_value = '{"id": "p2"}'
    mock_runtime.profiles = {"p1": p1, "p2": p2}

    with (
        patch("helomi_cli.profiles.cmd.Runtime", return_value=mock_runtime),
        patch("helomi_cli.profiles.cmd.print") as mock_print,
        patch("helomi_cli.profiles.cmd.print_json") as mock_print_json,
    ):
        run_profiles_cmd(catalog, profile_id=None)
        assert mock_print.called
        assert mock_print_json.call_count == 2


def test_run_profiles_cmd_single_found():
    """Verify run_profiles_cmd prints profile json when profile_id exists."""
    catalog = MagicMock(spec=LocalCatalog)
    mock_runtime = MagicMock()
    p1 = MagicMock()
    p1.id = "p1"
    p1.model_dump_json.return_value = '{"id": "p1"}'
    mock_runtime.profiles = {"p1": p1}

    with (
        patch("helomi_cli.profiles.cmd.Runtime", return_value=mock_runtime),
        patch("helomi_cli.profiles.cmd.print"),
        patch("helomi_cli.profiles.cmd.print_json") as mock_print_json,
    ):
        run_profiles_cmd(catalog, profile_id="p1")
        assert mock_print_json.call_count == 1
        mock_print_json.assert_called_once_with('{"id": "p1"}')


def test_run_profiles_cmd_single_not_found():
    """Verify run_profiles_cmd prints error message when profile_id does not exist."""
    catalog = MagicMock(spec=LocalCatalog)
    mock_runtime = MagicMock()
    mock_runtime.profiles = {}

    with (
        patch("helomi_cli.profiles.cmd.Runtime", return_value=mock_runtime),
        patch("helomi_cli.profiles.cmd.print") as mock_print,
        patch("helomi_cli.profiles.cmd.print_json") as mock_print_json,
    ):
        run_profiles_cmd(catalog, profile_id="unknown")
        assert mock_print.called
        assert not mock_print_json.called
