from helomi_foundation import ConfigModel, HFModel


class SmartTurnConfig(ConfigModel):
    model: HFModel = HFModel.default_field("mlx-community/smart-turn-v3")
    threshold: float = 0.5
    max_audio_seconds: float = 30.0
    pre_roll_seconds: float = 0.5
    post_roll_seconds: float = 0.2
    min_speech_seconds: float = 0.3
    silence_seconds: float = 0.5
    fallback_silence_seconds: float = 1.8
    conversation_timeout_seconds: float = 30.0
