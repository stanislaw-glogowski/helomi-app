import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from prompt_toolkit import PromptSession
from prompt_toolkit.buffer import Buffer

from helomi_cli.say.cmd import _input_loop, pipeline_loop
from helomi_core.config import Profile
from helomi_speech.domain import (
    ProfileActivated,
    ProfileDeactivated,
    TranscriptionReady,
)


@pytest.mark.asyncio
async def test_cli_say_input_loop_commands(tmp_path):
    """Verify input loop parses bracketed commands and exits cleanly."""
    mock_pipeline = MagicMock()
    mock_pipeline.active_profile = Profile(
        name="Default", id="default", root_path=tmp_path
    )
    mock_pipeline.deactivate_profile = AsyncMock()
    mock_pipeline.say_text = AsyncMock()

    mock_session = MagicMock(spec=PromptSession)
    # Simulate user inputs: "hello", "x", "exit"
    inputs = ["hello", "x", "exit"]

    async def mock_prompt_async(*args, **kwargs):
        if inputs:
            return inputs.pop(0)
        return "exit"

    mock_session.prompt_async = AsyncMock(side_effect=mock_prompt_async)
    shutdown = asyncio.Event()

    await _input_loop(mock_session, mock_pipeline, shutdown)

    # 1. "hello" called pipeline.say_text("hello")
    mock_pipeline.say_text.assert_called_with("hello")

    # 2. "x" called pipeline.deactivate_profile()
    mock_pipeline.deactivate_profile.assert_called_once()

    # 3. "exit" triggered shutdown event
    assert shutdown.is_set()


@pytest.mark.asyncio
async def test_cli_say_pipeline_loop_event_handling():
    """Verify pipeline loop receives events and updates UI buffers."""
    mock_pipeline = MagicMock()

    async def mock_subscribe():
        yield ProfileActivated(profile_id="default")
        yield TranscriptionReady(profile_id="default", text="transcribed speech")
        yield ProfileDeactivated(profile_id="default")

    mock_pipeline.subscribe = mock_subscribe

    mock_buffer = MagicMock(spec=Buffer)
    mock_buffer.text = ""
    mock_buffer.cursor_position = 0

    mock_app = MagicMock()
    mock_app.current_buffer = mock_buffer

    mock_session = MagicMock(spec=PromptSession)
    mock_session.app = mock_app

    await pipeline_loop(mock_session, mock_pipeline)

    # Verify that TranscriptionReady populated buffer text
    assert mock_buffer.text == "transcribed speech"
    assert mock_buffer.cursor_position == len("transcribed speech")
    assert mock_app.invalidate.called
