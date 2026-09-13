from fastapi import FastAPI

from ...pipeline import PipelineExtension
from ...version import __version__
from ..session import SessionManager
from .routes import create_router


def create_api(
    pipeline: PipelineExtension,
    sessions: SessionManager,
) -> FastAPI:
    app = FastAPI(
        title="Helomi API",
        version=__version__,
        description=(
            "Privacy-first voice assistant API for audio orchestration, "
            "profile management, pipeline command execution, "
            "and real-time event streaming."
        ),
        openapi_tags=[
            {
                "name": "General",
                "description": "General service information and root metadata.",
            },
            {
                "name": "Health",
                "description": "Service health check and status endpoints.",
            },
            {
                "name": "Profiles",
                "description": (
                    "Voice assistant profile configuration "
                    "and real-time event streaming."
                ),
            },
            {
                "name": "Commands",
                "description": (
                    "Pipeline execution commands for speech and profile control."
                ),
            },
        ],
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.pipeline = pipeline
    app.state.sessions = sessions

    app.add_api_route(
        "/",
        methods=["GET"],
        endpoint=lambda: {
            "title": app.title,
            "version": app.version,
            "description": app.description,
            "docs_url": app.docs_url,
        },
        summary="API Root",
        description="Return basic API status and title information.",
        response_description="Basic API information",
        tags=["General"],
        responses={
            200: {
                "description": "API title and status information",
                "content": {
                    "application/json": {
                        "example": {"title": "Helomi API"},
                    },
                },
            },
        },
    )

    app.include_router(
        prefix="/api/v1",
        router=create_router(),
    )

    return app
