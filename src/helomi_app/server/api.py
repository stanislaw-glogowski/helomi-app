import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Request
from starlette.responses import StreamingResponse

from ..config import ResponseMode
from ..messages import (
    CommandResult,
    EndConversationCommand,
    SayReactionCommand,
    SayTextCommand,
)
from ..version import __version__
from .session import Session, SessionManager

if TYPE_CHECKING:
    from ..application import Application
else:
    Application = Any

type APICommand = SayTextCommand | SayReactionCommand | EndConversationCommand


def get_application(request: Request) -> Application:
    return request.app.state.application


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


ApplicationDep = Annotated[Application, Depends(get_application)]
SessionsDep = Annotated[SessionManager, Depends(get_sessions)]
SessionHeader = Annotated[str, Header(alias="x-session-id")]
CommandBody = Annotated[APICommand, Body(discriminator="type")]


def create_api(application: Application, sessions: SessionManager) -> FastAPI:
    api = FastAPI(
        title="Helomi API",
        version=__version__,
        description="Privacy-first voice assistant API.",
        redoc_url=None,
    )
    api.state.application = application
    api.state.sessions = sessions
    api.add_api_route(
        "/",
        methods=["GET"],
        endpoint=lambda: {
            "title": api.title,
            "version": api.version,
            "docs_url": api.docs_url,
        },
    )
    api.add_api_route(
        "/health",
        methods=["GET"],
        endpoint=lambda: {"status": "OK"},
    )
    api.include_router(create_router(), prefix="/api/v1")
    return api


def create_router() -> APIRouter:
    router = APIRouter()
    router.add_api_route("/profile", methods=["GET"], endpoint=get_profiles)
    router.add_api_route("/profile/{profile_id}", methods=["GET"], endpoint=get_profile)
    router.add_api_route(
        "/profile/{profile_id}/stream",
        methods=["GET"],
        endpoint=get_profile_stream,
    )
    router.add_api_route("/command", methods=["POST"], endpoint=post_command)
    return router


async def get_profiles(
    application: ApplicationDep,
    require_prompt: str | None = None,
) -> list[dict[str, Any]]:
    active_id = application.active_profile.id if application.active_profile else None
    return [
        item
        for profile in application.profiles
        if (
            item := profile.to_public_dict(
                require_prompt=require_prompt,
                active_id=active_id,
            )
        )
    ]


async def get_profile(
    profile_id: str,
    application: ApplicationDep,
    require_prompt: str | None = None,
) -> dict[str, Any]:
    profile = application.profiles.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    result = profile.to_public_dict(
        require_prompt=require_prompt,
        active_id=application.active_profile.id if application.active_profile else None,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


async def get_profile_stream(
    profile_id: str,
    application: ApplicationDep,
    sessions: SessionsDep,
) -> StreamingResponse:
    if application.profiles.get(profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    session = await sessions.acquire(profile_id)
    if session is None:
        raise HTTPException(status_code=409, detail="Profile already in use")

    async def generate(active_session: Session) -> AsyncIterator[str]:
        payload = json.dumps(
            {
                "session_id": active_session.id,
                "profile_id": active_session.profile_id,
            }
        )
        try:
            yield f"event: session_started\ndata: {payload}\n\n"
            async for event in active_session.subscribe():
                data = event.model_dump_json(exclude={"type"})
                yield f"event: {event.type}\ndata: {data}\n\n"
        finally:
            await sessions.release(active_session)

    return StreamingResponse(
        generate(session),
        media_type="text/event-stream",
        headers={
            "X-Session-ID": session.id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def post_command(
    command: CommandBody,
    application: ApplicationDep,
    sessions: SessionsDep,
    session_id: SessionHeader,
) -> CommandResult:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if application.response_mode != ResponseMode.API:
        raise HTTPException(status_code=409, detail="API response mode is inactive")

    match command:
        case SayTextCommand():
            final_command = command.model_copy(
                update={"profile_id": session.profile_id, "mode": ResponseMode.API}
            )
        case SayReactionCommand():
            final_command = command.model_copy(
                update={"profile_id": session.profile_id, "mode": ResponseMode.API}
            )
        case EndConversationCommand():
            final_command = command
    return await application.execute_command(final_command)
