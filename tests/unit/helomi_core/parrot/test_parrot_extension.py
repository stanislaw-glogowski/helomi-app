import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_core.parrot.extension import ParrotExtension
from helomi_core.pipeline.domain import SayText, TranscriptionReady
from helomi_core.pipeline.service import PipelineService


@pytest.mark.asyncio
async def test_parrot_extension_echoes_transcription() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.execute_command = AsyncMock(return_value=True)

    async def fake_subscribe(_=None):
        yield TranscriptionReady(profile_id="p1", text="echo this")

    mock_pipeline.subscribe_event = fake_subscribe

    parrot = ParrotExtension(mock_pipeline)
    async with parrot:
        await asyncio.sleep(0.05)

    mock_pipeline.execute_command.assert_called_once()
    called_cmd = mock_pipeline.execute_command.call_args[0][0]
    assert isinstance(called_cmd, SayText)
    assert called_cmd.text == "echo this"
