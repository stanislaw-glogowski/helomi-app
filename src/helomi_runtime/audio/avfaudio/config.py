from helomi_foundation import ConfigModel

from ..room_voice import RoomVoiceProfile


class AVFAudioSettings(ConfigModel):
    voice_processing: bool = True


class AVFAudioProfile(ConfigModel):
    room_voice: RoomVoiceProfile | None = None
