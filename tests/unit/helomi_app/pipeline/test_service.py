import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from helomi_app.core.audio import (
    AudioChunk,
    AudioDriver,
    AudioFormat,
    CapturedEvent,
    DisconnectedEvent,
    RawAudio,
)
from helomi_app.core.audio.config import AudioProfile
from helomi_app.core.detection import (
    ConversationEndedEvent,
    DetectionWorker,
    UtteranceContinuedEvent,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
)
from helomi_app.core.stt import STTResponse, STTWorker
from helomi_app.core.tts import TTSChunk, TTSWorker
from helomi_app.pipeline import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayReactionCmd,
    SayTextCmd,
    SpeechInterruptedEvent,
    SynthesisReadyEvent,
    TranscriptionReadyEvent,
)
from helomi_app.pipeline.extension import PipelineExtension
from helomi_app.pipeline.request import PipelineRequest
from helomi_app.pipeline.service import PipelineService
from helomi_app.profile import Profile, ReactionKind


class MockExtensionA(PipelineExtension):
    pass


class MockExtensionB(PipelineExtension):
    pass


@pytest.fixture
def mock_profiles():
    prof1 = MagicMock(spec=Profile)
    prof1.id = "prof1"
    prof1.name = "Profile One"
    prof1.audio = AudioProfile.model_construct(
        room_voice_path=Path("/path/to/room1.wav"),
    )
    prof1.stt = MagicMock()
    prof1.tts = MagicMock()
    prof1.get_reaction = MagicMock(return_value=None)

    prof2 = MagicMock(spec=Profile)
    prof2.id = "prof2"
    prof2.name = "Profile Two"
    prof2.audio = AudioProfile.model_construct(
        room_voice_path=Path("/path/to/room2.wav"),
    )
    prof2.stt = MagicMock()
    prof2.tts = MagicMock()
    prof2.get_reaction = MagicMock(return_value=None)

    catalog = MagicMock()

    def _get_profile(k: str | None):
        return prof1 if k in ("prof1", None) else prof2

    catalog.get = MagicMock(side_effect=_get_profile)
    catalog.__iter__ = MagicMock(return_value=iter([prof1, prof2]))
    return catalog


@pytest.fixture
def mock_service(mock_profiles):
    audio_driver = MagicMock(spec=AudioDriver)
    audio_driver.start_room_voice = AsyncMock(return_value=True)
    audio_driver.stop_room_voice = AsyncMock(return_value=True)
    audio_driver.disconnect = AsyncMock(return_value=True)
    audio_driver.interrupt = AsyncMock(return_value=False)
    audio_driver.play = AsyncMock(return_value=True)

    async def empty_capture():
        if False:
            yield None

    audio_driver.capture = empty_capture

    det_worker = MagicMock(spec=DetectionWorker)
    det_worker.change_mode = AsyncMock()

    stt_worker = MagicMock(spec=STTWorker)
    tts_worker = MagicMock(spec=TTSWorker)

    service = PipelineService(
        profiles=mock_profiles,
        audio_driver=audio_driver,
        detection_worker=det_worker,
        stt_worker=stt_worker,
        tts_worker=tts_worker,
    )
    return service, audio_driver, det_worker, stt_worker, tts_worker


def test_pipeline_request_generation() -> None:
    initial_gen = PipelineRequest.current_generation()
    req1 = PipelineRequest(data="first")
    assert req1.generation == initial_gen
    assert req1.is_current_generation

    PipelineRequest.bump_generation()
    assert not req1.is_current_generation
    assert PipelineRequest.current_generation() == initial_gen + 1

    req2 = PipelineRequest(data="second")
    assert req2.generation == initial_gen + 1
    assert req2.is_current_generation


@pytest.mark.asyncio
async def test_pipeline_service_activation_flow(mock_service) -> None:
    service, audio_driver, det_worker, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)
    assert service.active_profile is None
    assert service.profiles is not None

    # First activation
    res = await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert res is True
    assert service.active_profile.id == "prof1"
    audio_driver.start_room_voice.assert_called_once_with(profile_id="prof1")
    det_worker.change_mode.assert_called_once()

    # Re-activating the same profile re-triggers and returns True (wakeword not omitted)
    res = await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert res is True
    assert service.active_profile.id == "prof1"

    # Switching to prof2
    res = await service.execute_command(ActivateProfileCmd(profile_id="prof2"))
    assert res is True
    assert service.active_profile.id == "prof2"
    assert audio_driver.start_room_voice.call_count == 2
    audio_driver.start_room_voice.assert_called_with(profile_id="prof2")

    # Deactivating profile
    res = await service.execute_command(DeactivateProfileCmd())
    assert res is True
    assert service.active_profile is None
    assert audio_driver.disconnect.call_count == 1

    # Deactivating when already None returns False
    res = await service.execute_command(DeactivateProfileCmd())
    assert res is False

    # Test activate_profile helper
    res = await service.activate_profile("prof1")
    assert res is True
    assert service.active_profile.id == "prof1"

    # Test deactivate_profile helper
    res = await service.deactivate_profile()
    assert res is True
    assert service.active_profile is None

    # Test say_text helper
    res = await service.say_text("Testing say_text helper")
    assert res is True
    assert service.active_profile.id == "prof1"


@pytest.mark.asyncio
async def test_pipeline_service_say_text(mock_service) -> None:
    service, _, _, _, _ = mock_service

    # Configure greeting reaction on prof1
    service._profiles.get("prof1").get_reaction = MagicMock(
        side_effect=lambda kind: "Cześć!" if kind == ReactionKind.GREETING else None
    )

    # SayText when active profile is None activates profile without greeting
    res = await service.execute_command(SayTextCmd(text="Hello world"))
    assert res is True
    assert service.active_profile.id == "prof1"
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Hello world"
    assert service._tts_queue.empty()

    # SayText with mismatching profile returns False
    res = await service.execute_command(SayTextCmd(text="Mismatch", profile_id="prof2"))
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_start_room_voice_error(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    service._active_extension = MockExtensionA(service)
    audio_driver.start_room_voice.side_effect = RuntimeError("audio_conversion_failed")

    # Initial activation handles activate failure gracefully
    res = await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert res is True
    assert service.active_profile.id == "prof1"

    # Switching profiles handles activate failure gracefully
    res = await service.execute_command(ActivateProfileCmd(profile_id="prof2"))
    assert res is True
    assert service.active_profile.id == "prof2"


@pytest.mark.asyncio
async def test_pipeline_service_subscribe_and_close(mock_service) -> None:
    service, _, _, _, _ = mock_service
    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    await asyncio.sleep(0.01)

    assert len(events) == 1
    assert isinstance(events[0], ProfileActivatedEvent)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_extensions_registration_and_activation(
    mock_service,
) -> None:
    service, _, _, _, _ = mock_service
    ext_a = MockExtensionA(service)
    ext_b = MockExtensionB(service)

    assert service.active_extension is None

    # Register ext_a and activate it
    service.register_extension(ext_a, activate=True)
    assert service.active_extension is MockExtensionA

    # Re-registering ext_a raises ValueError
    with pytest.raises(ValueError, match="already registered"):
        service.register_extension(ext_a)

    # Register ext_b without activating
    service.register_extension(ext_b, activate=False)
    assert service.active_extension is MockExtensionA

    # Switch active extension
    changed = await service.activate_extension(MockExtensionB)
    assert changed is True
    assert service.active_extension is MockExtensionB

    # Switching to same extension returns False
    changed_again = await service.activate_extension(MockExtensionB)
    assert changed_again is False


@pytest.mark.asyncio
async def test_pipeline_service_extension_filtering(mock_service) -> None:
    service, _, _, _, _ = mock_service
    ext_a = MockExtensionA(service)
    ext_b = MockExtensionB(service)

    service.register_extension(ext_a, activate=True)
    service.register_extension(ext_b, activate=False)

    # Inactive extension execute_command returns False
    cmd = SayTextCmd(text="Hi from B")
    res_b = await service.execute_command(cmd, extension=ext_b)
    assert res_b is False

    # Active extension execute_command succeeds
    res_a = await service.execute_command(cmd, extension=ext_a)
    assert res_a is True

    # Subscription filtering
    events_a = []
    events_b = []

    async def sub_a():
        async for evt in service.subscribe_event(extension=ext_a):
            events_a.append(evt)

    async def sub_b():
        async for evt in service.subscribe_event(extension=ext_b):
            events_b.append(evt)

    task_a = asyncio.create_task(sub_a())
    task_b = asyncio.create_task(sub_b())
    await asyncio.sleep(0.01)

    # Dispatch event
    service._dispatch_event(ProfileActivatedEvent(profile_id="prof1"))
    await asyncio.sleep(0.01)

    assert len(events_a) == 1
    assert len(events_b) == 0

    task_a.cancel()
    task_b.cancel()
    await asyncio.gather(task_a, task_b, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_detection_loop_speech_interrupted(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    async def mock_detect(audio):
        yield UtteranceDetectedEvent(audio=MagicMock(spec=AudioChunk))

    service._detection_worker.detect = mock_detect

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    task.cancel()
    await asyncio.gather(det_task, task, return_exceptions=True)

    # Check that SpeechInterrupted was dispatched
    interrupted_events = [e for e in events if isinstance(e, SpeechInterruptedEvent)]
    assert len(interrupted_events) == 1
    assert interrupted_events[0].profile_id == "prof1"
    assert not service._stt_queue.empty()


@pytest.mark.asyncio
async def test_pipeline_service_stt_tts_and_playback_loops(mock_service) -> None:
    service, audio_driver, _, stt_worker, tts_worker = mock_service

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # Mock STT worker
    async def fake_transcribe(request):
        yield STTResponse(text="Transcribed text")

    stt_worker.transcribe = fake_transcribe

    # Mock TTS worker
    fake_audio = MagicMock(spec=RawAudio)

    async def fake_synthesize(request):
        yield TTSChunk(audio=fake_audio)

    tts_worker.synthesize = fake_synthesize

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    sub_task = asyncio.create_task(listener())
    stt_task = asyncio.create_task(service._stt_loop())
    tts_task = asyncio.create_task(service._tts_loop())
    playback_task = asyncio.create_task(service._playback_loop())

    await asyncio.sleep(0.01)

    # Trigger STT
    req_audio = MagicMock(spec=RawAudio)
    await service.execute_command(SayTextCmd(text="test TTS"))

    service._stt_queue.put_nowait(
        PipelineRequest(data=MagicMock(audio=req_audio)),
    )

    await asyncio.sleep(0.05)

    assert any(
        isinstance(e, TranscriptionReadyEvent) and e.text == "Transcribed text"
        for e in events
    )
    audio_driver.play.assert_called_with(
        audio=fake_audio,
    )

    sub_task.cancel()
    stt_task.cancel()
    tts_task.cancel()
    playback_task.cancel()
    await asyncio.gather(
        sub_task, stt_task, tts_task, playback_task, return_exceptions=True
    )


@pytest.mark.asyncio
async def test_pipeline_service_say_text_empty(mock_service) -> None:
    service, _, _, _, _ = mock_service
    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # Empty text returns False
    res = await service.execute_command(SayTextCmd(text=""))
    assert res is False

    res = await service.execute_command(SayTextCmd(text="   "))
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_utterance_started_barge_in(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    service.active_profile.get_reaction = MagicMock(
        side_effect=lambda kind: "Tak?" if kind == ReactionKind.INTERRUPTED else None
    )

    async def mock_detect(audio):
        yield UtteranceStartedEvent()
        yield UtteranceContinuedEvent()

    service._detection_worker.detect = mock_detect

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    task.cancel()
    await asyncio.gather(det_task, task, return_exceptions=True)

    interrupted_events = [e for e in events if isinstance(e, SpeechInterruptedEvent)]
    assert len(interrupted_events) == 1
    assert interrupted_events[0].profile_id == "prof1"
    assert service._tts_queue.empty()


@pytest.mark.asyncio
async def test_pipeline_service_greeting_reaction(mock_service) -> None:
    service, _, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)

    # Configure greeting reaction
    service._profiles.get("prof1").get_reaction = MagicMock(
        side_effect=lambda kind: "Cześć!" if kind == ReactionKind.GREETING else None
    )

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Cześć!"


@pytest.mark.asyncio
async def test_pipeline_service_synthesis_ready_event(mock_service) -> None:
    service, _, _, _, tts_worker = mock_service

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    raw1 = RawAudio(format=AudioFormat.MONO_16, data=b"\x00" * 32)
    fake_chunk = TTSChunk(audio=raw1)

    async def fake_synth(request):
        yield fake_chunk

    tts_worker.synthesize = fake_synth

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    sub_task = asyncio.create_task(listener())
    tts_task = asyncio.create_task(service._tts_loop())

    await asyncio.sleep(0.01)
    await service.execute_command(SayTextCmd(text="Hello synthesis"))
    await asyncio.sleep(0.05)

    synthesis_events = [e for e in events if isinstance(e, SynthesisReadyEvent)]
    assert len(synthesis_events) == 1
    assert synthesis_events[0].profile_id == "prof1"
    assert synthesis_events[0].audio == raw1

    sub_task.cancel()
    tts_task.cancel()
    await asyncio.gather(sub_task, tts_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_interrupted_reaction(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    service.active_profile.get_reaction = MagicMock(
        side_effect=lambda kind: "Tak?" if kind == ReactionKind.INTERRUPTED else None
    )

    async def mock_detect(audio):
        yield UtteranceStartedEvent()

    service._detection_worker.detect = mock_detect
    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    await asyncio.gather(det_task, return_exceptions=True)

    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Tak?"
    assert req.data.profile_id == "prof1"


@pytest.mark.asyncio
async def test_pipeline_service_farewell_reaction_deactivation(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)

    service._profiles.get("prof1").get_reaction = MagicMock(
        side_effect=lambda kind: (
            "Do widzenia!" if kind == ReactionKind.FAREWELL else None
        )
    )

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert service.active_profile.id == "prof1"

    # Trigger deactivation with farewell
    res = await service.execute_command(DeactivateProfileCmd())
    assert res is True
    # Profile stays active while farewell is being spoken
    assert service.active_profile is not None
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Do widzenia!"
    assert req.is_final is True

    # Simulate DisconnectedEvent arriving after playback finishes
    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    sub_task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    async def fake_events():
        yield DisconnectedEvent()

    audio_driver.subscribe_event = fake_events
    cap_task = asyncio.create_task(service._capture_loop())
    await asyncio.sleep(0.05)
    cap_task.cancel()
    sub_task.cancel()
    await asyncio.gather(cap_task, sub_task, return_exceptions=True)

    assert service.active_profile is None
    assert any(isinstance(e, ProfileDeactivatedEvent) for e in events)


@pytest.mark.asyncio
async def test_pipeline_service_persistent_profile_continuous_conversation(
    mock_service,
) -> None:
    service, _, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)
    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert service.active_profile.id == "prof1"

    # Persistent profile is enabled by default
    assert service.options.is_enabled("persistent_profile") is True

    async def mock_detect(audio):
        yield ConversationEndedEvent()

    service._detection_worker.detect = mock_detect
    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    await asyncio.gather(det_task, return_exceptions=True)

    # In persistent profile mode, conversation timeout does NOT deactivate profile
    assert service.active_profile.id == "prof1"


@pytest.mark.asyncio
async def test_pipeline_service_say_reaction_and_mismatch(mock_service) -> None:
    service, _, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)
    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # Profile mismatch
    res = await service.execute_command(
        SayTextCmd(text="Hello", profile_id="unknown_prof")
    )
    assert res is False

    # SayReactionCmd with valid reaction
    service._profiles.get("prof1").get_reaction.return_value = "Witaj!"
    res = await service.execute_command(
        SayReactionCmd(reaction=ReactionKind.GREETING, profile_id="prof1")
    )
    assert res is True
    assert not service._tts_queue.empty()
    req = service._tts_queue.get_nowait()
    assert req.data.text == "Witaj!"

    # SayReactionCmd with empty reaction returns False
    service._profiles.get("prof1").get_reaction.return_value = None
    res = await service.execute_command(
        SayReactionCmd(reaction=ReactionKind.FAREWELL, profile_id="prof1")
    )
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_capture_loop_events(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    service.register_extension(MockExtensionA, activate=True)

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    sub_task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    # 1. CapturedEvent with profile_id activates profile and queues audio
    raw_audio = MagicMock(spec=RawAudio)

    async def stream_captured():
        yield CapturedEvent(audio=raw_audio, profile_id="prof1")
        await asyncio.sleep(0.02)
        # 2. DisconnectedEvent deactivates profile
        yield DisconnectedEvent()

    audio_driver.subscribe_event = stream_captured
    cap_task = asyncio.create_task(service._capture_loop())
    await asyncio.sleep(0.05)
    cap_task.cancel()
    sub_task.cancel()
    await asyncio.gather(cap_task, sub_task, return_exceptions=True)

    assert any(isinstance(e, ProfileActivatedEvent) for e in events)
    assert any(isinstance(e, ProfileDeactivatedEvent) for e in events)
    assert service.active_profile is None


@pytest.mark.asyncio
async def test_pipeline_service_extension_lifecycle_advanced(mock_service) -> None:
    service, audio_driver, det_worker, _, _ = mock_service
    audio_driver.room_voice_supported = True
    det_worker.wakeword_supported = True

    # Register extension A and activate
    service.register_extension(MockExtensionA, activate=True)
    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # sync_extension dispatches ExtensionActivatedEvent
    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    sub_task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    await service.sync_extension()
    await asyncio.sleep(0.01)

    # Deactivate extension stops room voice
    res = await service.deactivate_extension()
    assert res is True
    audio_driver.stop_room_voice.assert_called()

    # Re-activating extension when profile is active starts room voice
    service.register_extension(MockExtensionB, activate=False)
    audio_driver.start_room_voice.reset_mock()
    res = await service.activate_extension(MockExtensionB)
    assert res is True
    audio_driver.start_room_voice.assert_called_with(profile_id="prof1")

    sub_task.cancel()
    await asyncio.gather(sub_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pipeline_service_activate_invalid_profile(mock_service) -> None:
    service, _, _, _, _ = mock_service
    # ProfileCatalog raises KeyError for missing profile; should be handled cleanly
    service._profiles.get = MagicMock(side_effect=KeyError("Profile not found"))
    res = await service.execute_command(ActivateProfileCmd(profile_id="non_existent"))
    assert res is False


@pytest.mark.asyncio
async def test_pipeline_service_stop_room_voice_error(mock_service) -> None:
    service, audio_driver, _, _, _ = mock_service
    audio_driver.stop_room_voice.side_effect = RuntimeError("driver error")

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # Deactivating profile with failing stop_room_voice should not raise
    res = await service.execute_command(DeactivateProfileCmd())
    assert res is True


@pytest.mark.asyncio
async def test_pipeline_service_interrupt_cooldown_blocks_second_interrupt(
    mock_service,
) -> None:
    """After first interrupt, cooldown prevents second interrupt.

    This ensures that reaction playback is protected from interruption.
    """
    service, audio_driver, _, _, _ = mock_service
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    assert not service._interrupt_cooldown

    # Two UtteranceStartedEvent in a row — second should be blocked by cooldown
    async def mock_detect(audio):
        yield UtteranceStartedEvent()
        yield UtteranceStartedEvent()

    service._detection_worker.detect = mock_detect

    events = []

    async def listener():
        async for evt in service.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    task.cancel()
    await asyncio.gather(det_task, task, return_exceptions=True)

    # Only ONE SpeechInterruptedEvent despite two UtteranceStartedEvents
    interrupted_events = [e for e in events if isinstance(e, SpeechInterruptedEvent)]
    assert len(interrupted_events) == 1
    assert service._interrupt_cooldown is True


@pytest.mark.asyncio
async def test_pipeline_service_interrupt_cooldown_clears_on_utterance_detected(
    mock_service,
) -> None:
    """Cooldown clears when user finishes speaking (UtteranceDetectedEvent)."""
    service, audio_driver, _, _, _ = mock_service
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))

    # Interrupt → cooldown ON → UtteranceDetected → cooldown OFF
    async def mock_detect(audio):
        yield UtteranceStartedEvent()
        yield UtteranceDetectedEvent(audio=MagicMock(spec=AudioChunk))

    service._detection_worker.detect = mock_detect
    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    await asyncio.gather(det_task, return_exceptions=True)

    assert service._interrupt_cooldown is False
    assert not service._stt_queue.empty()


@pytest.mark.asyncio
async def test_pipeline_service_interrupt_cooldown_clears_on_conversation_ended(
    mock_service,
) -> None:
    """Cooldown clears on ConversationEndedEvent (timeout)."""
    service, audio_driver, _, _, _ = mock_service
    audio_driver.interrupt = AsyncMock(return_value=True)

    await service.execute_command(ActivateProfileCmd(profile_id="prof1"))
    service._interrupt_cooldown = True  # simulate active cooldown

    async def mock_detect(audio):
        yield ConversationEndedEvent()

    service._detection_worker.detect = mock_detect
    service._detection_queue.put_nowait(MagicMock(spec=RawAudio))

    det_task = asyncio.create_task(service._detection_loop())
    await asyncio.sleep(0.05)
    det_task.cancel()
    await asyncio.gather(det_task, return_exceptions=True)

    assert service._interrupt_cooldown is False
