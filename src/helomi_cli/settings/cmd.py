from rich import print, print_json

from helomi_core import Runtime
from helomi_core.resources import LocalCatalog


def run_settings_cmd(
    local_catalog: LocalCatalog,
):
    runtime = Runtime(local_catalog)

    print("[italic cyan]Settings:[/italic cyan]")
    print_json(runtime.settings.model_dump_json())
    print()
