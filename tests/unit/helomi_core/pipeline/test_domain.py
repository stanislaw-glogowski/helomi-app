from helomi_core.pipeline.domain import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    SpeechInterrupted,
    SynthesisReady,
    TranscriptionReady,
)


def test_pipeline_commands() -> None:
    act = ActivateProfile(profile_id="p1", trace_id="tr1")
    assert act.type == "activate_profile"
    assert act.profile_id == "p1"
    assert act.trace_id == "tr1"

    deact = DeactivateProfile(trace_id="tr2")
    assert deact.type == "deactivate_profile"
    assert deact.trace_id == "tr2"

    say = SayText(text="Hello", profile_id="p1")
    assert say.type == "say_text"
    assert say.text == "Hello"
    assert say.profile_id == "p1"


def test_pipeline_events() -> None:
    p_act = ProfileActivated(profile_id="p1", trace_id="tr1")
    assert p_act.type == "profile_activated"
    assert p_act.profile_id == "p1"

    p_deact = ProfileDeactivated(profile_id="p1")
    assert p_deact.type == "profile_deactivated"
    assert p_deact.profile_id == "p1"

    trans = TranscriptionReady(profile_id="p1", text="speech text")
    assert trans.type == "transcription_ready"
    assert trans.text == "speech text"
    assert trans.audio is None

    synth = SynthesisReady(profile_id="p1", text="hello")
    assert synth.type == "synthesis_ready"
    assert synth.text == "hello"
    assert synth.audio is None

    interrupted = SpeechInterrupted(profile_id="p1")
    assert interrupted.type == "speech_interrupted"
    assert interrupted.profile_id == "p1"
