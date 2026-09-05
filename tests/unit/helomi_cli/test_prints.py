from unittest.mock import MagicMock, patch

from helomi_cli.widgets.prints import (
    _print_adapter,
    _print_adapters,
    _print_profiles,
    print_exit,
    print_welcome,
)
from helomi_core import Runtime


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
    settings.audio.adapter = "avfaudio"
    settings.wakeword.adapter = "openwakeword"
    settings.vad.adapter = "silero_vad"
    settings.turn.adapter = "smart_turn"
    settings.stt.adapter = "parakeet"
    settings.tts.adapter = "voxcpm2"

    runtime = MagicMock(spec=Runtime)
    runtime.settings = settings
    runtime.profiles = MagicMock()
    runtime.profiles.__iter__ = MagicMock(return_value=iter([prof1, prof2, prof3]))
    runtime.profiles.get = MagicMock(return_value=prof1)

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        print_welcome(runtime, "Welcome message", profile_id="p2")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        print_exit("exit parrot mode")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        _print_adapter("Audio    ", "avfaudio")
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        _print_adapters(runtime)
        assert mock_print.called

    with patch("helomi_cli.widgets.prints.print") as mock_print:
        # Cover branches: active profile, default profile, other profile
        _print_profiles(runtime, profile_id="p2")
        assert mock_print.called
