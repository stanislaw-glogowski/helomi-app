import asyncio
from pathlib import Path

import numpy as np

from helomi_app.config import ConversationSettings
from helomi_app.conversation import ConversationService
from helomi_app.messages import (
    ActivateProfileCommand,
    ActivationSource,
    CallEndedEvent,
    CallStartedEvent,
    CommandRejectionCode,
    ConversationState,
    DeactivateProfileCommand,
    DriverChangedEvent,
    EndConversationCommand,
    ResponseMode,
    SayReactionCommand,
    SayTextCommand,
    SetConversationOptionsCommand,
    SetMonitoringCommand,
    SetResponseModeCommand,
    SpeechInterruptedEvent,
    SwitchDriverCommand,
    SynthesisReadyEvent,
    TranscriptionReadyEvent,
)
from helomi_app.response import (
    APIResponseModule,
    OperatorResponseModule,
    ParrotResponseModule,
)
from helomi_foundation import EventSource
from helomi_runtime.audio import (
    AudioChunk,
    AudioDriverCapabilities,
    AudioDriverDescriptor,
    AudioDriverKind,
    AudioFormat,
    CapturedEvent,
    ConnectedEvent,
    DisconnectedEvent,
    RawAudio,
    RouteChangedEvent,
)
from helomi_runtime.config import Profile, ProfileCatalog
from helomi_runtime.detection import (
    ConversationEndedEvent,
    DetectionMode,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)
from helomi_runtime.reaction import ReactionKind
from helomi_runtime.synthesis import SynthesisChunk
from helomi_runtime.transcription import TranscriptionResponse


class FakeAudioRouter(EventSource):
    def __init__(self):
        super().__init__()
        self.played: list[tuple[RawAudio, str | None, int | None]] = []
        self.interruptions = 0
        self.interrupted_turn_id: int | None = None
        self.room_voice_profile: str | None = None
        self.waited: list[str] = []
        self.monitoring_enabled = True
        self.remote_profile_id: str | None = None
        self.is_remote_session = False
        self.disconnects = 0
        self.switch_result = True
        self.driver_descriptors = (
            AudioDriverDescriptor(
                id="avfaudio",
                name="Local",
                kind=AudioDriverKind.LOCAL,
                capabilities=AudioDriverCapabilities(
                    capture=True,
                    playback=True,
                    interrupt=True,
                    room_voice=True,
                    remote_session=False,
                    local_monitoring=True,
                    manual_profile_selection=True,
                ),
            ),
        )

    async def play(self, audio, *, playback_id=None, turn_id=None):
        self.played.append((audio, playback_id, turn_id))
        return True

    async def wait_for_playback(self, playback_id, timeout_seconds):
        self.waited.append(playback_id)
        return True

    async def interrupt(self, *, turn_id=None):
        self.interruptions += 1
        self.interrupted_turn_id = turn_id
        return True

    async def start_room_voice(self, profile_id):
        self.room_voice_profile = profile_id
        return True

    async def stop_room_voice(self):
        self.room_voice_profile = None
        return True

    async def disconnect(self, farewell=None):
        self.disconnects += 1
        return True

    async def switch_driver(self, driver_id, *, end_remote_session=False):
        return self.switch_result and driver_id == "avfaudio"

    def set_monitoring(self, enabled):
        changed = self.monitoring_enabled != enabled
        self.monitoring_enabled = enabled
        return changed


class FakeDetectionWorker:
    wakeword_supported = True

    def __init__(self):
        self.current_mode = DetectionMode.WAKEWORD

    async def set_mode(self, mode, force=False):
        self.current_mode = mode
        return True

    async def reset_idle_timeout(self):
        pass

    async def detect(self, audio):
        if False:
            yield None


class FakeTranscriptionWorker:
    def __init__(self, responses=()):
        self.responses = responses

    async def transcribe(self, request):
        for response in self.responses:
            yield response


class FakeSynthesisWorker:
    def __init__(self, chunks=()):
        self.chunks = chunks

    async def synthesize(self, request):
        for chunk in self.chunks:
            yield chunk


class FakeReactions:
    def __init__(self, values):
        self.values = values

    def get_audio(self, profile_id, reaction):
        return self.values.get(reaction)


def create_profile(tmp_path: Path) -> Profile:
    return Profile.model_validate(
        {
            "name": "Alexa",
            "transcription": {"parakeet": {}},
            "synthesis": {"voxcpm2": {}},
            "wakeword": {"openwakeword": {"model_path": tmp_path / "wakeword.onnx"}},
        },
        context={
            "id": "alexa",
            "config_path": tmp_path / "profile.yml",
            "root_path": tmp_path,
            "prompts": {},
        },
    )


def create_service(
    tmp_path: Path,
    *,
    reactions: dict | None = None,
    settings: ConversationSettings | None = None,
    response_mode: ResponseMode = ResponseMode.PARROT,
    transcription_responses=(),
    synthesis_chunks=(),
) -> tuple[ConversationService, FakeAudioRouter, FakeDetectionWorker]:
    (tmp_path / "wakeword.onnx").touch()
    profile = create_profile(tmp_path)
    router = FakeAudioRouter()
    detection = FakeDetectionWorker()
    modules = {
        ResponseMode.API: APIResponseModule(),
        ResponseMode.PARROT: ParrotResponseModule(),
        ResponseMode.OPERATOR: OperatorResponseModule(),
    }
    service = ConversationService(
        settings=settings or ConversationSettings(),
        profiles=ProfileCatalog({"alexa": profile}),
        reactions=FakeReactions(reactions or {}),  # type: ignore[arg-type]
        audio_router=router,  # type: ignore[arg-type]
        detection_worker=detection,  # type: ignore[arg-type]
        transcription_worker=FakeTranscriptionWorker(transcription_responses),  # type: ignore[arg-type]
        synthesis_worker=FakeSynthesisWorker(synthesis_chunks),  # type: ignore[arg-type]
        transcription_adapter="parakeet",
        synthesis_adapter="voxcpm2",
        response_mode=response_mode,
        response_modules=modules,
    )
    return service, router, detection


def raw_audio() -> RawAudio:
    return RawAudio(
        AudioFormat.MONO_16,
        np.zeros(320, dtype=np.float32).tobytes(),
    )


async def test_greeting_plays_once_for_same_active_profile(tmp_path: Path):
    service, router, _ = create_service(
        tmp_path,
        reactions={ReactionKind.GREETING: raw_audio()},
    )

    async with router, service:
        command = ActivateProfileCommand(
            profile_id="alexa",
            source=ActivationSource.WAKEWORD,
        )
        assert (await service.execute_command(command)).accepted
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert (await service.execute_command(command)).accepted
        await asyncio.sleep(0)

    assert len(router.played) == 1


async def test_manual_profile_activation_does_not_play_greeting(tmp_path: Path):
    greeting = raw_audio()

    for source in (ActivationSource.CLI, ActivationSource.TRAY):
        service, router, _ = create_service(
            tmp_path,
            reactions={ReactionKind.GREETING: greeting},
        )
        async with router, service:
            result = await service.execute_command(
                ActivateProfileCommand(profile_id="alexa", source=source)
            )
            assert result.accepted
            assert service._speech_queue.empty()

        assert not router.played


async def test_barge_in_is_silent_and_invalidates_current_turn(tmp_path: Path):
    service, router, _ = create_service(tmp_path)
    events = []

    async with router, service:
        await service.execute_command(
            ActivateProfileCommand(
                profile_id="alexa",
                source=ActivationSource.WAKEWORD,
            )
        )

        async def collect_interruption():
            async for event in service.subscribe_events():
                events.append(event)
                if isinstance(event, SpeechInterruptedEvent):
                    return

        collector = asyncio.create_task(collect_interruption())
        await asyncio.sleep(0)
        service._set_state(ConversationState.SPEAKING)
        await service._handle_detection_event(UtteranceStartedEvent())
        await asyncio.wait_for(collector, 1)

    assert router.interruptions == 1
    assert router.interrupted_turn_id == 1
    assert sum(isinstance(event, SpeechInterruptedEvent) for event in events) == 1
    assert not router.played


async def test_follow_up_timeout_respects_wakeword_and_persistence(tmp_path: Path):
    service, _, detection = create_service(tmp_path)

    async with service:
        await service.execute_command(
            ActivateProfileCommand(
                profile_id="alexa",
                source=ActivationSource.WAKEWORD,
            )
        )
        await service._handle_follow_up_timeout()
        assert service.state == ConversationState.ARMED
        assert service.active_profile is not None
        assert detection.current_mode == DetectionMode.WAKEWORD

        await service.execute_command(SetConversationOptionsCommand(wakeword=False))
        service._set_state(ConversationState.LISTENING)
        await service._handle_follow_up_timeout()
        assert service.state == ConversationState.LISTENING
        assert detection.current_mode == DetectionMode.UTTERANCE


async def test_non_persistent_profile_is_removed_after_timeout(tmp_path: Path):
    service, router, _ = create_service(
        tmp_path,
        settings=ConversationSettings(persistent_profile=False),
        reactions={ReactionKind.FAREWELL: raw_audio()},
    )

    async with router, service:
        await service.execute_command(
            ActivateProfileCommand(
                profile_id="alexa",
                source=ActivationSource.WAKEWORD,
            )
        )
        await service._handle_follow_up_timeout()

    assert service.active_profile is None
    assert len(router.waited) == 1


async def test_inactive_response_mode_is_rejected(tmp_path: Path):
    service, _, _ = create_service(tmp_path)

    async with service:
        await service.execute_command(
            ActivateProfileCommand(
                profile_id="alexa",
                source=ActivationSource.CLI,
            )
        )
        result = await service.execute_command(
            SayTextCommand(
                text="Hello",
                mode=ResponseMode.API,
                profile_id="alexa",
            )
        )

    assert not result.accepted
    assert result.rejection_code == CommandRejectionCode.MODE_INACTIVE


async def test_api_synthesis_is_interruptible_before_playback(tmp_path: Path):
    service, router, _ = create_service(tmp_path, response_mode=ResponseMode.API)
    await service.execute_command(
        ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
    )
    result = await service.execute_command(
        SayTextCommand(text="Delayed response", mode=ResponseMode.API)
    )
    assert result.accepted
    assert service.state == ConversationState.PROCESSING

    await service._handle_detection_event(UtteranceStartedEvent())

    assert router.interruptions == 1
    assert router.interrupted_turn_id == 1
    assert service.state == ConversationState.LISTENING


async def test_complete_parrot_turn_emits_clean_synthesis(tmp_path: Path):
    audio = raw_audio()
    service, router, _ = create_service(
        tmp_path,
        transcription_responses=(TranscriptionResponse(text="Hello"),),
        synthesis_chunks=(SynthesisChunk(audio=audio),),
    )
    events = []

    async with router, service:
        await service.execute_command(
            ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
        )

        async def collect():
            async for event in service.subscribe_events():
                events.append(event)
                if isinstance(event, SynthesisReadyEvent):
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await service._handle_detection_event(
            UtteranceDetectedEvent(audio=AudioChunk.from_raw(audio))
        )
        await asyncio.wait_for(collector, 1)
        for _ in range(10):
            if router.played:
                break
            await asyncio.sleep(0)

    assert any(isinstance(event, TranscriptionReadyEvent) for event in events)
    synthesis = next(
        event for event in events if isinstance(event, SynthesisReadyEvent)
    )
    assert synthesis.audio == audio
    assert router.played[-1][0] == audio


async def test_profile_activation_rejections_and_switch(tmp_path: Path):
    service, router, _ = create_service(tmp_path)
    missing = await service.execute_command(
        ActivateProfileCommand(profile_id="missing", source=ActivationSource.CLI)
    )
    assert missing.rejection_code == CommandRejectionCode.PROFILE_NOT_FOUND

    mismatch = await service.execute_command(
        ActivateProfileCommand(profile_id="alexa", source=ActivationSource.TWILIO)
    )
    assert mismatch.rejection_code == CommandRejectionCode.PROFILE_MISMATCH

    router.remote_profile_id = "alexa"
    accepted = await service.execute_command(
        ActivateProfileCommand(profile_id="alexa", source=ActivationSource.TWILIO)
    )
    assert accepted.accepted
    assert (
        await service.execute_command(
            ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
        )
    ).accepted

    assert (
        await service.execute_command(DeactivateProfileCommand(play_farewell=False))
    ).accepted
    assert (
        await service.execute_command(EndConversationCommand(play_farewell=False))
    ).rejection_code == CommandRejectionCode.INVALID_STATE


async def test_text_reaction_and_queue_rejections(tmp_path: Path):
    service, _, _ = create_service(tmp_path)
    assert (
        await service.execute_command(
            SayTextCommand(text=" ", mode=ResponseMode.PARROT)
        )
    ).rejection_code == CommandRejectionCode.EMPTY_TEXT
    assert (
        await service.execute_command(
            SayTextCommand(text="Hello", mode=ResponseMode.PARROT)
        )
    ).rejection_code == CommandRejectionCode.PROFILE_REQUIRED

    await service.execute_command(
        ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
    )
    assert (
        await service.execute_command(
            SayTextCommand(text="Hello", mode=ResponseMode.PARROT, profile_id="missing")
        )
    ).rejection_code == CommandRejectionCode.PROFILE_MISMATCH
    assert (
        await service.execute_command(
            SayReactionCommand(
                reaction=ReactionKind.GREETING,
                mode=ResponseMode.API,
            )
        )
    ).rejection_code == CommandRejectionCode.MODE_INACTIVE
    assert (
        await service.execute_command(
            SayReactionCommand(
                reaction=ReactionKind.GREETING,
                mode=ResponseMode.PARROT,
                profile_id="missing",
            )
        )
    ).rejection_code == CommandRejectionCode.PROFILE_MISMATCH
    assert (
        await service.execute_command(
            SayReactionCommand(
                reaction=ReactionKind.GREETING,
                mode=ResponseMode.PARROT,
            )
        )
    ).rejection_code == CommandRejectionCode.UNSUPPORTED

    for index in range(100):
        assert (
            await service.execute_command(
                SayTextCommand(text=f"Sentence {index}", mode=ResponseMode.PARROT)
            )
        ).accepted
    assert service._speech_queue.qsize() == 100

    service._reactions.values[ReactionKind.GREETING] = raw_audio()
    assert (
        await service.execute_command(
            SayReactionCommand(reaction=ReactionKind.GREETING, mode=ResponseMode.PARROT)
        )
    ).accepted
    assert service._speech_queue.qsize() == 101


async def test_mode_driver_monitoring_and_options_commands(tmp_path: Path):
    service, router, detection = create_service(tmp_path)
    assert (
        await service.execute_command(SetResponseModeCommand(mode=ResponseMode.PARROT))
    ).rejection_code == CommandRejectionCode.INVALID_STATE
    assert (
        await service.execute_command(SwitchDriverCommand(driver_id="missing"))
    ).rejection_code == CommandRejectionCode.DRIVER_NOT_FOUND

    await service.execute_command(
        ActivateProfileCommand(profile_id="alexa", source=ActivationSource.CLI)
    )
    service._set_state(ConversationState.PROCESSING)
    assert (
        await service.execute_command(SetResponseModeCommand(mode=ResponseMode.API))
    ).accepted
    assert router.interruptions == 1
    assert router.interrupted_turn_id == 1

    router.is_remote_session = True
    assert (
        await service.execute_command(SwitchDriverCommand(driver_id="avfaudio"))
    ).rejection_code == CommandRejectionCode.CONFIRMATION_REQUIRED
    assert (
        await service.execute_command(
            SwitchDriverCommand(driver_id="avfaudio", end_remote_session=True)
        )
    ).accepted
    router.switch_result = False
    assert (
        await service.execute_command(
            SwitchDriverCommand(driver_id="avfaudio", end_remote_session=True)
        )
    ).rejection_code == CommandRejectionCode.UNSUPPORTED

    assert (
        await service.execute_command(SetMonitoringCommand(enabled=True))
    ).rejection_code == CommandRejectionCode.INVALID_STATE
    assert (await service.execute_command(SetMonitoringCommand(enabled=False))).accepted

    assert (
        await service.execute_command(SetConversationOptionsCommand())
    ).rejection_code == CommandRejectionCode.INVALID_STATE
    assert (
        await service.execute_command(SetConversationOptionsCommand(room_voice=False))
    ).accepted
    assert router.room_voice_profile is None
    assert (
        await service.execute_command(SetConversationOptionsCommand(room_voice=True))
    ).accepted
    assert router.room_voice_profile == "alexa"
    assert (
        await service.execute_command(SetConversationOptionsCommand(wakeword=False))
    ).accepted
    assert detection.current_mode == DetectionMode.UTTERANCE


async def test_audio_events_drive_remote_call_and_route(tmp_path: Path):
    service, router, _ = create_service(tmp_path)
    events = []
    router.remote_profile_id = "alexa"

    async def collect():
        async for event in service.subscribe_events():
            events.append(event)
            if isinstance(event, CallEndedEvent):
                return

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await service._handle_audio_event(
        ConnectedEvent(
            driver_id="twilio",
            profile_id="alexa",
            call_sid="CA1",
            caller="+48123456789",
        )
    )
    await service._handle_audio_event(
        RouteChangedEvent(
            driver_id="twilio", previous_driver_id="avfaudio", profile_id="alexa"
        )
    )
    await service._handle_audio_event(
        DisconnectedEvent(driver_id="twilio", call_sid="CA1")
    )
    await asyncio.wait_for(collector, 1)

    call = next(event for event in events if isinstance(event, CallStartedEvent))
    assert call.caller.endswith("6789") and call.caller.startswith("*")
    assert any(isinstance(event, DriverChangedEvent) for event in events)
    assert any(isinstance(event, CallEndedEvent) for event in events)
    assert service.active_profile is None

    rejected, rejected_router, _ = create_service(tmp_path)
    await rejected._handle_audio_event(
        ConnectedEvent(
            driver_id="twilio",
            profile_id="alexa",
            call_sid="CA2",
            caller="123",
        )
    )
    assert rejected_router.disconnects == 1


async def test_detection_events_and_bounded_input_queues(tmp_path: Path):
    service, _, _ = create_service(tmp_path)
    await service._handle_detection_event(WakeWordDetectedEvent(profile_id="alexa"))
    assert service.active_profile is not None
    await service.execute_command(SetConversationOptionsCommand(wakeword=False))
    await service._handle_detection_event(WakeWordDetectedEvent(profile_id="alexa"))

    service._set_state(ConversationState.CLOSING)
    await service._handle_detection_event(UtteranceStartedEvent())
    service._set_state(ConversationState.LISTENING)
    await service._handle_detection_event(
        UtteranceDetectedEvent(audio=AudioChunk.from_raw(raw_audio()))
    )
    assert service.state == ConversationState.PROCESSING
    assert service._transcription_queue.qsize() == 1

    for _ in range(150):
        await service._handle_audio_event(CapturedEvent(audio=raw_audio()))
    assert service._capture_seconds <= service._CAPTURE_BUFFER_SECONDS + 1e-9
    assert service._detection_queue.qsize() < 150
    assert service._capture_gap

    await service._handle_detection_event(ConversationEndedEvent())
