import asyncio
from pathlib import Path
from urllib.request import urlretrieve

from rich import print

from helomi_core import Profile, Runtime

from ..widgets import Spinner

_OWW_RELEASE_URL = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
_OWW_ROOT_MODELS = [
    "embedding_model.onnx",
    "melspectrogram.onnx",
    "silero_vad.onnx",
]
_OWW_PROFILE_MODEL = "alexa_v0.1.onnx"


async def run_install_cmd(
    runtime: Runtime,
    spinner: Spinner,
):
    models_root = runtime.resources.build_path("models")

    print(
        "[italic cyan]Installing [magenta]OpenWakeWord[/magenta] models:[/italic cyan]"
    )
    for file_name in _OWW_ROOT_MODELS:
        await _install_oww_model(spinner, file_name, models_root)

    models_root = runtime.resources.build_path("models", Profile.DEFAULT_ID)

    await _install_oww_model(spinner, _OWW_PROFILE_MODEL, models_root)


def _download_oww_model(file_name: str, dst_path: Path) -> None:
    url = f"{_OWW_RELEASE_URL}/{file_name}"
    file_path = dst_path / file_name
    urlretrieve(url, file_path)


async def _install_oww_model(spinner: Spinner, file_name: str, dst_path: Path) -> None:
    await spinner.start(f"{file_name} ...")
    await asyncio.to_thread(_download_oww_model, file_name, dst_path)
    await spinner.stop(f"{file_name}")
