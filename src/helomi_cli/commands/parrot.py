import asyncio

from rich import print

from helomi_core import Runtime
from helomi_core.pipeline import (
    ActivateProfileCmd,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    TranscriptionReadyEvent,
)

from ..widgets import Spinner, print_exit, print_welcome


async def run_parrot_cmd(
    runtime: Runtime,
    shutdown: asyncio.Event,
    profile_id: str | None,
    spinner: Spinner,
):
    print()
    await spinner.start("Initializing audio drivers & speech pipeline...")
    await runtime.get_parrot_extension(True)
    pipeline = await runtime.get_pipeline_service()

    if profile_id:
        await pipeline.execute_command(ActivateProfileCmd(profile_id=profile_id))

    await spinner.stop("Parrot mode ready")

    print_welcome(
        runtime,
        "[bold green]Helomi Parrot is active and listening[/bold green]",
        profile_id,
    )

    print()
    print(
        "[italic]Speak into your microphone. "
        "Detected speech will be transcribed and repeated back.[/italic]"
    )

    print_exit("exit parrot mode")

    async def _monitor_events() -> None:
        async for event in pipeline.subscribe_event():
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

    monitor_task = asyncio.create_task(_monitor_events())
    try:
        await shutdown.wait()
    finally:
        monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)

    print()
    await spinner.start("Stopping speech pipeline...")
    await spinner.stop("Parrot stopped")
