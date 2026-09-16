from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    status,
)

from ....version import __version__
from .bridge import TwilioBridge


def create_app(bridge: TwilioBridge) -> FastAPI:
    app = FastAPI(
        title="Helomi Twilio Entrypoint",
        version=__version__,
        docs_url=None,
        openapi_url=None,
    )

    app.state.bridge = bridge

    app.add_api_route(
        "/",
        methods=["GET"],
        endpoint=lambda: {
            "title": app.title,
            "version": app.version,
        },
    )

    app.add_api_route(
        "/health",
        methods=["GET"],
        endpoint=lambda: {
            "status": "OK",
        },
    )

    app.add_api_route(
        "/",
        methods=["POST"],
        endpoint=handle_request,
    )

    app.add_api_websocket_route(
        "/{profile_id}/{call_sid}/{deadline}/{sig}",
        endpoint=handle_websocket,
    )

    return app


async def handle_request(request: Request) -> Response:
    bridge: TwilioBridge = request.app.state.bridge
    params = dict(await request.form())

    caller = params.get("From", None)
    callee = params.get("To", None)
    call_sid = params.get("CallSid", None)

    if params.get("CallStatus", None) != "ringing" or params.get("ErrorCode", None):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if (
        not isinstance(caller, str)
        or not isinstance(callee, str)
        or not isinstance(call_sid, str)
        or not caller
        or not callee
        or not call_sid
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request.",
        )

    if not bridge.is_request_valid(request, params):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature.",
        )

    if bridge.is_caller_allowed(caller):
        if (profile_id := bridge.get_profile_id(callee)) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Callee not found.",
            )

        url = bridge.get_websocket_url(profile_id, call_sid)

        response = f'<Connect><Stream url="{url}"/></Connect>'
    else:
        response = '<Reject reason="busy" />'

    return Response(
        media_type="application/xml",
        content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                {response}
            </Response>""",
    )


async def handle_websocket(
    websocket: WebSocket,
    profile_id: str | None = None,
    call_sid: str | None = None,
    deadline: str | None = None,
    sig: str | None = None,
) -> None:
    bridge: TwilioBridge = websocket.app.state.bridge
    if not profile_id or not call_sid or not deadline or not sig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request.",
        )
    if not bridge.is_signature_valid(profile_id, call_sid, deadline, sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature.",
        )

    await websocket.accept()
    await bridge.connect(profile_id, websocket)
