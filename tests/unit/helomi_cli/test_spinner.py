import asyncio
from unittest.mock import patch

import pytest

from helomi_cli.widgets.spinner import Spinner


@pytest.mark.asyncio
async def test_spinner_disabled():
    """Verify Spinner does nothing when disabled flag is True."""
    spinner = Spinner(disabled=True)
    await spinner.start("Testing...")
    assert spinner._task is None
    await spinner.stop("Done")


@pytest.mark.asyncio
async def test_spinner_lifecycle():
    """Verify Spinner start, spin, and stop lifecycle writes to stdout."""
    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush"):
        spinner = Spinner(disabled=False)
        await spinner.start("Loading models...")
        assert spinner._task is not None

        # Give task brief time to iterate frames
        await asyncio.sleep(0.1)

        await spinner.stop("Models loaded")
        assert spinner._task is None
        assert mock_write.called
