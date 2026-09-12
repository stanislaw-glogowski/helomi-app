from typing import Annotated

from fastapi import Body, Depends, Header, Path, Query, Request

from ...pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    PipelineExtension,
    SayReactionCmd,
    SayTextCmd,
)
from ..session import SessionManager


def get_pipeline(request: Request) -> PipelineExtension:
    return request.app.state.pipeline


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


SessionHeader = Annotated[
    str,
    Header(
        alias="x-session-id",
        description=(
            "Active session identifier returned in the X-Session-ID "
            "response header of the profile SSE stream."
        ),
    ),
]


RequirePromptParam = Annotated[
    str | None,
    Query(
        description="Optional prompt identifier to require or filter profiles by.",
    ),
]

ProfileIdPath = Annotated[
    str,
    Path(
        description="Unique identifier of the assistant profile.",
    ),
]

CommandBody = Annotated[
    ActivateProfileCmd | DeactivateProfileCmd | SayTextCmd | SayReactionCmd,
    Body(
        description=(
            "Pipeline command to execute "
            "(activate profile, deactivate profile, say text, or say reaction)."
        ),
    ),
]

PipelineDep = Annotated[PipelineExtension, Depends(get_pipeline)]

SessionsDep = Annotated[SessionManager, Depends(get_sessions)]
