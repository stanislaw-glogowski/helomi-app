from typing import Any, Self


class DeepMergeDict[TKey = str, TItem = Any](dict[TKey, TItem]):
    def merged_with(self, override: dict[TKey, TItem] | None = None) -> Self:
        return self.__class__(self._merge_data(self, override)) if override else self

    def __or__(self, other: dict[TKey, TItem]) -> Self:  # type: ignore[override]
        return self.merged_with(other)

    @classmethod
    def _merge_data(cls, base: Any, override: Any) -> Any:
        if isinstance(base, dict) and isinstance(override, dict):
            result = base.copy()
            for key, value in override.items():
                result[key] = cls._merge_data(base.get(key), value)
            return result
        else:
            return override
