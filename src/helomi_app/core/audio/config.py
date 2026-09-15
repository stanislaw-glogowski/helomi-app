from typing import Literal

from pydantic import Field

from ...common import AdapterConfig, AdapterExtractor
from .avfaudio.config import AVFAudioProfile, AVFAudioSettings
from .twilio.config import TwilioProfile, TwilioSettings


class _BaseConfig(AdapterConfig):
    adapter: Literal["avfaudio", "twilio"] = "avfaudio"


class AudioSettings(_BaseConfig, AdapterExtractor[AVFAudioSettings | TwilioSettings]):
    avfaudio: AVFAudioSettings = Field(default_factory=AVFAudioSettings)
    twilio: TwilioSettings | None = None


class AudioProfile(_BaseConfig, AdapterExtractor[AVFAudioProfile | TwilioProfile]):
    avfaudio: AVFAudioProfile = Field(default_factory=AVFAudioProfile)
    twilio: TwilioProfile | None = None
