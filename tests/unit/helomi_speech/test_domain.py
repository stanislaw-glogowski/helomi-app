from pathlib import Path

from helomi_core.config import Profile
from helomi_speech.domain import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    SpeechRequest,
    TranscriptionReady,
)


def test_speech_commands():
    """Verify command models instantiation and discriminator fields."""
    cmd_act = ActivateProfile(profile_id="gizmo")
    assert cmd_act.type == "activate_profile"
    assert cmd_act.profile_id == "gizmo"

    cmd_deact = DeactivateProfile()
    assert cmd_deact.type == "deactivate_profile"

    cmd_say = SayText(text="Hello world", profile_id="viki")
    assert cmd_say.type == "say_text"
    assert cmd_say.text == "Hello world"
    assert cmd_say.profile_id == "viki"


def test_speech_events():
    """Verify speech event models instantiation and types."""
    ev_act = ProfileActivated(profile_id="viki")
    assert ev_act.type == "profile_activated"
    assert ev_act.profile_id == "viki"

    ev_deact = ProfileDeactivated(profile_id="viki")
    assert ev_deact.type == "profile_deactivated"
    assert ev_deact.profile_id == "viki"

    ev_trans = TranscriptionReady(profile_id="viki", text="Test transcript")
    assert ev_trans.type == "transcription_ready"
    assert ev_trans.text == "Test transcript"


def test_speech_request_profile_verification(tmp_path: Path):
    """Verify SpeechRequest verify_profile checks."""
    req = SpeechRequest(profile_id="active_p", data="sample_data")

    active_profile = Profile(name="Active", id="active_p", root_path=tmp_path)
    other_profile = Profile(name="Other", id="other_p", root_path=tmp_path)

    assert req.verify_profile(active_profile) == active_profile
    assert req.verify_profile(other_profile) is None
    assert req.verify_profile(None) is None
