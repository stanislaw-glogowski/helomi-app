from helomi_foundation import ConfigModel, HFModel

_DEFAULT_MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v3"


class ParakeetSettings(ConfigModel):
    model: HFModel = HFModel.default_field(_DEFAULT_MODEL_ID)


class ParakeetProfile(ConfigModel):
    language: str | None = None
