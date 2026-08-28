import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..speech import ActivateProfile, SayText, SpeechCmd
from .session import ProfileLockedError, Session, SessionManager


def create_router(session_manager: SessionManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.api_route("/speech", methods=["GET", "QUERY"])
    async def get_speech_stream(
        request: Request,
        profile_id: Annotated[str, Query(description="ID of the profile to lock")],
    ) -> StreamingResponse:
        server_context = request.app.state.context

        if profile_id not in server_context.runtime.profiles:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{profile_id}' not found",
            )

        try:
            session = await session_manager.acquire(profile_id)
        except ProfileLockedError as err:
            raise HTTPException(
                status_code=409,
                detail=str(err),
            ) from err

        async def sse_event_generator(
            active_session: Session,
        ) -> AsyncIterator[str]:
            init_data = json.dumps(
                {
                    "session_id": active_session.id,
                    "profile_id": active_session.profile_id,
                }
            )
            yield f"event: session\ndata: {init_data}\n\n"

            try:
                while True:
                    event = await active_session.queue.get()
                    try:
                        if event is None:
                            break
                        dumped = event.model_dump_json()
                        yield f"event: {event.type}\ndata: {dumped}\n\n"
                    finally:
                        active_session.queue.task_done()
            finally:
                await session_manager.release(active_session.id)

        return StreamingResponse(
            sse_event_generator(session),
            media_type="text/event-stream",
            headers={
                "X-Session-ID": session.id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @router.post("/speech")
    async def post_speech_cmd(
        request: Request,
        cmd: SpeechCmd,
        x_session_id: Annotated[
            str,
            Header(alias="x-session-id", description="Session ID returned by SSE"),
        ],
    ) -> dict[str, bool | str]:
        session = session_manager.get(x_session_id)
        if session is None:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid or expired session '{x_session_id}'",
            )

        server_context = request.app.state.context

        final_cmd: SpeechCmd
        match cmd:
            case SayText(text=text, profile_id=pid, trace_id=trace_id):
                if pid is not None and pid != session.profile_id:
                    msg = (
                        f"Profile '{pid}' does not match "
                        f"session profile '{session.profile_id}'"
                    )
                    raise HTTPException(status_code=403, detail=msg)
                final_cmd = SayText(
                    text=text,
                    profile_id=session.profile_id,
                    trace_id=trace_id,
                )
            case ActivateProfile(profile_id=pid, trace_id=trace_id):
                if pid is not None and pid != session.profile_id:
                    msg = (
                        f"Profile '{pid}' does not match "
                        f"session profile '{session.profile_id}'"
                    )
                    raise HTTPException(status_code=403, detail=msg)
                final_cmd = ActivateProfile(
                    profile_id=session.profile_id,
                    trace_id=trace_id,
                )
            case _:
                final_cmd = cmd

        success = await server_context.publish_command(final_cmd)
        return {
            "status": "ok",
            "success": success,
        }

    return router
