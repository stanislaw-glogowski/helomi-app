import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_core.detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
)
from helomi_core.pipeline import (
    ActivateProfile,
    PipelineOptions,
    PipelineService,
)
from helomi_core.reaction import ReactionKind
from helomi_core.server import ServerExtension


@pytest.fixture
def mock_pipeline_dependencies():
    profiles = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = "alexa"
    mock_profile.audio = MagicMock()
    mock_profile.get_reaction.return_value = None
    profiles.get.return_value = mock_profile

    audio_driver = MagicMock()
    audio_driver.activate = AsyncMock()
    audio_driver.deactivate = AsyncMock()

    detection_worker = MagicMock(spec=DetectionWorker)
    detection_worker.change_mode = AsyncMock()

    stt_worker = MagicMock()
    tts_worker = MagicMock()

    return (
        profiles,
        audio_driver,
        detection_worker,
        stt_worker,
        tts_worker,
        mock_profile,
    )


def test_pipeline_options_defaults():
    """Verify default values of PipelineOptions."""
    options = PipelineOptions()
    assert options.room_voice is True
    assert options.wake_word is True


@pytest.mark.asyncio
async def test_pipeline_service_options_property_and_init(mock_pipeline_dependencies):
    """Verify options property and init options handling."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )

    custom_options = PipelineOptions(room_voice=False, wake_word=False)
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
        options=custom_options,
    )

    assert service.options is custom_options
    assert service.options.room_voice is False
    assert service.options.wake_word is False


@pytest.mark.asyncio
async def test_pipeline_service_set_option_validation(mock_pipeline_dependencies):
    """Verify set_option validates option keys and returns False on no-op."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )

    with pytest.raises(AttributeError, match="Unknown pipeline option: nonexistent"):
        await service.set_option("nonexistent", True)

    # Initial room_voice is True, setting True returns False (no change)
    res = await service.set_option("room_voice", True)
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_activation(mock_pipeline_dependencies):
    """Verify room_voice option controls audio_driver.activate."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )

    # 1. room_voice = True (default) -> driver.activate is called
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._active_extension = ServerExtension

    cmd = ActivateProfile(profile_id="alexa")
    await service._handle_activate_profile(cmd)
    audio_driver.activate.assert_called_once_with(mock_profile.audio)

    # 2. room_voice = False -> driver.activate is NOT called
    audio_driver.activate.reset_mock()
    await service.set_option("room_voice", False)
    service._active_profile = None  # reset active profile

    await service._handle_activate_profile(cmd)
    audio_driver.activate.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_toggle_live(mock_pipeline_dependencies):
    """Verify toggling room_voice immediately controls audio_driver."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._active_extension = ServerExtension
    service._active_profile = mock_profile

    # Toggle to False -> calls driver.deactivate
    res = await service.set_option("room_voice", False)
    assert res is True
    assert service.options.room_voice is False
    audio_driver.deactivate.assert_called_once()

    # Toggle to True -> calls driver.activate
    res = await service.set_option("room_voice", True)
    assert res is True
    assert service.options.room_voice is True
    audio_driver.activate.assert_called_once_with(mock_profile.audio)

    # Handle error in audio_driver.activate gracefully
    audio_driver.activate.side_effect = RuntimeError("Audio error")
    await service.set_option("room_voice", False)
    await service.set_option("room_voice", True)


@pytest.mark.asyncio
async def test_pipeline_service_wake_word_toggle_and_modes(mock_pipeline_dependencies):
    """Verify toggling wake_word updates detection worker modes."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._active_extension = ServerExtension

    # 1. Active profile is None, toggling wake_word to False then True -> PROFILE mode
    await service.set_option("wake_word", False)
    detection_worker.change_mode.reset_mock()
    res = await service.set_option("wake_word", True)
    assert res is True
    detection_worker.change_mode.assert_called_with(DetectionMode.PROFILE)

    # 2. Active profile is set, toggling wake_word to False -> UTTERANCE mode
    service._active_profile = mock_profile
    detection_worker.change_mode.reset_mock()
    await service.set_option("wake_word", False)
    assert service.options.wake_word is False
    detection_worker.change_mode.assert_called_once_with(DetectionMode.UTTERANCE)


@pytest.mark.asyncio
async def test_pipeline_service_detection_loop_wake_word_handling(
    mock_pipeline_dependencies,
):
    """Verify detection loop respects wake_word option."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._active_extension = ServerExtension
    service.execute_command = AsyncMock()

    # Case 1: wake_word is True
    # ProfileDetected triggers ActivateProfile
    service._detection_worker.detect = MagicMock()

    async def mock_detect_profile(_):
        yield ProfileDetected(profile_id="alexa")

    service._detection_worker.detect.side_effect = mock_detect_profile
    await service._detection_queue.put(MagicMock())

    # Run detection loop for 1 iteration
    raw = await service._detection_queue.get()
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ProfileDetected):
            if service._options.wake_word and service._active_extension is not None:
                await service.execute_command(
                    ActivateProfile(profile_id=res.profile_id),
                )
    service.execute_command.assert_called_once_with(
        ActivateProfile(profile_id="alexa"),
    )

    # Case 2: wake_word is False
    # ProfileDetected is ignored
    service.execute_command.reset_mock()
    await service.set_option("wake_word", False)

    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ProfileDetected):
            if service._options.wake_word and service._active_extension is not None:
                await service.execute_command(
                    ActivateProfile(profile_id=res.profile_id),
                )
    service.execute_command.assert_not_called()

    # Case 3: ConversationEnded when wake_word is False does NOT deactivate profile
    service._active_profile = mock_profile
    detection_worker.change_mode.reset_mock()

    async def mock_detect_ended(_):
        yield ConversationEnded()

    service._detection_worker.detect.side_effect = mock_detect_ended
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ConversationEnded):
            if service._options.wake_word and service._active_extension is not None:
                await service.execute_command(MagicMock())
            elif service._active_profile is not None:
                await service._detection_worker.change_mode(DetectionMode.UTTERANCE)

    service.execute_command.assert_not_called()
    detection_worker.change_mode.assert_called_once_with(DetectionMode.UTTERANCE)


@pytest.mark.asyncio
async def test_pipeline_service_tts_mode_extension_transition(
    mock_pipeline_dependencies,
):
    """Verify switching to/from TTS mode deactivates and restores room voice."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._active_profile = mock_profile
    service._active_extension = ServerExtension

    # 1. Transition to TTS mode (extension = None) deactivates room voice
    await service.set_active_extension(None)
    assert service.active_extension is None
    audio_driver.deactivate.assert_called_once()

    # 2. Transition back from TTS mode to ServerExtension restores room voice
    audio_driver.activate.reset_mock()
    await service.set_active_extension(ServerExtension)
    assert service.active_extension is ServerExtension
    audio_driver.activate.assert_called_once_with(mock_profile.audio)

    # 3. Same extension returns False
    assert await service.set_active_extension(ServerExtension) is False

    # 4. Error during restore is handled gracefully
    await service.set_active_extension(None)
    audio_driver.activate.side_effect = RuntimeError("Failed audio")
    await service.set_active_extension(ServerExtension)

    # 5. Restore with no active profile and wake_word=True sets PROFILE mode
    service._active_profile = None
    await service.set_active_extension(None)
    detection_worker.change_mode.reset_mock()
    await service.set_active_extension(ServerExtension)
    detection_worker.change_mode.assert_called_once_with(DetectionMode.PROFILE)

    # 6. Restore with no active profile and wake_word=False sets UTTERANCE mode
    await service.set_option("wake_word", False)
    await service.set_active_extension(None)
    detection_worker.change_mode.reset_mock()
    await service.set_active_extension(ServerExtension)
    detection_worker.change_mode.assert_called_once_with(DetectionMode.UTTERANCE)


@pytest.mark.asyncio
async def test_pipeline_service_greeting_reaction_respects_wake_word(
    mock_pipeline_dependencies,
):
    """Verify greeting reaction is only queued if wake_word option is True."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    mock_profile.get_reaction.side_effect = lambda kind: (
        "Tak?" if kind == ReactionKind.GREETING else None
    )

    # 1. wake_word = True -> greeting is queued
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    await service._handle_activate_profile(ActivateProfile(profile_id="alexa"))
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Tak?"

    # 2. wake_word = False -> greeting is NOT queued
    service._active_profile = None
    await service.set_option("wake_word", False)
    await service._handle_activate_profile(ActivateProfile(profile_id="alexa"))
    assert service._tts_queue.empty()


@pytest.mark.asyncio
async def test_pipeline_service_tts_mode_skips_detection(
    mock_pipeline_dependencies,
):
    """Verify detection loop skips detect and does not set UTTERANCE in TTS mode."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service._extensions = {ServerExtension: MagicMock()}
    service._active_extension = None
    assert service._is_active_or_no_extensions is False

    # 1. Activate profile in TTS mode does not switch detection worker to UTTERANCE
    detection_worker.change_mode.reset_mock()
    await service._handle_activate_profile(ActivateProfile(profile_id="alexa"))
    detection_worker.change_mode.assert_not_called()

    # 2. In TTS mode, detection loop consumes audio but does not call detect()
    detection_worker.detect.reset_mock()
    task = asyncio.create_task(service._detection_loop())
    await service._detection_queue.put(MagicMock())
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    detection_worker.detect.assert_not_called()
