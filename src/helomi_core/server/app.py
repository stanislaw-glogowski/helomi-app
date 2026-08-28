from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI

from ..speech import SpeechCmd
from .routes import create_router
from .session import SessionManager

if TYPE_CHECKING:
    from ..runtime import Runtime


@dataclass(slots=True)
class ServerContext:
    runtime: Runtime
    session_manager: SessionManager
    publish_command: Callable[[SpeechCmd], Awaitable[bool]]


def create_app(server_context: ServerContext) -> FastAPI:
    app = FastAPI(
        title="Helomi Local Speech API",
        version="0.5.0",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.context = server_context

    app.include_router(create_router(server_context.session_manager))

    @app.get("/api/v1/health")
    async def health_check() -> dict[str, str | int]:
        return {
            "status": "healthy",
            "active_sessions": server_context.session_manager.active_sessions_count,
        }

    return app
