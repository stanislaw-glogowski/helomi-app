import asyncio

from rich import print

from helomi_app import Application
from helomi_app.messages import (
    ActivationSource,
    CallEndedEvent,
    CallStartedEvent,
    ConversationState,
    DriverChangedEvent,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    TranscriptionReadyEvent,
)

from ..widgets import Spinner, print_exit, print_welcome


async def run_parrot_cmd(
    application: Application,
    shutdown: asyncio.Event,
    profile_id: str | None,
    spinner: Spinner,
):
    print()
    await spinner.start("Initializing audio drivers and speech runtime...")
    if profile_id is not None:
        result = await application.activate_profile(
            profile_id,
            ActivationSource.CLI,
        )
        if not result.accepted:
            raise RuntimeError(
                result.detail or f"Cannot activate profile {profile_id!r}"
            )
    elif application.state != ConversationState.ARMED:
        raise RuntimeError(
            "profile_id is required because wake-word activation is unavailable"
        )

    await spinner.stop("Parrot mode ready")

    print_welcome(
        application,
        "[bold green]Helomi Parrot is active and listening[/bold green]",
        profile_id,
    )

    print()
    print(
        "[italic]Speak into your microphone. "
        "Detected speech will be transcribed and repeated back.[/italic]"
    )

    print_exit("exit parrot mode")

    async def _monitor_events():
        async for event in application.subscribe_events():
            match event:
                case ProfileActivatedEvent(profile_id=pid):
                    print(
                        f" [cyan]●[/cyan] Profile activated: [magenta]{pid}[/magenta]"
                    )
                case ProfileDeactivatedEvent():
                    print(" [dim]○ Profile deactivated[/dim]")
                case TranscriptionReadyEvent(text=text):
                    print(f" [bold cyan]🎙 Heard:[/bold cyan] {text}")
                    print(f" [bold green]🦜 Echoing back:[/bold green] {text}")
                case DriverChangedEvent(driver_id=driver_id):
                    print(f" [blue]Audio route:[/blue] {driver_id}")
                case CallStartedEvent(caller=caller):
                    print(f" [green]Incoming call:[/green] {caller}")
                case CallEndedEvent():
                    print(" [dim]Call ended[/dim]")

    monitor_task = asyncio.create_task(_monitor_events())
    try:
        await shutdown.wait()
    finally:
        monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)

    print()
    await spinner.start("Stopping speech runtime...")
    await spinner.stop("Parrot stopped")
