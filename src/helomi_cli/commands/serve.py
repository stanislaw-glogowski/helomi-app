import asyncio

from rich import print

from helomi_app import Application

from ..widgets import Spinner, print_exit, print_welcome


async def run_serve_cmd(
    application: Application,
    shutdown: asyncio.Event,
    spinner: Spinner,
):
    print()
    await spinner.start("Starting Helomi speech server...")
    server = application.server
    if server is None:
        raise RuntimeError("API server is not enabled")
    await spinner.stop("Server ready")

    url = server.url

    print_welcome(
        application,
        f"[bold green]Helomi Server running at[/bold green] [blue]{url}[/blue]",
    )

    print()
    print(f"[italic cyan]API docs: [blue]{url}/docs[/blue][/italic cyan]")

    print_exit("stop the server")

    await shutdown.wait()

    print()
    await spinner.start("Stopping server...")
    await spinner.stop("Server stopped")
