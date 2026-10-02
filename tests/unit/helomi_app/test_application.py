from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helomi_app import (
    ActivationSource,
    Application,
    CommandResult,
    ResponseMode,
)
from helomi_app.config import (
    ApplicationSettings,
    ConversationSettings,
    ServerSettings,
)
from helomi_app.messages import ConversationState
from helomi_foundation import ManagedComponent


class FakeRuntime(ManagedComponent):
    def __init__(self):
        super().__init__()
        self.settings = MagicMock()
        self.settings.app = ApplicationSettings(
            conversation=ConversationSettings(),
            server=ServerSettings(),
            response_mode=ResponseMode.PARROT,
        ).model_dump()
        self.settings.transcription.adapter = "parakeet"
        self.settings.synthesis.adapter = "voxcpm2"
        self.profiles = MagicMock()
        self.resources = MagicMock()
        self.audio_router = MagicMock()

    async def get_reaction_catalog(self):
        return MagicMock()

    async def get_audio_router(self):
        return self.audio_router

    async def get_detection_worker(self):
        return MagicMock()

    async def get_transcription_worker(self):
        return MagicMock()

    async def get_synthesis_worker(self):
        return MagicMock()


class FakeConversation(ManagedComponent):
    def __init__(self):
        super().__init__()
        self.active_profile = None
        self.options = MagicMock()
        self.state = ConversationState.IDLE
        self.response_mode = ResponseMode.PARROT
        self.audio_router = MagicMock()
        self.commands = []

    async def execute_command(self, command):
        self.commands.append(command)
        return CommandResult.ok()

    async def _events(self):
        if False:
            yield None

    def subscribe_events(self):
        return self._events()


class FakeServer(ManagedComponent):
    docs_url = "http://127.0.0.1:4356/docs"


@pytest.mark.asyncio
async def test_application_facade_and_composition():
    runtime = FakeRuntime()
    conversation = FakeConversation()
    with (
        patch("helomi_app.application.Runtime", return_value=runtime),
        patch(
            "helomi_app.application.ConversationService",
            return_value=conversation,
        ),
        patch("helomi_app.server.ServerModule", return_value=FakeServer()),
    ):
        application = Application(
            Path("/unused"), serve_api=True, response_mode=ResponseMode.API
        )
        assert application.settings is runtime.settings
        assert application.resources is runtime.resources
        assert application.profiles is runtime.profiles
        with pytest.raises(RuntimeError, match="not mounted"):
            _ = application.state

        async with application:
            assert application.active_profile is None
            assert application.options is conversation.options
            assert application.state == ConversationState.IDLE
            assert application.response_mode == ResponseMode.PARROT
            assert application.audio_router is conversation.audio_router
            assert application.server is not None

            assert (
                await application.activate_profile("alexa", ActivationSource.CLI)
            ).accepted
            assert (await application.deactivate_profile(play_farewell=False)).accepted
            assert (
                await application.say_text(
                    "Hello", mode=ResponseMode.OPERATOR, profile_id="alexa"
                )
            ).accepted
            assert (await application.set_response_mode(ResponseMode.OPERATOR)).accepted
            assert (
                await application.execute_command(conversation.commands[-1])
            ).accepted
            assert application.subscribe_events() is not None

        assert application.server is None
        with pytest.raises(RuntimeError, match="not mounted"):
            _ = application.active_profile


@pytest.mark.asyncio
async def test_application_without_server():
    runtime = FakeRuntime()
    conversation = FakeConversation()
    with (
        patch("helomi_app.application.Runtime", return_value=runtime),
        patch("helomi_app.application.ConversationService", return_value=conversation),
    ):
        async with Application() as application:
            assert application.server is None


def test_application_parses_and_caches_its_own_settings():
    runtime = FakeRuntime()
    runtime.settings.app = {"response_mode": "api", "server": {"port": 9000}}
    with patch("helomi_app.application.Runtime", return_value=runtime):
        application = Application()
        assert application.app_settings.response_mode == ResponseMode.API
        assert application.app_settings.server.port == 9000
        assert application.app_settings is application.app_settings


@pytest.mark.asyncio
async def test_invalid_app_settings_fail_before_components_are_mounted():
    runtime = FakeRuntime()
    runtime.settings.app = {"server": {"port": 0}}
    runtime.settings.config_path = Path("settings.yml")
    with patch("helomi_app.application.Runtime", return_value=runtime):
        application = Application()
        with pytest.raises(ValueError, match=r"Invalid app settings in settings\.yml"):
            async with application:
                pytest.fail("Invalid application was mounted")
    assert not runtime.is_mounted
