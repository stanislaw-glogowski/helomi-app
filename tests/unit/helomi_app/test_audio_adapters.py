from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_runtime.audio.avfaudio.config import AVFAudioProfile, AVFAudioSettings
from helomi_runtime.audio.avfaudio.driver import AVFAudioDriver
from helomi_runtime.audio.domain import AudioFormat, RawAudio
from helomi_runtime.audio.messages import (
    DisconnectCommand,
    InterruptCommand,
    PlayCommand,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)


@pytest.fixture
def mock_avfaudio_driver():
    settings = AVFAudioSettings()
    profiles = {
        "alexa": AVFAudioProfile(room_voice=None),
    }
    driver = AVFAudioDriver(settings=settings, profiles=profiles)
    driver._ready_signal.set()
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.stdout = MagicMock()
    driver._proc = mock_proc
    return driver


@pytest.mark.asyncio
async def test_avfaudio_driver_play_and_interrupt(mock_avfaudio_driver):
    driver = mock_avfaudio_driver
    raw = RawAudio(format=AudioFormat.MONO_16, data=b"\x00" * 320)

    # Before any play, interrupt returns False
    assert await driver.execute_command(InterruptCommand()) is False

    # Play queues playback
    assert await driver.execute_command(PlayCommand(audio=raw)) is True
    assert driver._pending_playbacks == 1

    # Interrupt now returns True and resets pending playbacks
    assert await driver.execute_command(InterruptCommand()) is True
    assert driver._pending_playbacks == 0

    # Second interrupt returns False because pending_playbacks is 0
    assert await driver.execute_command(InterruptCommand()) is False


@pytest.mark.asyncio
async def test_avfaudio_driver_room_voice_commands(mock_avfaudio_driver):
    driver = mock_avfaudio_driver

    # Start room voice for profile with None path and not started -> returns False
    res = await driver.execute_command(StartRoomVoiceCommand(profile_id="alexa"))
    assert res is False

    # Stop room voice when not started -> returns False
    res = await driver.execute_command(StopRoomVoiceCommand())
    assert res is False

    # Disconnect when room voice not started -> returns True
    res = await driver.execute_command(DisconnectCommand())
    assert res is True
