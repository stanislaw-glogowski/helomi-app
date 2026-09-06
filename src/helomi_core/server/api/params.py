from typing import Annotated

from fastapi import Depends, Header, Request

from ...pipeline import PipelineExtension
from ..session import SessionManager


def get_pipeline(request: Request) -> PipelineExtension:
    return request.app.state.pipeline


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


SessionId = Annotated[
    str,
    Header(alias="x-session-id", description="Session ID returned by profile SSE"),
]

Pipeline = Annotated[PipelineExtension, Depends(get_pipeline)]

Sessions = Annotated[SessionManager, Depends(get_sessions)]
