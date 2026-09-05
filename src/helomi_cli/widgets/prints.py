from rich import print

from helomi_core import Runtime


def print_welcome(runtime: Runtime, msg: str, profile_id: str | None = None):
    print()
    print(msg)

    _print_adapters(runtime)
    _print_profiles(runtime, profile_id)


def print_exit(action: str):
    print()
    print(f"[dim]Press [bold]Ctrl+C[/bold] to {action}.[/dim]")
    print()


def _print_profiles(runtime: Runtime, profile_id: str | None = None):
    print()
    print("[italic cyan]Profiles available:[/italic cyan]")
    default_profile = runtime.profiles.get(None)
    for profile in runtime.profiles:
        if profile.id == profile_id:
            tag = " [italic magenta]active[/italic magenta]"
        elif profile is default_profile:
            tag = " [italic dim]default[/italic dim]"
        else:
            tag = ""

        print(f"  [green]{profile.name}[/green] [white]({profile.id})[/white]{tag}")


def _print_adapter(label: str, adapter: str):
    print(f"  [green]{label}[/green][italic magenta]{adapter}[/italic magenta]")


def _print_adapters(runtime: Runtime):
    cfg = runtime.settings
    print()
    print("[italic cyan]Adapters used:[/italic cyan]")
    _print_adapter("Audio    ", cfg.audio.adapter)
    _print_adapter("Wakeword ", cfg.wakeword.adapter)
    _print_adapter("VAD      ", cfg.vad.adapter)
    _print_adapter("Turn     ", cfg.turn.adapter)
    _print_adapter("STT      ", cfg.stt.adapter)
    _print_adapter("TTS      ", cfg.tts.adapter)
