from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_core.pipeline.domain import SayText
from helomi_core.pipeline.extension import PipelineExtension
from helomi_core.pipeline.service import PipelineService


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
    cmd = SayText(text="hello")
    res = await ext.execute_command(cmd)

    assert res is True
    mock_pipeline.execute_command.assert_called_once_with(cmd, ext)


def test_pipeline_extension_subscribe_event() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.subscribe_event = MagicMock(return_value="mock_iterator")

    ext = DummyExtension(mock_pipeline)
    sub = ext._subscribe_event()

    assert sub == "mock_iterator"
    mock_pipeline.subscribe_event.assert_called_once_with(ext)
