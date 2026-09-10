from pathlib import Path
from unittest.mock import MagicMock, patch

import AppKit
import pytest

from helomi_tray.app.dialogs import BaseDialog, SaveFileDialog


def test_base_dialog_activate_lifecycle():
    """Verify BaseDialog._activate context manager elevates and restores policy."""
    mock_app = MagicMock()
    mock_app_cls = MagicMock()
    mock_app_cls.sharedApplication.return_value = mock_app

    dialog = BaseDialog()
    with patch("helomi_tray.app.dialogs.base.NSApplication", mock_app_cls):
        with dialog._activate():
            mock_app.setActivationPolicy_.assert_called_once_with(
                AppKit.NSApplicationActivationPolicyRegular
            )
            mock_app.activateIgnoringOtherApps_.assert_called_once_with(True)

        mock_app.setActivationPolicy_.assert_called_with(
            AppKit.NSApplicationActivationPolicyAccessory
        )


def test_base_dialog_activate_exception_restores_policy():
    """Verify BaseDialog._activate restores policy even on exception."""
    mock_app = MagicMock()
    mock_app_cls = MagicMock()
    mock_app_cls.sharedApplication.return_value = mock_app

    dialog = BaseDialog()
    with patch("helomi_tray.app.dialogs.base.NSApplication", mock_app_cls):
        with pytest.raises(RuntimeError, match="Error inside context"):
            with dialog._activate():
                raise RuntimeError("Error inside context")

        mock_app.setActivationPolicy_.assert_called_with(
            AppKit.NSApplicationActivationPolicyAccessory
        )


def test_save_file_dialog_success(tmp_path: Path):
    out_file = tmp_path / "test.wav"

    mock_panel = MagicMock()
    mock_panel.runModal.return_value = AppKit.NSModalResponseOK
    mock_url = MagicMock()
    mock_url.path.return_value = str(out_file)
    mock_panel.URL.return_value = mock_url

    mock_panel_cls = MagicMock()
    mock_panel_cls.savePanel.return_value = mock_panel

    mock_app = MagicMock()
    mock_app_cls = MagicMock()
    mock_app_cls.sharedApplication.return_value = mock_app

    with (
        patch("helomi_tray.app.dialogs.save_file.NSSavePanel", mock_panel_cls),
        patch("helomi_tray.app.dialogs.base.NSApplication", mock_app_cls),
    ):
        result = SaveFileDialog(
            title="Custom Save",
            default_name="custom.wav",
            allowed_types=["wav"],
        ).open()

        assert result == out_file
        mock_panel.setTitle_.assert_called_once_with("Custom Save")
        mock_panel.setNameFieldStringValue_.assert_called_once_with("custom.wav")
        mock_panel.setAllowedFileTypes_.assert_called_once_with(["wav"])
        mock_app.setActivationPolicy_.assert_any_call(
            AppKit.NSApplicationActivationPolicyRegular
        )
        mock_app.setActivationPolicy_.assert_called_with(
            AppKit.NSApplicationActivationPolicyAccessory
        )


def test_save_file_dialog_cancelled():
    mock_panel = MagicMock()
    mock_panel.runModal.return_value = AppKit.NSModalResponseCancel

    mock_panel_cls = MagicMock()
    mock_panel_cls.savePanel.return_value = mock_panel

    mock_app = MagicMock()
    mock_app_cls = MagicMock()
    mock_app_cls.sharedApplication.return_value = mock_app

    with (
        patch("helomi_tray.app.dialogs.save_file.NSSavePanel", mock_panel_cls),
        patch("helomi_tray.app.dialogs.base.NSApplication", mock_app_cls),
    ):
        result = SaveFileDialog(title="Save").open()
        assert result is None
        mock_app.setActivationPolicy_.assert_called_with(
            AppKit.NSApplicationActivationPolicyAccessory
        )


def test_save_file_dialog_none_url():
    mock_panel = MagicMock()
    mock_panel.runModal.return_value = AppKit.NSModalResponseOK
    mock_panel.URL.return_value = None

    mock_panel_cls = MagicMock()
    mock_panel_cls.savePanel.return_value = mock_panel

    mock_app = MagicMock()
    mock_app_cls = MagicMock()
    mock_app_cls.sharedApplication.return_value = mock_app

    with (
        patch("helomi_tray.app.dialogs.save_file.NSSavePanel", mock_panel_cls),
        patch("helomi_tray.app.dialogs.base.NSApplication", mock_app_cls),
    ):
        result = SaveFileDialog(title="Save").open()
        assert result is None
        mock_app.setActivationPolicy_.assert_called_with(
            AppKit.NSApplicationActivationPolicyAccessory
        )
