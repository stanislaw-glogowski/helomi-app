from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audio import AudioDriver
    from .runtime import Runtime
    from .stt import STTAdapter
    from .tts import TTSAdapter
    from .turn import TurnAdapter
    from .vad import VADAdapter
    from .wakeword import WakeWordAdapter


def get_audio_driver(runtime: Runtime) -> AudioDriver:
    from .audio.avfaudio.config import AVFAudioSettings

    profiles = runtime.profiles.get_adapter_profiles("audio")

    match settings := runtime.settings.audio.extract_adapter():
        case AVFAudioSettings():
            from .audio.avfaudio.driver import AVFAudioDriver

            return AVFAudioDriver(settings, profiles)

        case _:
            raise ValueError(f"Unsupported local audio adapter: {settings}")


def get_stt_adapter(runtime: Runtime) -> STTAdapter:
    from .stt.parakeet.config import ParakeetSettings
    from .stt.whisper.config import WhisperSettings

    profiles = runtime.profiles.get_adapter_profiles("stt")

    match settings := runtime.settings.stt.extract_adapter():
        case ParakeetSettings():
            from .stt.parakeet.adapter import ParakeetAdapter

            return ParakeetAdapter(settings, profiles)

        case WhisperSettings():
            from .stt.whisper.adapter import WhisperAdapter

            return WhisperAdapter(settings, profiles)

        case _:
            raise ValueError(f"Unsupported STT adapter: {settings}")


def get_tts_adapter(runtime: Runtime) -> TTSAdapter:
    from .tts.supertonic.config import SupertonicSettings
    from .tts.voxcpm2.config import VoxCPM2Settings

    profiles = runtime.profiles.get_adapter_profiles("tts")

    match settings := runtime.settings.tts.extract_adapter():
        case SupertonicSettings():
            from .tts.supertonic.adapter import SupertonicAdapter

            return SupertonicAdapter(settings, profiles)
        case VoxCPM2Settings():
            from .tts.voxcpm2.adapter import VoxCPM2Adapter

            return VoxCPM2Adapter(settings, profiles)

        case _:
            raise ValueError(f"Unsupported TTS adapter: {settings}")


def get_turn_adapter(runtime: Runtime) -> TurnAdapter:
    from .turn.smart_turn.config import SmartTurnSettings

    match settings := runtime.settings.turn.extract_adapter():
        case SmartTurnSettings():
            from .turn.smart_turn.adapter import SmartTurnAdapter

            return SmartTurnAdapter(settings)

        case _:
            raise ValueError(f"Unsupported turn adapter: {settings}")


def get_vad_adapter(runtime: Runtime) -> VADAdapter:
    from .vad.silero_vad.config import SileroVADMLXSettings, SileroVADONNXSettings

    match settings := runtime.settings.vad.extract_adapter():
        case SileroVADMLXSettings():
            from .vad.silero_vad.mlx_adapter import SileroVADMLXAdapter

            return SileroVADMLXAdapter(settings)

        case SileroVADONNXSettings():
            from vad.silero_vad.onnx_adapter import SileroVADONNXAdapter

            return SileroVADONNXAdapter(settings)

        case _:
            raise ValueError(f"Unsupported VAD adapter: {settings}")


def get_wakeword_adapter(runtime: Runtime) -> WakeWordAdapter | None:
    profiles = runtime.profiles.get_adapter_profiles("wakeword")

    if not profiles:
        return None

    from .wakeword.openwakeword.config import OpenWakeWordSettings

    match settings := runtime.settings.wakeword.extract_adapter():
        case OpenWakeWordSettings():
            from .wakeword.openwakeword.adapter import OpenWakeWordAdapter

            return OpenWakeWordAdapter(settings, profiles)

        case None:
            return None

        case _:
            raise ValueError(f"Unsupported wakeword adapter: {settings}")
