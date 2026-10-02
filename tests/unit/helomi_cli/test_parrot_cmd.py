import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app import (
    ActivationSource,
    CallEndedEvent,
    CallStartedEvent,
    CommandRejectionCode,
    CommandResult,
    ConversationState,
    DriverChangedEvent,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    TranscriptionReadyEvent,
)
from helomi_cli.commands.parrot import run_parrot_cmd
from helomi_cli.widgets import Spinner


def _application(events=()):
    application = MagicMock()
    application.state = ConversationState.ARMED
    application.activate_profile = AsyncMock(return_value=CommandResult.ok())

    async def subscribe():
        for event in events:
            yield event

    application.subscribe_events = subscribe
    return application


@pytest.mark.asyncio
async def test_run_parrot_activates_profile_and_monitors_events():
    events = (
        ProfileActivatedEvent(profile_id="alexa", source=ActivationSource.CLI),
        TranscriptionReadyEvent(profile_id="alexa", text="Hello"),
        DriverChangedEvent(driver_id="avfaudio"),
        CallStartedEvent(profile_id="alexa", caller="***1234", monitoring=True),
        CallEndedEvent(profile_id="alexa"),
        ProfileDeactivatedEvent(profile_id="alexa"),
    )
    application = _application(events)
    shutdown = asyncio.Event()

    async def stop():
        await asyncio.sleep(0.01)
        shutdown.set()

    stop_task = asyncio.create_task(stop())
    await run_parrot_cmd(
        application,
        shutdown,
        "alexa",
        Spinner(disabled=True),
    )
    await stop_task

    application.activate_profile.assert_awaited_once_with("alexa", ActivationSource.CLI)


@pytest.mark.asyncio
async def test_run_parrot_without_profile_requires_armed_state():
    application = _application()
    shutdown = asyncio.Event()
    shutdown.set()
    await run_parrot_cmd(application, shutdown, None, Spinner(disabled=True))
    application.activate_profile.assert_not_awaited()

    application.state = ConversationState.IDLE
    with pytest.raises(RuntimeError, match="profile_id is required"):
        await run_parrot_cmd(application, shutdown, None, Spinner(disabled=True))


@pytest.mark.asyncio
async def test_run_parrot_reports_profile_rejection():
    application = _application()
    application.activate_profile.return_value = CommandResult.reject(
        CommandRejectionCode.PROFILE_NOT_FOUND, "Unknown profile"
    )
    with pytest.raises(RuntimeError, match="Unknown profile"):
        await run_parrot_cmd(
            application,
            asyncio.Event(),
            "missing",
            Spinner(disabled=True),
        )
