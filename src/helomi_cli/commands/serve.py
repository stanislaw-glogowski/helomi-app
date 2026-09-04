import asyncio

from rich import print

from helomi_app import Runtime

from ..widgets import Spinner


async def run_serve_cmd(
    runtime: Runtime,
    shutdown: asyncio.Event,
    spinner: Spinner,
):
    print()
    await spinner.start("Starting Helomi speech server...")
    server = await runtime.get_server_extension()
    await spinner.stop("Server ready")

    print()
    print(
        "[bold green]Helomi Server running at[/bold green] "
        f"[bold cyan]{server.url}[/bold cyan]"
    )
    print()
    print("[italic cyan]Profiles available:[/italic cyan]")
    default_profile = runtime.profiles.get(None)
    for profile in runtime.profiles:
        is_default = profile is default_profile
        mark = "[green]*[/green]" if is_default else " "
        default_tag = " [dim](default)[/dim]" if is_default else ""
        print(
            f"  {mark} [magenta]{profile.name}[/magenta] "
            f"[dim]({profile.id})[/dim]{default_tag}"
        )

    print()
    print("[italic cyan]Available endpoints:[/italic cyan]")
    url = server.url
    print(f"  [cyan]GET [/cyan] [bold]{url}/api/v1/health[/bold]")
    print(f"  [cyan]GET [/cyan] [bold]{url}/api/v1/profile[/bold]")
    print(f"  [cyan]GET [/cyan] [bold]{url}/api/v1/profile/{{id}}[/bold]")
    print(f"  [cyan]GET [/cyan] [bold]{url}/api/v1/speech[/bold]")
    print(f"  [cyan]POST[/cyan] [bold]{url}/api/v1/speech[/bold]")
    print()
    print("[dim]Press [bold]Ctrl+C[/bold] to stop the server.[/dim]")
    print()

    await shutdown.wait()

    print()
    await spinner.start("Stopping server...")
    await spinner.stop("Server stopped")
