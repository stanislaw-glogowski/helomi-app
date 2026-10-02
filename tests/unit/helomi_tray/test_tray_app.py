from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from helomi_app import (
    ActivationSource,
    CallEndedEvent,
    CallStartedEvent,
    CommandResult,
    ConversationOptionsChangedEvent,
    ConversationState,
    ConversationStateChangedEvent,
    DriverChangedEvent,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    ResponseMode,
    ResponseModeChangedEvent,
)
from helomi_app.config import ApplicationSettings
from helomi_runtime.audio import (
    AudioDriverCapabilities,
    AudioDriverDescriptor,
    AudioDriverKind,
)
from helomi_tray.app import TrayApplication, TrayState, TrayStatus


def _info(
    driver_id: str,
    *,
    remote: bool = False,
    selectable: bool = True,
) -> AudioDriverDescriptor:
    return AudioDriverDescriptor(
        id=driver_id,
        name="Twilio" if remote else "Mac audio",
        kind=AudioDriverKind.GSM if remote else AudioDriverKind.LOCAL,
        capabilities=AudioDriverCapabilities(
            capture=True,
            playback=True,
            interrupt=True,
            room_voice=True,
            remote_session=remote,
            local_monitoring=not remote,
            manual_profile_selection=selectable,
        ),
    )


class FakeProfiles:
    def __init__(self):
        self.profile = SimpleNamespace(
            id="alexa", name="Alexa", emoji="👩🏻", has_room_voice=True
        )

    def __iter__(self):
        return iter([self.profile])

    def get(self, profile_id):
        assert profile_id == "alexa"
        return self.profile


class FakeApplication:
    def __init__(self):
        self.app_settings = ApplicationSettings()
        self.settings = SimpleNamespace(
            audio=SimpleNamespace(
                initial_driver="avfaudio",
                drivers=[
                    "avfaudio",
                    "twilio",
                ],
            ),
            detection=SimpleNamespace(wakeword=SimpleNamespace()),
        )
        self.profiles = FakeProfiles()
        self.execute_command = AsyncMock(return_value=CommandResult.ok())
        self.events = []

    async def subscribe_events(self):
        for event in self.events:
            yield event


def _running_state(**updates) -> TrayState:
    base = TrayState(
        status=TrayStatus.RUNNING,
        response_mode=ResponseMode.PARROT,
        conversation_state=ConversationState.LISTENING,
        profile_id="alexa",
        api_url="http://127.0.0.1:4356/docs",
        persistent_profile=True,
        reactions=True,
        room_voice=True,
        wakeword=True,
        active_driver_id="avfaudio",
        driver_descriptors=(
            _info("avfaudio"),
            _info("twilio", remote=True, selectable=False),
        ),
        monitoring=True,
    )
    return replace(base, **updates)


def test_tray_initialization_and_state_rendering():
    app = TrayApplication(FakeApplication())  # type: ignore[arg-type]
    assert app._state.status == TrayStatus.STARTING
    assert app._menu_profiles.get_action("alexa").title == "Alexa"
    assert "default" not in app._menu_profiles.get_action("alexa").title.lower()

    app._state = _running_state()
    app._sync_state(None)
    assert app._menu_profiles.get_action("alexa").enabled
    assert app._menu_drivers.get_action("avfaudio").checked
    assert not app._menu_drivers.get_action("twilio").enabled
    assert app._menu_modes.get_action("parrot").checked
    assert app._menu_settings.get_action("room_voice").enabled
    assert app._menu_server.enabled
    assert "Alexa" in app.title

    app._state = _running_state(
        active_driver_id="twilio", remote_session=True, response_mode=ResponseMode.API
    )
    app._sync_state(None)
    assert not app._menu_profiles.get_action("alexa").enabled
    assert app._menu_drivers.get_action("twilio").checked
    assert app._menu_modes.get_action("api").checked

    app._state = replace(app._state, status=TrayStatus.QUITTING)
    app._sync_state(None)
    assert not app._menu_settings.get_action("wakeword").enabled


def test_tray_callbacks_issue_public_commands():
    app = TrayApplication(FakeApplication())  # type: ignore[arg-type]
    app._state = _running_state()
    app._execute = MagicMock()

    profile = app._menu_profiles.get_action("alexa")
    app._on_profile_click(profile)
    assert app._execute.call_args.args[0].source == ActivationSource.TRAY
    profile.set_checked(True)
    app._on_profile_click(profile)
    assert app._execute.call_args.args[0].type == "deactivate_profile"

    app._on_mode_click(app._menu_modes.get_action("api"))
    assert app._execute.call_args.args[0].mode == ResponseMode.API
    app._on_setting_click(app._menu_settings.get_action("wakeword"))
    assert app._execute.call_args.args[0].wakeword is True

    with patch("helomi_tray.app.app.webbrowser.open") as opened:
        app._on_server_click(app._menu_server)
    opened.assert_called_once_with("http://127.0.0.1:4356/docs")

    driver = app._menu_drivers.get_action("twilio")
    app._on_driver_click(driver)
    assert app._execute.call_args.args[0].driver_id == "twilio"
    app._state = replace(app._state, remote_session=True)
    with patch("helomi_tray.app.app.ConfirmDialog.open", return_value=False):
        before = app._execute.call_count
        app._on_driver_click(driver)
        assert app._execute.call_count == before
    with patch("helomi_tray.app.app.ConfirmDialog.open", return_value=True):
        app._on_driver_click(driver)
        assert app._execute.call_args.args[0].end_remote_session is True


def test_tts_and_call_windows_are_independent():
    app = TrayApplication(FakeApplication())  # type: ignore[arg-type]
    app._state = _running_state()
    app._execute = MagicMock()
    tts = MagicMock()
    call = MagicMock()
    with (
        patch("helomi_tray.app.app.TTSWindow", return_value=tts),
        patch("helomi_tray.app.app.CallWindow", return_value=call),
    ):
        app._on_tts_click()
        assert app._tts_window is tts
        tts.show.assert_called_once()
        assert app._execute.call_args.args[0].mode == ResponseMode.OPERATOR
        app._handle_tts_send("Hello")
        assert app._execute.call_args.args[0].text == "Hello"

        event = CallStartedEvent(profile_id="alexa", caller="****6789", monitoring=True)
        app._open_call_window(event)
        assert app._call_window is call
        call.show.assert_called_once()
        assert app._tts_window is tts

        app._set_monitoring(False)
        assert app._state.monitoring is False
        app._end_call()
        assert app._execute.call_args.args[0].type == "end_conversation"
        app._handle_call_closed()
        assert app._call_window is None
        app._handle_tts_closed()
        assert app._tts_window is None
        assert app._execute.call_args.args[0].mode == ResponseMode.PARROT


async def test_event_loop_updates_state_and_forwards_windows():
    application = FakeApplication()
    application.events = [
        ProfileActivatedEvent(profile_id="alexa", source=ActivationSource.TWILIO),
        DriverChangedEvent(driver_id="twilio", previous_driver_id="avfaudio"),
        CallStartedEvent(profile_id="alexa", caller="****6789", monitoring=True),
        ResponseModeChangedEvent(
            mode=ResponseMode.API, previous_mode=ResponseMode.PARROT
        ),
        ConversationStateChangedEvent(
            state=ConversationState.PROCESSING,
            previous_state=ConversationState.LISTENING,
        ),
        ConversationOptionsChangedEvent(
            persistent_profile=False,
            reactions=False,
            room_voice=False,
            wakeword=False,
        ),
        CallEndedEvent(profile_id="alexa"),
        ProfileDeactivatedEvent(profile_id="alexa"),
    ]
    app = TrayApplication(application)  # type: ignore[arg-type]
    app._state = _running_state()
    app._tts_window = MagicMock()
    app._open_call_window = MagicMock()
    with patch(
        "helomi_tray.app.app.PyObjCTools.AppHelper.callAfter",
        side_effect=lambda callback, *args: callback(*args),
    ):
        await app._event_loop()
    assert app._state.profile_id is None
    assert app._state.response_mode == ResponseMode.API
    assert app._state.conversation_state == ConversationState.PROCESSING
    assert not app._state.persistent_profile
    app._open_call_window.assert_called_once()


def test_start_animation_and_command_without_loop():
    app = TrayApplication(FakeApplication())  # type: ignore[arg-type]
    app._animate_start_icon(None)
    assert app.title.startswith("⠋")
    app._state = replace(app._state, status=TrayStatus.RUNNING)
    timer = MagicMock()
    app._animate_start_icon(timer)
    timer.stop.assert_called_once()
    assert app._execute(MagicMock()) is None
