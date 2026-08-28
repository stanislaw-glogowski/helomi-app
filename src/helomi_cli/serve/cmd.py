import asyncio

from rich import print

from helomi_core import Runtime
from helomi_core.resources import LocalCatalog

from ..widgets import Spinner


async def run_serve_cmd(
    local_catalog: LocalCatalog,
    spinner: Spinner,
    shutdown: asyncio.Event,
) -> None:
    runtime = Runtime(local_catalog)
    server = runtime.get_server()

    await spinner.start(
        f"Initializing speech pipeline & server on http://{server.host}:{server.port}..."
    )

    async with server:
        await spinner.stop()
        print(
            "[bold green]FastAPI speech server running at "
            f"http://{server.host}:{server.port}[/bold green]"
        )
        print("[dim]Available endpoints:[/dim]")
        print("  [cyan]GET  /api/v1/speech?profile_id=<id>[/cyan]  (SSE stream)")
        print("  [cyan]POST /api/v1/speech[/cyan]                 (Command execution)")
        print("  [cyan]GET  /api/v1/health[/cyan]                 (Health check)")

        await shutdown.wait()

        await spinner.start("Closing server & speech pipeline...")

    await spinner.stop()
