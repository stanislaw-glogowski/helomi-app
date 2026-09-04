from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.pipeline.domain import SayText
from helomi_app.pipeline.extension import PipelineExtension
from helomi_app.pipeline.service import PipelineService


@pytest.mark.asyncio
async def test_pipeline_extension_enable_disable() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.execute = AsyncMock(return_value=True)
    mock_pipeline.profiles = MagicMock()
    mock_pipeline.active_profile = MagicMock()

    ext = PipelineExtension(mock_pipeline, is_enabled=False)
    assert not ext.is_enabled
    assert ext.profiles is mock_pipeline.profiles
    assert ext.active_profile is mock_pipeline.active_profile

    # When disabled, execute returns False
    cmd = SayText(text="hello")
    res = await ext.execute(cmd)
    assert res is False
    mock_pipeline.execute.assert_not_called()

    # Enable
    ext.enable()
    assert ext.is_enabled

    res = await ext.execute(cmd)
    assert res is True
    mock_pipeline.execute.assert_called_once_with(cmd)

    # Disable again
    ext.disable()
    assert not ext.is_enabled


def test_pipeline_extension_subscribe() -> None:
    mock_pipeline = MagicMock(spec=PipelineService)
    mock_pipeline.subscribe = MagicMock(return_value="mock_iterator")

    ext = PipelineExtension(mock_pipeline, is_enabled=True)
    sub = ext._subscribe()
    assert sub == "mock_iterator"
    mock_pipeline.subscribe.assert_called_once_with(ext._is_enabled)
