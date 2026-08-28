from unittest.mock import MagicMock, patch

from helomi_cli.settings.cmd import run_settings_cmd
from helomi_core.resources import LocalCatalog


def test_run_settings_cmd():
    """Verify run_settings_cmd prints settings json."""
    catalog = MagicMock(spec=LocalCatalog)
    mock_runtime = MagicMock()
    mock_runtime.settings.model_dump_json.return_value = '{"setting_key": "val"}'

    with (
        patch("helomi_cli.settings.cmd.Runtime", return_value=mock_runtime),
        patch("helomi_cli.settings.cmd.print") as mock_print,
        patch("helomi_cli.settings.cmd.print_json") as mock_print_json,
    ):
        run_settings_cmd(catalog)
        assert mock_print.called
        mock_print_json.assert_called_once_with('{"setting_key": "val"}')
