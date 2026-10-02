from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audio import AudioDriver
    from .audio.config import AudioDriverId
    from .detection import TurnAdapter, VADAdapter, WakeWordAdapter
    from .runtime import Runtime
    from .synthesis import SynthesisAdapter
    from .transcription import TranscriptionAdapter


def create_audio_drivers(runtime: Runtime) -> dict[AudioDriverId, AudioDriver]:
    from .audio.avfaudio.config import AVFAudioSettings
    from .audio.avfaudio.driver import AVFAudioDriver
    from .audio.twilio.config import TwilioSettings
    from .audio.twilio.driver import TwilioDriver

    drivers: dict[AudioDriverId, AudioDriver] = {}
    for driver_id in runtime.settings.audio.drivers:
        settings = runtime.settings.audio.require_driver_settings(driver_id)
        profiles = runtime.profiles.collect_audio_profiles(driver_id)
        match settings:
            case AVFAudioSettings():
                driver = AVFAudioDriver(settings, profiles)
            case TwilioSettings():
                driver = TwilioDriver(settings, profiles)
        drivers[driver_id] = driver
    return drivers


def create_transcription_adapter(runtime: Runtime) -> TranscriptionAdapter:
    from .config import AdapterExtractor
    from .transcription.parakeet.adapter import ParakeetAdapter
    from .transcription.parakeet.config import ParakeetSettings
    from .transcription.whisper.adapter import WhisperAdapter
    from .transcription.whisper.config import WhisperSettings

    settings = runtime.settings.transcription

    config = AdapterExtractor.extract(settings.adapter, settings)
    match config:
        case ParakeetSettings():
            return ParakeetAdapter(
                config,
                runtime.profiles.collect_adapter_profiles(
                    "transcription", settings.adapter
                ),
                settings.options,
            )
        case WhisperSettings():
            return WhisperAdapter(
                config,
                runtime.profiles.collect_adapter_profiles(
                    "transcription", settings.adapter
                ),
                settings.options,
            )

    raise ValueError("Missing selected transcription configuration")


def create_synthesis_adapter(runtime: Runtime) -> SynthesisAdapter:
    from .config import AdapterExtractor
    from .synthesis.piper.adapter import PiperAdapter
    from .synthesis.piper.config import PiperSettings
    from .synthesis.supertonic.adapter import SupertonicAdapter
    from .synthesis.supertonic.config import SupertonicSettings
    from .synthesis.voxcpm2.adapter import VoxCPM2Adapter
    from .synthesis.voxcpm2.config import VoxCPM2Settings

    settings = runtime.settings.synthesis
    profiles = runtime.profiles.collect_adapter_profiles("synthesis", settings.adapter)

    config = AdapterExtractor.extract(settings.adapter, settings)
    match config:
        case SupertonicSettings():
            return SupertonicAdapter(config, profiles)
        case VoxCPM2Settings():
            return VoxCPM2Adapter(config, profiles)
        case PiperSettings():
            return PiperAdapter(config, profiles)

    raise ValueError("Missing selected synthesis configuration")


def create_turn_adapter(runtime: Runtime) -> TurnAdapter:
    from .config import AdapterExtractor
    from .detection.smart_turn.adapter import SmartTurnAdapter

    settings = runtime.settings.detection.turn
    return SmartTurnAdapter(AdapterExtractor.extract(settings.adapter, settings))


def create_vad_adapter(runtime: Runtime) -> VADAdapter:
    from .config import AdapterExtractor
    from .detection.silero_vad.adapter import SileroVADAdapter

    settings = runtime.settings.detection.vad
    return SileroVADAdapter(
        AdapterExtractor.extract(settings.adapter, settings), settings.options
    )


def create_wakeword_adapter(runtime: Runtime) -> WakeWordAdapter | None:
    from .config import AdapterExtractor
    from .detection.openwakeword.adapter import OpenWakeWordAdapter

    settings = runtime.settings.detection.wakeword
    if settings is None:
        return None

    profiles = runtime.profiles.collect_adapter_profiles("wakeword", settings.adapter)
    return (
        OpenWakeWordAdapter(
            AdapterExtractor.extract(settings.adapter, settings), profiles
        )
        if profiles
        else None
    )
