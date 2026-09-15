from typing import Literal

from ...common import AdapterConfig, AdapterExtractor
from .silero_vad.config import SileroVADSettings


class VADSettings(AdapterConfig, AdapterExtractor[SileroVADSettings]):
    adapter: Literal["silero_vad"] = "silero_vad"

    silero_vad: SileroVADSettings | None = None
