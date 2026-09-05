from typing import Any

from fastapi import FastAPI

from ...pipeline import PipelineExtension
from ..session import SessionManager
from .router import create_router


def create_api(
    pipeline: PipelineExtension,
    sessions: SessionManager,
) -> FastAPI:
    app = FastAPI(
        title="Helomi API",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.pipeline = pipeline
    app.state.sessions = sessions

    @app.get("/")
    async def get_index() -> dict[str, Any]:
        return {
            "title": app.title,
        }

    app.include_router(
        prefix="/api/v1",
        router=create_router(),
    )

    return app
