from rich import print

from helomi_app import Application


def print_welcome(
    application: Application,
    msg: str,
    profile_id: str | None = None,
):
    print()
    print(msg)

    _print_adapters(application)
    _print_profiles(application, profile_id)


def print_exit(action: str):
    print()
    print(f"[dim]Press [bold]Ctrl+C[/bold] to {action}.[/dim]")
    print()


def _print_profiles(application: Application, profile_id: str | None = None):
    print()
    print("[italic cyan]Profiles available:[/italic cyan]")
    for profile in application.profiles:
        if profile.id == profile_id:
            tag = " [italic magenta]active[/italic magenta]"
        else:
            tag = ""

        print(f"  [green]{profile.name}[/green] [white]({profile.id})[/white]{tag}")


def _print_adapter(label: str, adapter: str):
    print(f"  [green]{label}[/green][italic magenta]{adapter}[/italic magenta]")


def _print_adapters(application: Application):
    settings = application.settings
    print()
    print("[italic cyan]Adapters used:[/italic cyan]")
    _print_adapter(
        "Audio    ",
        ", ".join(settings.audio.drivers),
    )
    _print_adapter(
        "Wakeword ",
        settings.detection.wakeword.adapter
        if settings.detection.wakeword
        else "disabled",
    )
    _print_adapter("VAD      ", settings.detection.vad.adapter)
    _print_adapter("Turn     ", settings.detection.turn.adapter)
    _print_adapter("STT      ", settings.transcription.adapter)
    _print_adapter("TTS      ", settings.synthesis.adapter)
