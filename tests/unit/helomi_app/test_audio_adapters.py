from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from helomi_app.core.audio.avfaudio.config import AVFAudioProfile, AVFAudioSettings
from helomi_app.core.audio.avfaudio.driver import AVFAudioDriver
from helomi_app.core.audio.domain import AudioFormat, RawAudio
from helomi_app.core.audio.messages import (
    DisconnectCmd,
    InterruptCmd,
    PlayCmd,
    StartRoomVoiceCmd,
    StopRoomVoiceCmd,
)
from helomi_app.core.audio.twilio.bridge import TwilioBridge, TwilioConnection
from helomi_app.core.audio.twilio.config import TwilioProfile, TwilioSettings


@pytest.fixture
def mock_avfaudio_driver():
    settings = AVFAudioSettings()
    profiles = {
        "alexa": AVFAudioProfile(room_voice_path=None),
    }
    driver = AVFAudioDriver(settings=settings, profiles=profiles)
    driver._ready_signal.set()
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    driver._proc = mock_proc
    return driver


@pytest.mark.asyncio
async def test_avfaudio_driver_play_and_interrupt(mock_avfaudio_driver):
    driver = mock_avfaudio_driver
    raw = RawAudio(format=AudioFormat.MONO_16, data=b"\x00" * 320)

    # Before any play, interrupt returns False
    assert await driver.execute_command(InterruptCmd()) is False

    # Play queues playback
    assert await driver.execute_command(PlayCmd(audio=raw)) is True
    assert driver._pending_playbacks == 1

    # Interrupt now returns True and resets pending playbacks
    assert await driver.execute_command(InterruptCmd()) is True
    assert driver._pending_playbacks == 0

    # Second interrupt returns False because pending_playbacks is 0
    assert await driver.execute_command(InterruptCmd()) is False


@pytest.mark.asyncio
async def test_avfaudio_driver_room_voice_commands(mock_avfaudio_driver):
    driver = mock_avfaudio_driver

    # Start room voice for profile with None path and not started -> returns False
    res = await driver.execute_command(StartRoomVoiceCmd(profile_id="alexa"))
    assert res is False

    # Stop room voice when not started -> returns False
    res = await driver.execute_command(StopRoomVoiceCmd())
    assert res is False

    # Disconnect when room voice not started -> returns True
    res = await driver.execute_command(DisconnectCmd())
    assert res is True


@pytest.fixture
async def mock_twilio_bridge():
    settings = TwilioSettings(
        auth_token="token",
        public_url="http://localhost:8000/twilio/",
    )
    profiles = {
        "alexa": TwilioProfile(callee="+1234567890"),
    }
    events = []
    bridge = TwilioBridge(
        settings=settings,
        profiles=profiles,
        dispatch_event=lambda evt: events.append(evt),
    )
    return bridge


@pytest.mark.asyncio
async def test_twilio_bridge_commands_no_connection(mock_twilio_bridge):
    bridge = mock_twilio_bridge
    raw = RawAudio(format=AudioFormat.MONO_16, data=b"\x00" * 320)

    # Without connection, commands return False
    assert await bridge.execute_command(PlayCmd(audio=raw)) is False
    assert await bridge.execute_command(InterruptCmd()) is False
    assert await bridge.execute_command(DisconnectCmd()) is False


@pytest.mark.asyncio
async def test_twilio_bridge_play_and_interrupt(mock_twilio_bridge):
    bridge = mock_twilio_bridge
    raw = RawAudio(format=AudioFormat.MONO_16, data=b"\x00" * 8000)

    mock_ws = AsyncMock(spec=WebSocket)
    connection = TwilioConnection(mock_ws)
    connection.set_sid("stream_sid_123")
    bridge._connection = connection

    # Play queues media requests
    assert await bridge.execute_command(PlayCmd(audio=raw)) is True
    assert not bridge._media_requests.empty()

    # Interrupt bumps epoch and sends ClearCmd
    initial_epoch = bridge._media_epoch
    assert await bridge.execute_command(InterruptCmd()) is True
    assert bridge._media_epoch > initial_epoch
    mock_ws.send_text.assert_called()

    # Verify ClearCmd was sent
    sent_text = mock_ws.send_text.call_args[0][0]
    assert '"event":"clear"' in sent_text

    # Disconnect closes connection
    assert await bridge.execute_command(DisconnectCmd()) is True
    mock_ws.close.assert_called_once()
