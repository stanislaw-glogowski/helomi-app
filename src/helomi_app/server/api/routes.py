import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ..session import Session
from .params import (
    CommandBody,
    PipelineDep,
    ProfileIdPath,
    RequirePromptParam,
    SessionHeader,
    SessionsDep,
)


def create_router() -> APIRouter:
    router = APIRouter()

    router.add_api_route(
        "/health",
        methods=["GET"],
        endpoint=get_check,
        summary="Health check",
        description="Check if the Helomi API service is running and healthy.",
        response_description="Service health status",
        tags=["Health"],
        responses={
            200: {
                "description": "Service is healthy and operational",
                "content": {
                    "application/json": {
                        "example": {"status": "OK"},
                    },
                },
            },
        },
    )

    router.add_api_route(
        "/profile",
        methods=["GET"],
        endpoint=get_profiles,
        summary="List profiles",
        description=(
            "Retrieve all configured assistant profiles, "
            "with optional filtering by prompt identifier."
        ),
        response_description="List of assistant profile objects",
        tags=["Profiles"],
        responses={
            200: {
                "description": "Successfully retrieved list of profiles",
            },
        },
    )

    router.add_api_route(
        "/profile/{profile_id}",
        methods=["GET"],
        endpoint=get_profile,
        summary="Get profile",
        description=(
            "Retrieve configuration and runtime details "
            "for a specific assistant profile by its ID."
        ),
        response_description="Assistant profile details",
        tags=["Profiles"],
        responses={
            200: {
                "description": "Profile details retrieved successfully",
            },
            404: {
                "description": (
                    "Profile not found or required prompt not found in profile"
                ),
            },
        },
    )

    router.add_api_route(
        "/profile/{profile_id}/stream",
        methods=["GET"],
        endpoint=get_profile_stream,
        summary="Stream profile events",
        description=(
            "Establish a Server-Sent Events (SSE) stream for real-time pipeline events "
            "(such as speech recognition, VAD state, wake-word detection, and TTS) "
            "for the given profile. Acquires an exclusive session lock for the profile."
        ),
        response_description="Real-time Server-Sent Events (SSE) stream",
        tags=["Profiles"],
        responses={
            200: {
                "description": (
                    "SSE connection established. Also returns the active session ID "
                    "in the X-Session-ID header."
                ),
                "content": {"text/event-stream": {}},
            },
            404: {
                "description": "Profile not found",
            },
            409: {
                "description": "Profile already in use by an active session",
            },
        },
    )

    router.add_api_route(
        "/command",
        methods=["POST"],
        endpoint=post_command,
        summary="Execute pipeline command",
        description=(
            "Execute a pipeline command within an active session. "
            "Commands include activating or deactivating a profile, "
            "synthesizing text to speech, or playing a reaction."
        ),
        response_description="Command execution outcome status",
        tags=["Commands"],
        responses={
            200: {
                "description": "Command executed successfully",
                "content": {
                    "application/json": {
                        "example": {"success": True},
                    },
                },
            },
            401: {
                "description": "Invalid, missing, or expired session ID",
            },
            403: {
                "description": (
                    "Target profile ID does not match the active session profile"
                ),
            },
        },
    )

    return router


async def get_check() -> dict[str, Any]:
    """Return the health status of the API server."""
    return {
        "status": "OK",
    }


async def get_profiles(
    pipeline: PipelineDep,
    require_prompt: RequirePromptParam = None,
) -> list[dict[str, Any]]:
    """List all assistant profiles."""
    active_id = (
        active_profile.id
        if (active_profile := pipeline.active_profile) is not None
        else None
    )
    default_id = pipeline.profiles.get(None).id

    return [
        item
        for profile in pipeline.profiles
        if (
            item := profile.dump(
                require_prompt=require_prompt,
                active_id=active_id,
                default_id=default_id,
            )
        )
    ]


async def get_profile(
    pipeline: PipelineDep,
    profile_id: ProfileIdPath,
    require_prompt: RequirePromptParam = None,
) -> dict[str, Any]:
    """Get profile details by profile ID."""
    profile = pipeline.profiles.get(profile_id, throw_on_not_found=False)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    active_id = (
        active_profile.id
        if (active_profile := pipeline.active_profile) is not None
        else None
    )
    default_id = pipeline.profiles.get(None).id

    if not (
        res := profile.dump(
            require_prompt=require_prompt,
            active_id=active_id,
            default_id=default_id,
        )
    ):
        raise HTTPException(status_code=404, detail="Prompt not found")

    return res


async def get_profile_stream(
    profile_id: ProfileIdPath,
    pipeline: PipelineDep,
    sessions: SessionsDep,
) -> StreamingResponse:
    """Stream real-time pipeline events for a profile via Server-Sent Events."""
    profile = pipeline.profiles.get(profile_id, throw_on_not_found=False)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    session = await sessions.acquire(
        profile_id=profile_id,
    )

    if session is None:
        raise HTTPException(status_code=409, detail="Profile already in use")

    async def sse_event_generator(_session: Session) -> AsyncIterator[str]:
        data = json.dumps(
            {
                "session_id": _session.id,
                "profile_id": _session.profile_id,
            }
        )
        yield f"event: session_started\ndata: {data}\n\n"

        try:
            async for event in _session.subscribe_event():
                data = event.model_dump_json(exclude={"type"})
                yield f"event: {event.type}\ndata: {data}\n\n"
        finally:
            await sessions.release(_session)

    return StreamingResponse(
        sse_event_generator(session),
        media_type="text/event-stream",
        headers={
            "X-Session-ID": session.id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def post_command(
    pipeline: PipelineDep,
    sessions: SessionsDep,
    session_id: SessionHeader,
    cmd: CommandBody,
) -> dict[str, bool | str]:
    """Execute a control command on the audio pipeline."""
    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired session {session_id}",
        )

    profile_id = getattr(cmd, "profile_id", None)

    if profile_id is not None and session.profile_id != profile_id:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Profile {profile_id} does not match "
                f"session profile '{session.profile_id}'"
            ),
        )

    if hasattr(cmd, "profile_id"):
        final_cmd = cmd.model_copy(
            deep=True,
            update={
                "profile_id": session.profile_id,
            },
        )
    else:
        final_cmd = cmd

    success = await pipeline.execute_command(final_cmd)

    return {
        "success": success,
    }
