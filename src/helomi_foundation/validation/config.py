from typing import Any

from pydantic import BaseModel, ConfigDict


class ConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    def _set_private_attr(self, name: str, value: Any) -> None:
        object.__setattr__(self, f"_{name}", value)
