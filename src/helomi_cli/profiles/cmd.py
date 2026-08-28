from rich import print, print_json

from helomi_core import Runtime
from helomi_core.resources import LocalCatalog


def run_profiles_cmd(
    local_catalog: LocalCatalog,
    profile_id: str | None = None,
):
    runtime = Runtime(local_catalog)

    if profile_id is None:
        for profile in runtime.profiles.values():
            print(
                f"[italic cyan]Profile [magenta]{profile.id}[/magenta]:[/italic cyan]"
            )
            print_json(profile.model_dump_json())
            print()
        return

    profile = runtime.profiles.get(profile_id, None)
    if profile is None:
        print(f"[italic red]Profile not found: {profile_id}[/italic red]")
        return

    print_json(profile.model_dump_json())
    print()
