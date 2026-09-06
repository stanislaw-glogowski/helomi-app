import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ...pipeline import (
    ActivateProfile,
    PipelineCmd,
    SayText,
)
from ..session import Session
from .params import Pipeline, SessionId, Sessions


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def get_health() -> dict[str, Any]:
        return {
            "status": "OK",
        }

    @router.get("/profile")
    async def get_profiles(
        pipeline: Pipeline,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": profile.id,
                "name": profile.name,
                "is_active": profile is pipeline.active_profile,
            }
            for profile in pipeline.profiles
        ]

    @router.get("/profile/{profile_id}")
    async def get_profile(
        profile_id: str,
        pipeline: Pipeline,
    ) -> dict[str, Any]:
        profile = pipeline.profiles.get(profile_id, throw_on_not_found=False)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        return {
            "id": profile.id,
            "name": profile.name,
            "is_active": profile is pipeline.active_profile,
        }

    @router.get("/profile/{profile_id}/stream")
    async def create_profile_stream(
        profile_id: str,
        pipeline: Pipeline,
        sessions: Sessions,
    ) -> StreamingResponse:
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
            yield f"event: session\ndata: {data}\n\n"

            try:
                async for event in _session.subscribe_event():
                    data = event.model_dump_json()
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

    @router.post("/command")
    async def post_command(
        cmd: PipelineCmd,
        session_id: SessionId,
        sessions: Sessions,
        pipeline: Pipeline,
    ) -> dict[str, bool | str]:
        session = sessions.get(session_id)

        if session is None:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid or expired session {session_id}",
            )

        match cmd:
            case SayText() | ActivateProfile():
                profile_id = cmd.profile_id
            case _:
                profile_id = None

        if profile_id is not None and session.profile_id != profile_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Profile {profile_id} does not match "
                    f"session profile '{session.profile_id}'"
                ),
            )

        final_cmd: PipelineCmd
        match cmd:
            case SayText():
                final_cmd = SayText(
                    text=cmd.text,
                    profile_id=session.profile_id,
                    trace_id=cmd.trace_id,
                )
            case ActivateProfile():
                final_cmd = ActivateProfile(
                    profile_id=session.profile_id,
                    trace_id=cmd.trace_id,
                )
            case cmd:
                final_cmd = cmd

        success = await pipeline.execute_command(final_cmd)

        return {
            "success": success,
        }

    return router
