from pydantic import Field

from helomi.common.validation import ConfigModel

from .audio import AudioSettings
from .capture import VADSettings, WakeWordProfile, WakeWordSettings
from .segmentation import SegmentationSettings
from .synthesis import TTSProfile, TTSSettings, default_tts_settings
from .transcription import STTProfile, STTSettings, default_stt_settings


class TurnTakingSettings(ConfigModel):
    sustained_barge_in_frames: int = Field(default=20, gt=0)
    continuation_silence_frames: int = Field(default=38, gt=0)
    reaction_pause: float = Field(default=0.2, ge=0.0)


class SpeechSettings(ConfigModel):
    audio: AudioSettings = AudioSettings()
    vad: VADSettings = VADSettings()
    wakeword: WakeWordSettings = WakeWordSettings()
    segmentation: SegmentationSettings = SegmentationSettings()
    turn_taking: TurnTakingSettings = TurnTakingSettings()
    tts: TTSSettings = default_tts_settings()
    stt: STTSettings = default_stt_settings()


class SpeechProfile(TTSProfile, STTProfile):
    wakeword: WakeWordProfile | None = None
