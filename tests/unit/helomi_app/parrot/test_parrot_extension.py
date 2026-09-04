import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.parrot.extension import ParrotExtension
from helomi_app.pipeline.domain import SayText, TranscriptionReady
from helomi_app.pipeline.service import PipelineService


@pytest.mark.asyncio
async def test_parrot_extension_echoes_transcription() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.execute = AsyncMock(return_value=True)

    async def fake_subscribe(_=None):
        yield TranscriptionReady(profile_id="p1", text="echo this")

    mock_pipeline.subscribe = fake_subscribe

    parrot = ParrotExtension(mock_pipeline, is_enabled=True)
    async with parrot:
        await asyncio.sleep(0.05)

    mock_pipeline.execute.assert_called_once()
    called_cmd = mock_pipeline.execute.call_args[0][0]
    assert isinstance(called_cmd, SayText)
    assert called_cmd.text == "echo this"
