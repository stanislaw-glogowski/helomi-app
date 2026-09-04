from typing import Any, ClassVar, Literal, overload

from pydantic import BaseModel, ConfigDict, model_validator


class BaseConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    def _set_private_attr(self, name: str, value: Any) -> None:
        object.__setattr__(self, f"_{name}", value)


class AdapterConfig(BaseConfig):
    ADAPTER_KEY: ClassVar[str] = "adapter"

    @model_validator(mode="before")
    @classmethod
    def transform_adapters(cls, data: Any) -> Any:
        if isinstance(data, dict):
            field = cls.model_fields.get(cls.ADAPTER_KEY, None)

            if field is not None:
                name = data.get(cls.ADAPTER_KEY, field.get_default())

                if isinstance(name, str):
                    value: Any = data.get(name, None)
                    data = {
                        cls.ADAPTER_KEY: name,
                    }

                    if value is not None:
                        data[name] = value
        return data


class AdapterExtractor[TAdapter]:
    @overload
    def extract_adapter(self, require: Literal[True] = True) -> TAdapter: ...

    @overload
    def extract_adapter(self, require: Literal[False]) -> TAdapter | None: ...

    def extract_adapter(self, require=True) -> TAdapter | None:
        name = getattr(self, AdapterConfig.ADAPTER_KEY, None)
        if not isinstance(name, str):
            if require:
                raise AttributeError(
                    f"Class '{self.__class__.__name__}' does not have an "
                    f"'{AdapterConfig.ADAPTER_KEY}' field."
                )
            return None

        value = getattr(self, name, None)
        if value is None:
            if require:
                raise ValueError(f"Missing config for adapter: {name}")
            return None
        return value
