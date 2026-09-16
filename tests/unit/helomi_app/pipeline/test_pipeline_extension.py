from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.pipeline import SayTextCmd
from helomi_app.pipeline.extension import PipelineExtension
from helomi_app.pipeline.service import PipelineService


class DummyExtension(PipelineExtension):
    pass


@pytest.mark.asyncio
async def test_pipeline_extension_properties_and_active_state() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.profiles = MagicMock()
    mock_pipeline.active_profile = MagicMock()
    mock_pipeline.active_extension = None

    ext = DummyExtension(mock_pipeline)
    assert not ext.is_active
    assert ext.profiles is mock_pipeline.profiles
    assert ext.active_profile is mock_pipeline.active_profile

    # Set as active extension
    mock_pipeline.active_extension = DummyExtension
    assert ext.is_active


@pytest.mark.asyncio
async def test_pipeline_extension_execute_command() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.execute_command = AsyncMock(return_value=True)

    ext = DummyExtension(mock_pipeline)
    cmd = SayTextCmd(text="hello")
    res = await ext.execute_command(cmd)

    assert res is True
    mock_pipeline.execute_command.assert_called_once_with(cmd, DummyExtension)


def test_pipeline_extension_subscribe_event() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.subscribe_event = MagicMock(return_value="mock_iterator")

    ext = DummyExtension(mock_pipeline)
    sub = ext._subscribe_event()

    assert sub == "mock_iterator"
    mock_pipeline.subscribe_event.assert_called_once_with(DummyExtension)


@pytest.mark.asyncio
async def test_server_extension_pipeline_loop_ignores_deactivated() -> None:
    from helomi_app.pipeline.domain import PipelineOptions
    from helomi_app.pipeline.messages import (
        ExtensionActivatedEvent,
        ExtensionDeactivatedEvent,
        OptionsSetEvent,
        ProfileActivatedEvent,
    )
    from helomi_app.pipeline.server.config import ServerSettings
    from helomi_app.pipeline.server.extension import ServerExtension
    from helomi_app.pipeline.server.session import SessionManager

    mock_pipeline = MagicMock(spec=PipelineService)
    mock_sessions = MagicMock(spec=SessionManager)
    settings = ServerSettings(host="127.0.0.1", port=4356)

    ext = ServerExtension(
        settings=settings,
        service=mock_pipeline,
        sessions=mock_sessions,
    )

    options = PipelineOptions(
        persistent_profile_enabled=True,
        persistent_profile_supported=True,
        reactions_enabled=True,
        reactions_supported=True,
        room_voice_enabled=True,
        room_voice_supported=True,
        wakeword_enabled=True,
        wakeword_supported=True,
    )

    async def mock_event_stream():
        yield OptionsSetEvent()
        yield ExtensionDeactivatedEvent(
            extension=DummyExtension,
            options=options,
        )
        yield ExtensionActivatedEvent(
            extension=DummyExtension,
            options=options,
            active_profile_id="p1",
        )

    ext._subscribe_event = mock_event_stream

    await ext._pipeline_loop()

    # Verify OptionsSetEvent and ExtensionDeactivatedEvent were filtered out
    # Only ExtensionActivatedEvent(active_profile_id="p1") produced a dispatched event
    assert mock_sessions.dispatch_event.call_count == 1
    call_args = mock_sessions.dispatch_event.call_args[0][0]
    assert isinstance(call_args, ProfileActivatedEvent)
    assert call_args.profile_id == "p1"
