from pydantic import FilePath

from ....common import BaseConfig


class AVFAudioSettings(BaseConfig):
    voice_processing: bool = True


class AVFAudioProfile(BaseConfig):
    room_voice_path: FilePath | None = None
