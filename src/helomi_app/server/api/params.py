from typing import Annotated

from fastapi import Depends, Header, Query, Request

from ...pipeline import PipelineExtension
from ..session import SessionManager


def get_pipeline(request: Request) -> PipelineExtension:
    return request.app.state.pipeline


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


ProfileId = Annotated[
    str,
    Query(description="ID of the profile to lock"),
]

SessionId = Annotated[
    str,
    Header(alias="x-session-id", description="Session ID returned by SSE"),
]

Pipeline = Annotated[PipelineExtension, Depends(get_pipeline)]

Sessions = Annotated[SessionManager, Depends(get_sessions)]
