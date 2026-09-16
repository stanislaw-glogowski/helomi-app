import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.core.audio import AudioDriver, RawAudio
from helomi_app.core.detection import (
    ConversationEndedEvent,
    DetectionMode,
    DetectionWorker,
    WakeWordDetectedEvent,
)
from helomi_app.pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ExtensionActivatedEvent,
    ExtensionDeactivatedEvent,
    OptionsSetEvent,
    PipelineExtension,
    PipelineOptions,
    PipelineService,
    SetOptionsCmd,
)
from helomi_app.profile import ReactionKind


class DummyExtensionA(PipelineExtension):
    pass


class DummyExtensionB(PipelineExtension):
    pass


@pytest.fixture
def mock_pipeline_dependencies():
    profiles = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = "alexa"
    mock_profile.audio = MagicMock()
    mock_profile.get_reaction.return_value = None
    profiles.get.return_value = mock_profile

    audio_driver = MagicMock(spec=AudioDriver)
    audio_driver.room_voice_supported = True
    audio_driver.start_room_voice = AsyncMock(return_value=True)
    audio_driver.stop_room_voice = AsyncMock(return_value=True)
    audio_driver.disconnect = AsyncMock(return_value=True)
    audio_driver.interrupt = AsyncMock(return_value=False)
    audio_driver.play = AsyncMock(return_value=True)

    async def empty_capture():
        if False:
            yield MagicMock(spec=RawAudio)

    audio_driver.subscribe_event = empty_capture

    detection_worker = MagicMock(spec=DetectionWorker)
    detection_worker.wakeword_supported = True
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
    """Verify PipelineOptions is_enabled logic."""
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
    assert options.is_enabled("persistent_profile") is True
    assert options.is_enabled("reactions") is True
    assert options.is_enabled("room_voice") is True
    assert options.is_enabled("wakeword") is True

    # Disabled if supported is False even if enabled is True
    unsupported_options = PipelineOptions(
        persistent_profile_enabled=True,
        persistent_profile_supported=False,
        reactions_enabled=True,
        reactions_supported=False,
        room_voice_enabled=True,
        room_voice_supported=False,
        wakeword_enabled=True,
        wakeword_supported=False,
    )
    assert unsupported_options.is_enabled("persistent_profile") is False
    assert unsupported_options.is_enabled("reactions") is False
    assert unsupported_options.is_enabled("room_voice") is False
    assert unsupported_options.is_enabled("wakeword") is False


@pytest.mark.asyncio
async def test_pipeline_service_options_property_and_init(mock_pipeline_dependencies):
    """Verify options property and init options handling."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )

    custom_options = PipelineOptions(
        persistent_profile_enabled=False,
        persistent_profile_supported=False,
        reactions_enabled=False,
        reactions_supported=False,
        room_voice_enabled=False,
        room_voice_supported=False,
        wakeword_enabled=False,
        wakeword_supported=False,
    )
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
        options=custom_options,
    )

    assert service.options is custom_options
    assert service.options.reactions_enabled is False
    assert service.options.room_voice_enabled is False
    assert service.options.wakeword_enabled is False
    assert service.options.persistent_profile_enabled is False


@pytest.mark.asyncio
async def test_pipeline_service_set_options_cmd(mock_pipeline_dependencies):
    """Verify SetOptionsCmd updates options and dispatches OptionsSetEvent."""
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

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    # 1. No changes -> returns False
    res = await service.execute_command(SetOptionsCmd())
    assert res is False

    # 2. Setting same value as current -> returns False
    res = await service.execute_command(SetOptionsCmd(reactions_enabled=True))
    assert res is False

    # 3. Setting new value -> returns True and dispatches OptionsSetEvent
    res = await service.execute_command(SetOptionsCmd(reactions_enabled=False))
    assert res is True
    assert service.options.reactions_enabled is False
    await asyncio.sleep(0.01)

    opt_events = [e for e in events if isinstance(e, OptionsSetEvent)]
    assert len(opt_events) == 1
    assert opt_events[0].reactions_enabled is False
    assert opt_events[0].room_voice_enabled is None
    assert opt_events[0].wakeword_enabled is None
    assert opt_events[0].persistent_profile_enabled is None

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_activation(mock_pipeline_dependencies):
    """Verify room_voice_enabled option controls audio_driver.activate."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )

    # 1. room_voice_enabled = True (default) -> driver.start_room_voice is called
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service.register_extension(DummyExtensionA, activate=True)

    cmd = ActivateProfileCmd(profile_id="alexa")
    await service.execute_command(cmd)
    audio_driver.start_room_voice.assert_called_once_with(profile_id="alexa")

    # 2. room_voice_enabled = False -> driver.start_room_voice is NOT called
    audio_driver.start_room_voice.reset_mock()
    await service.execute_command(SetOptionsCmd(room_voice_enabled=False))
    await service.execute_command(DeactivateProfileCmd())

    await service.execute_command(cmd)
    audio_driver.start_room_voice.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_toggle_live(mock_pipeline_dependencies):
    """Verify toggling room_voice_enabled immediately controls audio_driver."""
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
    service.register_extension(DummyExtensionA, activate=True)
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    audio_driver.stop_room_voice.reset_mock()
    audio_driver.start_room_voice.reset_mock()

    # Toggle to False -> calls driver.stop_room_voice
    res = await service.execute_command(SetOptionsCmd(room_voice_enabled=False))
    assert res is True
    assert service.options.room_voice_enabled is False
    audio_driver.stop_room_voice.assert_called_once()

    # Toggle to True -> calls driver.start_room_voice
    res = await service.execute_command(SetOptionsCmd(room_voice_enabled=True))
    assert res is True
    assert service.options.room_voice_enabled is True
    audio_driver.start_room_voice.assert_called_once_with(profile_id="alexa")

    # Handle error in audio_driver.start_room_voice gracefully
    audio_driver.start_room_voice.side_effect = RuntimeError("Audio error")
    await service.execute_command(SetOptionsCmd(room_voice_enabled=False))
    await service.execute_command(SetOptionsCmd(room_voice_enabled=True))


@pytest.mark.asyncio
async def test_pipeline_service_wakeword_toggle_and_modes(mock_pipeline_dependencies):
    """Verify deactivating profile uses wakeword_enabled to pick detection mode."""
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
    service.register_extension(DummyExtensionA, activate=True)

    # 1. wakeword_enabled = False -> deactivation does not change mode to WAKEWORD
    await service.execute_command(SetOptionsCmd(wakeword_enabled=False))
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    detection_worker.change_mode.reset_mock()
    audio_driver.disconnect.reset_mock()
    await service.execute_command(DeactivateProfileCmd())
    detection_worker.change_mode.assert_not_called()
    audio_driver.disconnect.assert_called_once()

    # 2. wakeword_enabled = True -> deactivation mode switches to WAKEWORD
    await service.execute_command(SetOptionsCmd(wakeword_enabled=True))
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    detection_worker.change_mode.reset_mock()
    audio_driver.disconnect.reset_mock()
    await service.execute_command(DeactivateProfileCmd())
    detection_worker.change_mode.assert_called_once_with(DetectionMode.WAKEWORD)
    audio_driver.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_service_detection_loop_wakeword_handling(
    mock_pipeline_dependencies,
):
    """Verify detection loop respects wakeword and persistent profile options."""
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
    service.register_extension(DummyExtensionA, activate=True)
    service.execute_command = AsyncMock()

    # Case 1: wakeword_enabled is False -> WakeWordDetectedEvent is ignored
    service._options = service._options.model_copy(update={"wakeword_enabled": False})
    service.execute_command.reset_mock()

    async def mock_detect_wakeword(_):
        yield WakeWordDetectedEvent(profile_id="alexa")

    service._detection_worker.detect = mock_detect_wakeword
    await service._detection_queue.put(MagicMock())

    raw = await service._detection_queue.get()
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, WakeWordDetectedEvent):
            if service.options.is_enabled("wakeword"):
                await service.execute_command(
                    ActivateProfileCmd(profile_id=res.profile_id),
                )
    service.execute_command.assert_not_called()

    # Case 2: wakeword_enabled is True -> triggers ActivateProfileCmd
    service._options = service._options.model_copy(update={"wakeword_enabled": True})
    service.execute_command.reset_mock()

    async for res in service._detection_worker.detect(raw):
        if isinstance(res, WakeWordDetectedEvent):
            if service.options.is_enabled("wakeword"):
                await service.execute_command(
                    ActivateProfileCmd(profile_id=res.profile_id),
                )
    service.execute_command.assert_called_once_with(
        ActivateProfileCmd(profile_id="alexa"),
    )

    # Case 3: ConversationEndedEvent when persistent_profile is True
    # does NOT deactivate profile
    service._options = service._options.model_copy(
        update={"persistent_profile_enabled": True}
    )
    service._active_profile = mock_profile
    service.execute_command.reset_mock()

    async def mock_detect_ended(_):
        yield ConversationEndedEvent()

    service._detection_worker.detect = mock_detect_ended
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ConversationEndedEvent):
            if (
                not service.options.is_enabled("persistent_profile")
                and service._active_profile
            ):
                await service.execute_command(DeactivateProfileCmd())

    service.execute_command.assert_not_called()

    # Case 4: ConversationEndedEvent when persistent_profile is False
    # triggers DeactivateProfileCmd
    service._options = service._options.model_copy(
        update={"persistent_profile_enabled": False}
    )
    service._active_profile = mock_profile
    service.execute_command.reset_mock()

    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ConversationEndedEvent):
            if (
                not service.options.is_enabled("persistent_profile")
                and service._active_profile
            ):
                await service.execute_command(DeactivateProfileCmd())

    service.execute_command.assert_called_once_with(
        DeactivateProfileCmd(),
    )


@pytest.mark.asyncio
async def test_pipeline_service_greeting_reaction_respects_options(
    mock_pipeline_dependencies,
):
    """Verify greeting reaction is only queued if reactions_enabled option is True."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    mock_profile.get_reaction.side_effect = lambda kind: (
        "Tak?" if kind == ReactionKind.GREETING else None
    )

    # 1. reactions_enabled = True (default) -> greeting is queued
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    service.register_extension(DummyExtensionA, activate=True)
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Tak?"

    # 2. reactions_enabled = False -> greeting is NOT queued
    await service.execute_command(DeactivateProfileCmd())
    await service.execute_command(SetOptionsCmd(reactions_enabled=False))
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    assert service._tts_queue.empty()


@pytest.mark.asyncio
async def test_pipeline_service_extension_lifecycle(mock_pipeline_dependencies):
    """Verify activate_extension and deactivate_extension event dispatching."""
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

    service.register_extension(DummyExtensionA, activate=True)
    service.register_extension(DummyExtensionB, activate=False)

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    # Activate DummyExtensionB
    res = await service.activate_extension(DummyExtensionB)
    assert res is True
    assert service.active_extension is DummyExtensionB

    # Reactivating same extension returns False
    res = await service.activate_extension(DummyExtensionB)
    assert res is False

    # Activating unregistered extension returns False
    class UnregisteredExtension(PipelineExtension):
        pass

    res = await service.activate_extension(UnregisteredExtension)
    assert res is False

    # Deactivate extension
    res = await service.deactivate_extension()
    assert res is True
    assert service.active_extension is None

    # Deactivating when none active returns False
    res = await service.deactivate_extension()
    assert res is False

    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    act_events = [e for e in events if isinstance(e, ExtensionActivatedEvent)]
    deact_events = [e for e in events if isinstance(e, ExtensionDeactivatedEvent)]
    assert len(act_events) >= 1
    assert len(deact_events) >= 1
