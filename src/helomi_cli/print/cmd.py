from typing import Literal

from rich import print, print_json

from helomi_core import Runtime


def run_print_cmd(
    runtime: Runtime,
    target: Literal["settings", "profiles", None] = None,
    profile_id: str | None = None,
):
    if target is None or target == "settings":
        print()
        print("[italic cyan]Settings:[/italic cyan]")
        print_json(runtime.settings.model_dump_json())
        print()

    if target is None or target == "profiles":
        if profile_id is None:
            for profile in runtime.profiles.values():
                print(
                    "[italic cyan]"
                    f"Profile [magenta]{profile.id}[/magenta]:"
                    "[/italic cyan]"
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
