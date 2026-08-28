from rich import print

from helomi_core.resources import LocalCatalog

from ..widgets import Spinner
from .openwakeword import install_openwakeword_models


async def run_install_cmd(
    local_catalog: LocalCatalog,
    spinner: Spinner,
):
    print()
    await install_openwakeword_models(spinner, local_catalog)
