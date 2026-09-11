from helomi_core.pipeline.domain import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ExtensionActivatedEvent,
    ExtensionDeactivatedEvent,
    OptionsSetEvent,
    PipelineOptions,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayReactionCmd,
    SayTextCmd,
    SetOptionsCmd,
    SpeechInterruptedEvent,
    SynthesisReadyEvent,
    TranscriptionReadyEvent,
)
from helomi_core.profile import ReactionKind


def test_pipeline_commands() -> None:
    act = ActivateProfileCmd(profile_id="p1", trace_id="tr1")
    assert act.type == "activate_profile"
    assert act.profile_id == "p1"
    assert act.trace_id == "tr1"

    deact = DeactivateProfileCmd(trace_id="tr2")
    assert deact.type == "deactivate_profile"
    assert deact.trace_id == "tr2"

    say = SayTextCmd(text="Hello", profile_id="p1")
    assert say.type == "say_text"
    assert say.text == "Hello"
    assert say.profile_id == "p1"

    reaction_cmd = SayReactionCmd(reaction=ReactionKind.GREETING, profile_id="p1")
    assert reaction_cmd.type == "say_reaction"
    assert reaction_cmd.reaction == ReactionKind.GREETING

    opt_cmd = SetOptionsCmd(greeting_enabled=False, room_voice_enabled=True)
    assert opt_cmd.type == "set_options"
    assert opt_cmd.greeting_enabled is False
    assert opt_cmd.room_voice_enabled is True
    assert opt_cmd.wakeword_enabled is None


def test_pipeline_events() -> None:
    p_act = ProfileActivatedEvent(profile_id="p1", trace_id="tr1")
    assert p_act.type == "profile_activated"
    assert p_act.profile_id == "p1"

    p_deact = ProfileDeactivatedEvent(profile_id="p1")
    assert p_deact.type == "profile_deactivated"
    assert p_deact.profile_id == "p1"

    trans = TranscriptionReadyEvent(profile_id="p1", text="speech text")
    assert trans.type == "transcription_ready"
    assert trans.text == "speech text"

    synth = SynthesisReadyEvent(profile_id="p1")
    assert synth.type == "synthesis_ready"
    assert synth.audio is None

    interrupted = SpeechInterruptedEvent(profile_id="p1")
    assert interrupted.type == "speech_interrupted"
    assert interrupted.profile_id == "p1"

    opt_event = OptionsSetEvent(greeting_enabled=False)
    assert opt_event.type == "options_set"
    assert opt_event.greeting_enabled is False

    ext_act = ExtensionActivatedEvent(
        active_profile_id="p1",
        options=PipelineOptions(),
    )
    assert ext_act.type == "extension_activated"
    assert ext_act.active_profile_id == "p1"

    ext_deact = ExtensionDeactivatedEvent()
    assert ext_deact.type == "extension_deactivated"
