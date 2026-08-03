from typing import Literal

from helomi.common.validation import ConfigModel


class AudioSettings(ConfigModel):
    driver: Literal["avfaudio", "pyaudio"] = "avfaudio"
