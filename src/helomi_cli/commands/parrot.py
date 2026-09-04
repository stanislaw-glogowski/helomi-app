import asyncio

from rich import print

from helomi_app import Runtime
from helomi_app.pipeline import ProfileActivated, ProfileDeactivated, TranscriptionReady

from ..widgets import Spinner


async def run_parrot_cmd(
    runtime: Runtime,
    shutdown: asyncio.Event,
    profile_id: str | None,
    spinner: Spinner,
):
    print()
    await spinner.start("Initializing audio drivers & speech pipeline...")
    await runtime.get_parrot_extension()
    pipeline = await runtime.get_pipeline_service()

    if profile_id:
        await pipeline.activate_profile(profile_id)

    await spinner.stop("Parrot mode ready")

    target_profile = runtime.profiles.get(profile_id)
    print()
    print("[bold green]Helomi Parrot is active and listening[/bold green]")
    print()
    print(
        f"[cyan]Active profile:[/cyan]   "
        f"[bold magenta]{target_profile.name}[/bold magenta] "
        f"[dim]({target_profile.id})[/dim]"
    )
    print(f"[cyan]Wakeword adapter:[/cyan] {target_profile.wakeword.adapter}")
    print(f"[cyan]STT adapter:[/cyan]      {target_profile.stt.adapter}")
    print(f"[cyan]TTS adapter:[/cyan]      {target_profile.tts.adapter}")
    print()
    print(
        "[italic]Speak into your microphone. "
        "Detected speech will be transcribed and repeated back.[/italic]"
    )
    print("[dim]Press [bold]Ctrl+C[/bold] to exit parrot mode.[/dim]")
    print()

    async def _monitor_events() -> None:
        async for event in pipeline.subscribe():
            match event:
                case ProfileActivated(profile_id=pid):
                    print(
                        f" [cyan]●[/cyan] Profile activated: [magenta]{pid}[/magenta]"
                    )
                case ProfileDeactivated():
                    print(" [dim]○ Profile deactivated[/dim]")
                case TranscriptionReady(text=text):
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
