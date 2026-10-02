from collections.abc import Collection
from typing import Any, ClassVar

from pydantic import model_validator

from helomi_foundation import ConfigFile, ConfigModel


def select_configs(
    data: Any,
    names: Collection[str],
    selected: Collection[str],
    *,
    defaults: bool = True,
) -> Any:
    """Prune inactive variants before references and model defaults are evaluated."""
    if not isinstance(data, dict):
        return data
    result = {
        key: value for key, value in data.items() if key not in names or key in selected
    }
    if defaults:
        for name in selected:
            if name in names and result.get(name) is None:
                result[name] = {}
    return result


class SelectedAdapterSettings(ConfigModel):
    _ADAPTERS: ClassVar[tuple[str, ...]]

    @model_validator(mode="before")
    @classmethod
    def select_adapter(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        adapter = ConfigFile.resolve_references(data.get("adapter"))
        data = {**data, "adapter": adapter}
        selected = (adapter,) if isinstance(adapter, str) else ()
        return ConfigFile.resolve_references(
            select_configs(data, cls._ADAPTERS, selected)
        )
