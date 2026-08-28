from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_cli.install.cmd import run_install_cmd
from helomi_cli.install.openwakeword import (
    _download_model,
    _install_model,
    install_openwakeword_models,
)
from helomi_cli.widgets import Spinner
from helomi_core.resources import LocalCatalog


def test_download_model(tmp_path: Path):
    """Verify _download_model calls urlretrieve with release URL and target path."""
    with patch("helomi_cli.install.openwakeword.urlretrieve") as mock_urlretrieve:
        _download_model("test_model.onnx", tmp_path)
        base = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
        expected_url = f"{base}/test_model.onnx"
        mock_urlretrieve.assert_called_once_with(
            expected_url, tmp_path / "test_model.onnx"
        )


@pytest.mark.asyncio
async def test_install_model(tmp_path: Path):
    """Verify _install_model manages spinner and downloads model in threadpool."""
    spinner = MagicMock(spec=Spinner)
    spinner.start = AsyncMock()
    spinner.stop = AsyncMock()

    with patch("helomi_cli.install.openwakeword._download_model") as mock_download:
        await _install_model(spinner, "model.onnx", tmp_path)
        spinner.start.assert_called_once_with("model.onnx ...")
        mock_download.assert_called_once_with("model.onnx", tmp_path)
        spinner.stop.assert_called_once_with("model.onnx")


@pytest.mark.asyncio
async def test_install_openwakeword_models(tmp_path: Path):
    """Verify install_openwakeword_models iterates through model files."""
    spinner = MagicMock(spec=Spinner)
    spinner.start = AsyncMock()
    spinner.stop = AsyncMock()

    local_catalog = MagicMock(spec=LocalCatalog)
    local_catalog.root_path = tmp_path
    local_catalog.MODELS_DIR = "models"
    local_catalog.PROFILES_DIR = "profiles"

    with patch(
        "helomi_cli.install.openwakeword._install_model", new_callable=AsyncMock
    ) as mock_install:
        await install_openwakeword_models(spinner, local_catalog)
        assert mock_install.call_count == 4


@pytest.mark.asyncio
async def test_run_install_cmd():
    """Verify run_install_cmd entrypoint delegates to install_openwakeword_models."""
    spinner = MagicMock(spec=Spinner)
    local_catalog = MagicMock(spec=LocalCatalog)

    with patch(
        "helomi_cli.install.cmd.install_openwakeword_models", new_callable=AsyncMock
    ) as mock_install:
        await run_install_cmd(local_catalog, spinner)
        mock_install.assert_called_once_with(spinner, local_catalog)
