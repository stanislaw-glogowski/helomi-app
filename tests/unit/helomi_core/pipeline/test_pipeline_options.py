import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_core.audio import AudioDriver, RawAudio
from helomi_core.detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
)
from helomi_core.pipeline import (
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
from helomi_core.profile import ReactionKind


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
    audio_driver.activate = AsyncMock()
    audio_driver.deactivate = AsyncMock()
    audio_driver.interrupt = MagicMock(return_value=False)
    audio_driver.play = MagicMock()

    async def empty_capture():
        if False:
            yield MagicMock(spec=RawAudio)

    audio_driver.capture = empty_capture

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
    assert options.greeting_enabled is True
    assert options.room_voice_enabled is True
    assert options.wakeword_enabled is True


@pytest.mark.asyncio
async def test_pipeline_service_options_property_and_init(mock_pipeline_dependencies):
    """Verify options property and init options handling."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, _ = (
        mock_pipeline_dependencies
    )

    custom_options = PipelineOptions(
        greeting_enabled=False,
        room_voice_enabled=False,
        wakeword_enabled=False,
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
    assert service.options.greeting_enabled is False
    assert service.options.room_voice_enabled is False
    assert service.options.wakeword_enabled is False


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
    res = await service.execute_command(SetOptionsCmd(greeting_enabled=True))
    assert res is False

    # 3. Setting new value -> returns True and dispatches OptionsSetEvent
    res = await service.execute_command(SetOptionsCmd(greeting_enabled=False))
    assert res is True
    assert service.options.greeting_enabled is False
    await asyncio.sleep(0.01)

    opt_events = [e for e in events if isinstance(e, OptionsSetEvent)]
    assert len(opt_events) == 1
    assert opt_events[0].greeting_enabled is False
    assert opt_events[0].room_voice_enabled is None
    assert opt_events[0].wakeword_enabled is None

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_activation(mock_pipeline_dependencies):
    """Verify room_voice_enabled option controls audio_driver.activate."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )

    # 1. room_voice_enabled = True (default) -> driver.activate is called
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )

    cmd = ActivateProfileCmd(profile_id="alexa")
    await service.execute_command(cmd)
    audio_driver.activate.assert_called_once_with(mock_profile.audio)

    # 2. room_voice_enabled = False -> driver.activate is NOT called
    audio_driver.activate.reset_mock()
    await service.execute_command(SetOptionsCmd(room_voice_enabled=False))
    await service.execute_command(DeactivateProfileCmd())

    await service.execute_command(cmd)
    audio_driver.activate.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_room_voice_toggle_live(mock_pipeline_dependencies):
    """Verify toggling room_voice_enabled immediately controls audio_driver."""
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
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    audio_driver.deactivate.reset_mock()
    audio_driver.activate.reset_mock()

    # Toggle to False -> calls driver.deactivate
    res = await service.execute_command(SetOptionsCmd(room_voice_enabled=False))
    assert res is True
    assert service.options.room_voice_enabled is False
    audio_driver.deactivate.assert_called_once()

    # Toggle to True -> calls driver.activate
    res = await service.execute_command(SetOptionsCmd(room_voice_enabled=True))
    assert res is True
    assert service.options.room_voice_enabled is True
    audio_driver.activate.assert_called_once_with(mock_profile.audio)

    # Handle error in audio_driver.activate gracefully
    audio_driver.activate.side_effect = RuntimeError("Audio error")
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

    # 1. wakeword_enabled = True (default) -> deactivation mode is PROFILE
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    detection_worker.change_mode.reset_mock()
    await service.execute_command(DeactivateProfileCmd())
    detection_worker.change_mode.assert_called_once_with(DetectionMode.PROFILE)

    # 2. wakeword_enabled = False -> deactivation mode is UTTERANCE
    await service.execute_command(SetOptionsCmd(wakeword_enabled=False))
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    detection_worker.change_mode.reset_mock()
    await service.execute_command(DeactivateProfileCmd())
    detection_worker.change_mode.assert_called_once_with(DetectionMode.UTTERANCE)


@pytest.mark.asyncio
async def test_pipeline_service_detection_loop_wakeword_handling(
    mock_pipeline_dependencies,
):
    """Verify detection loop respects wakeword_enabled option."""
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
    service.execute_command = AsyncMock()

    # Case 1: wakeword_enabled is True
    # ProfileDetected triggers ActivateProfileCmd
    service._detection_worker.detect = MagicMock()

    async def mock_detect_profile(_):
        yield ProfileDetected(profile_id="alexa")

    service._detection_worker.detect.side_effect = mock_detect_profile
    await service._detection_queue.put(MagicMock())

    raw = await service._detection_queue.get()
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ProfileDetected):
            if service._options.wakeword_enabled:
                await service.execute_command(
                    ActivateProfileCmd(profile_id=res.profile_id),
                )
    service.execute_command.assert_called_once_with(
        ActivateProfileCmd(profile_id="alexa"),
    )

    # Case 2: wakeword_enabled is False -> ProfileDetected is ignored
    service.execute_command.reset_mock()
    await service.set_options(wakeword_enabled=False)

    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ProfileDetected):
            if service._options.wakeword_enabled:
                await service.execute_command(
                    ActivateProfileCmd(profile_id=res.profile_id),
                )
    service.execute_command.assert_not_called()

    # Case 3: ConversationEnded when wakeword_enabled is False
    # does NOT deactivate profile
    service._active_profile = mock_profile
    detection_worker.change_mode.reset_mock()

    async def mock_detect_ended(_):
        yield ConversationEnded()

    service._detection_worker.detect.side_effect = mock_detect_ended
    async for res in service._detection_worker.detect(raw):
        if isinstance(res, ConversationEnded):
            if service._options.wakeword_enabled:
                await service.execute_command(DeactivateProfileCmd())
            elif service._active_profile is not None:
                await service._detection_worker.change_mode(DetectionMode.UTTERANCE)

    service.execute_command.assert_not_called()
    detection_worker.change_mode.assert_called_once_with(DetectionMode.UTTERANCE)


@pytest.mark.asyncio
async def test_pipeline_service_greeting_reaction_respects_options(
    mock_pipeline_dependencies,
):
    """Verify greeting reaction is only queued if greeting_enabled option is True."""
    profiles, audio_driver, detection_worker, stt_worker, tts_worker, mock_profile = (
        mock_pipeline_dependencies
    )
    mock_profile.get_reaction.side_effect = lambda kind: (
        "Tak?" if kind == ReactionKind.GREETING else None
    )

    # 1. greeting_enabled = True -> greeting is queued
    service = PipelineService(
        profiles=profiles,
        audio_driver=audio_driver,
        detection_worker=detection_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    await service.execute_command(ActivateProfileCmd(profile_id="alexa"))
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Tak?"

    # 2. greeting_enabled = False -> greeting is NOT queued
    await service.execute_command(DeactivateProfileCmd())
    await service.execute_command(SetOptionsCmd(greeting_enabled=False))
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
