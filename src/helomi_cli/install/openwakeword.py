import asyncio
from pathlib import Path
from urllib.request import urlretrieve

from rich import print

from helomi_core import Profile
from helomi_core.resources import LocalCatalog

from ..widgets import Spinner

_RELEASE_URL = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
_ROOT_MODELS = [
    "embedding_model.onnx",
    "melspectrogram.onnx",
    "silero_vad.onnx",
]
_PROFILE_MODEL = "alexa_v0.1.onnx"


def _download_model(file_name: str, dst_path: Path) -> None:
    url = f"{_RELEASE_URL}/{file_name}"
    file_path = dst_path / file_name
    urlretrieve(url, file_path)


async def _install_model(spinner: Spinner, file_name: str, dst_path: Path) -> None:
    await spinner.start(f"{file_name} ...")
    await asyncio.to_thread(_download_model, file_name, dst_path)
    await spinner.stop(f"{file_name}")


async def install_openwakeword_models(spinner: Spinner, local_catalog: LocalCatalog):
    models_root = local_catalog.root_path / local_catalog.MODELS_DIR

    print(
        "[italic cyan]Installing [magenta]OpenWakeWord[/magenta] models:[/italic cyan]"
    )
    for file_name in _ROOT_MODELS:
        await _install_model(spinner, file_name, models_root)

    models_root = (
        local_catalog.root_path
        / local_catalog.PROFILES_DIR
        / Profile.DEFAULT_ID
        / local_catalog.MODELS_DIR
    )

    await _install_model(spinner, _PROFILE_MODEL, models_root)
