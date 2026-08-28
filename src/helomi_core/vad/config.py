from typing import Literal

from helomi_common import AdapterConfig, AdapterExtractor

from .silero_vad.config import SileroVADConfig


class VADSettings(AdapterConfig, AdapterExtractor[SileroVADConfig]):
    adapter: Literal["silero_vad"] = "silero_vad"

    silero_vad: SileroVADConfig | None = None
