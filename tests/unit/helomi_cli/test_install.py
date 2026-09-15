from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helomi_app import Runtime
from helomi_cli.commands.install import (
    _OWW_ROOT_MODELS,
    _download_oww_model,
    _install_oww_model,
    run_install_cmd,
)
from helomi_cli.widgets import Spinner


def test_download_oww_model(tmp_path: Path) -> None:
    with patch("helomi_cli.commands.install.urlretrieve") as mock_urlretrieve:
        _download_oww_model("model.onnx", tmp_path)
        mock_urlretrieve.assert_called_once_with(
            "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/model.onnx",
            tmp_path / "model.onnx",
        )


@pytest.mark.asyncio
async def test_install_oww_model(tmp_path: Path) -> None:
    spinner = MagicMock(spec=Spinner)
    spinner.start = AsyncMock()
    spinner.stop = AsyncMock()

    with patch("helomi_cli.commands.install._download_oww_model") as mock_download:
        await _install_oww_model(spinner, "model.onnx", tmp_path)
        spinner.start.assert_called_once_with("model.onnx ...")
        mock_download.assert_called_once_with("model.onnx", tmp_path)
        spinner.stop.assert_called_once_with("model.onnx")


@pytest.mark.asyncio
async def test_run_install_cmd(tmp_path: Path) -> None:
    spinner = MagicMock(spec=Spinner)
    spinner.start = AsyncMock()
    spinner.stop = AsyncMock()

    runtime = MagicMock(spec=Runtime)
    runtime.resources = MagicMock()
    runtime.resources.build_path = MagicMock(return_value=tmp_path)

    with patch(
        "helomi_cli.commands.install._install_oww_model", new_callable=AsyncMock
    ) as mock_install:
        await run_install_cmd(runtime, spinner)
        expected_calls = len(_OWW_ROOT_MODELS) + 1
        assert mock_install.call_count == expected_calls
