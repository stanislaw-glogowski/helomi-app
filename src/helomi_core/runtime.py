from typing import TYPE_CHECKING, Any

from .audio import AudioDriver, AudioMode, get_audio_driver
from .config import Profile, Settings
from .detection import DetectionWorker
from .resources import LocalCatalog, LocalStore
from .stt import STTWorker, get_stt_adapter
from .tts import TTSWorker, get_tts_adapter
from .turn import get_turn_adapter
from .vad import get_vad_adapter
from .wakeword import get_wakeword_adapter

if TYPE_CHECKING:
    from .server import Server, ServerSettings
    from .speech import SpeechPipeline


class Runtime:
    def __init__(self, local_catalog: LocalCatalog | None = None) -> None:
        if local_catalog is None:
            local_catalog = LocalStore()

        settings = Settings.model_validate(
            local_catalog.read_settings_data(),
        )

        profiles = local_catalog.read_profiles_data()

        profile_adapters: dict[str, dict[str, Any]] = {
            "stt": {
                "adapter": settings.stt.adapter,
                settings.stt.adapter: {},
            },
            "tts": {
                "adapter": settings.tts.adapter,
                settings.tts.adapter: {},
            },
            "wakeword": {
                "adapter": settings.wakeword.adapter,
                settings.wakeword.adapter: {},
            },
        }

        profiles = {
            id: Profile.model_validate(data.extend(profile_adapters))
            for id, data in profiles.items()
        }

        self._settings = settings
        self._profiles = profiles
        self._default_profile_id = (
            default_profile_id
            if (default_profile_id := settings.profile.default)
            else next(iter(profiles))
        )

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def profiles(self) -> dict[str, Profile]:
        return self._profiles

    def get_profile(self, profile_id: str | None = None) -> Profile:
        if profile_id is None:
            profile_id = self._default_profile_id

        profile = self._profiles.get(profile_id)

        if profile is None:
            raise ValueError(f"Profile not found: {profile_id}")
        return profile

    def get_audio_driver(self, mode: AudioMode | None = None) -> AudioDriver:
        return get_audio_driver(self._settings.audio, mode)

    def get_detection_worker(self) -> DetectionWorker:
        return DetectionWorker(
            turn_adapter=get_turn_adapter(self._settings.turn),
            vad_adapter=get_vad_adapter(self._settings.vad),
            wakeword_adapter=get_wakeword_adapter(
                self._settings.wakeword,
                {id: profile.wakeword for id, profile in self._profiles.items()},
            ),
        )

    def get_stt_worker(self) -> STTWorker:
        return STTWorker(
            adapter=get_stt_adapter(self._settings.stt),
        )

    def get_tts_worker(self) -> TTSWorker:
        return TTSWorker(
            adapter=get_tts_adapter(self._settings.tts),
        )

    def get_speech_pipeline(self) -> SpeechPipeline:
        from .speech import SpeechPipeline

        return SpeechPipeline(self)

    def get_server(
        self,
        config: ServerSettings | None = None,
        auto_server: bool = True,
    ) -> Server:
        from .server import Server

        return Server(
            runtime=self,
            config=config or self._settings.server,
            auto_server=auto_server,
        )
