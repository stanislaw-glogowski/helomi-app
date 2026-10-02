from unittest.mock import MagicMock, patch

from helomi_app import Application
from helomi_cli.widgets.prints import (
    _print_adapter,
    _print_adapters,
    _print_profiles,
    print_exit,
    print_welcome,
)


def test_prints_widgets() -> None:
    prof1 = MagicMock()
    prof1.id = "p1"
    prof1.name = "Profile 1"

    prof2 = MagicMock()
    prof2.id = "p2"
    prof2.name = "Profile 2"

    prof3 = MagicMock()
    prof3.id = "p3"
    prof3.name = "Profile 3"

    settings = MagicMock()
    settings.audio.drivers = ["avfaudio"]
    settings.detection.wakeword.adapter = "openwakeword"
    settings.detection.vad.adapter = "silero_vad"
    settings.detection.turn.adapter = "smart_turn"
    settings.transcription.adapter = "parakeet"
    settings.synthesis.adapter = "voxcpm2"

    application = MagicMock(spec=Application)
    application.settings = settings
    application.profiles = MagicMock()
    application.profiles.__iter__ = MagicMock(return_value=iter([prof1, prof2, prof3]))

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        print_welcome(application, "Welcome message", profile_id="p2")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        print_exit("exit parrot mode")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        _print_adapter("Audio    ", "avfaudio")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        _print_adapters(application)
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        # Cover branches: active profile and inactive profile.
        _print_profiles(application, profile_id="p2")
        assert mock_print.called
