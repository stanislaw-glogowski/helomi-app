from typing import Literal

from helomi_foundation import ConfigModel, HFModel


class SileroVADConfig(ConfigModel):
    engine: Literal["mlx"] = "mlx"
    model: HFModel = HFModel.default_field("mlx-community/silero-vad")
