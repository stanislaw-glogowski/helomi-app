from pydantic import FilePath

from helomi_common import BaseConfig


class AVFAudioConfig(BaseConfig):
    input_index: int | None = None
    output_index: int | None = None
    room_voice_path: FilePath | None = None
