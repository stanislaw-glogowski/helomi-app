from unittest.mock import MagicMock, patch

from helomi_cli.print.cmd import run_print_cmd


def test_run_print_cmd_all():
    """Verify run_print_cmd with target=None prints both settings and profiles."""
    runtime = MagicMock()
    runtime.settings.model_dump_json.return_value = '{"setting_key": "setting_val"}'

    mock_profile = MagicMock()
    mock_profile.id = "default"
    mock_profile.model_dump_json.return_value = '{"profile_key": "profile_val"}'
    runtime.profiles = {"default": mock_profile}

    with (
        patch("helomi_cli.print.cmd.print") as mock_print,
        patch("helomi_cli.print.cmd.print_json") as mock_print_json,
    ):
        run_print_cmd(runtime, target=None)
        assert mock_print.called
        assert mock_print_json.call_count == 2


def test_run_print_cmd_settings_only():
    """Verify run_print_cmd with target='settings' prints only settings."""
    runtime = MagicMock()
    runtime.settings.model_dump_json.return_value = '{"setting_key": "setting_val"}'

    with (
        patch("helomi_cli.print.cmd.print") as mock_print,
        patch("helomi_cli.print.cmd.print_json") as mock_print_json,
    ):
        run_print_cmd(runtime, target="settings")
        assert mock_print.called
        assert mock_print_json.call_count == 1
        mock_print_json.assert_called_once_with('{"setting_key": "setting_val"}')


def test_run_print_cmd_profiles_all():
    """Verify run_print_cmd with target='profiles' prints all profiles."""
    runtime = MagicMock()
    p1 = MagicMock()
    p1.id = "p1"
    p1.model_dump_json.return_value = '{"id": "p1"}'
    p2 = MagicMock()
    p2.id = "p2"
    p2.model_dump_json.return_value = '{"id": "p2"}'
    runtime.profiles = {"p1": p1, "p2": p2}

    with (
        patch("helomi_cli.print.cmd.print") as mock_print,
        patch("helomi_cli.print.cmd.print_json") as mock_print_json,
    ):
        run_print_cmd(runtime, target="profiles", profile_id=None)
        assert mock_print.called
        assert mock_print_json.call_count == 2


def test_run_print_cmd_profiles_single_found():
    """Verify run_print_cmd prints specific profile when found."""
    runtime = MagicMock()
    p1 = MagicMock()
    p1.id = "p1"
    p1.model_dump_json.return_value = '{"id": "p1"}'
    runtime.profiles = {"p1": p1}

    with (
        patch("helomi_cli.print.cmd.print") as mock_print,
        patch("helomi_cli.print.cmd.print_json") as mock_print_json,
    ):
        run_print_cmd(runtime, target="profiles", profile_id="p1")
        assert mock_print.called
        mock_print_json.assert_called_once_with('{"id": "p1"}')


def test_run_print_cmd_profiles_single_not_found():
    """Verify run_print_cmd prints error when profile is not found."""
    runtime = MagicMock()
    runtime.profiles = {}

    with (
        patch("helomi_cli.print.cmd.print") as mock_print,
        patch("helomi_cli.print.cmd.print_json") as mock_print_json,
    ):
        run_print_cmd(runtime, target="profiles", profile_id="unknown")
        assert mock_print.called
        assert not mock_print_json.called
