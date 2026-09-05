import asyncio

from rich import print

from helomi_core import Runtime

from ..widgets import Spinner, print_exit, print_welcome


async def run_serve_cmd(
    runtime: Runtime,
    shutdown: asyncio.Event,
    spinner: Spinner,
):
    print()
    await spinner.start("Starting Helomi speech server...")
    server = await runtime.get_server_extension(True)
    await spinner.stop("Server ready")

    url = server.url

    print_welcome(
        runtime,
        f"[bold green]Helomi Server running at[/bold green] [blue]{url}[/blue]",
    )

    print()
    print(f"[italic cyan]API docs: [blue]{url}/docs[/blue][/italic cyan]")

    print_exit("stop the server")

    await shutdown.wait()

    print()
    await spinner.start("Stopping server...")
    await spinner.stop("Server stopped")
