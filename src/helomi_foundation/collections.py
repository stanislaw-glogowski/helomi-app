from typing import Any, Self


class DeepMergeDict[TKey = str, TValue = Any](dict[TKey, TValue]):
    """Dictionary with recursive, non-mutating override semantics."""

    def merged_with(self, override: dict[TKey, TValue] | None = None) -> Self:
        if override is None:
            return self.__class__(self)
        return self.__class__(self._merge(self, override))

    @classmethod
    def _merge(cls, base: Any, override: Any) -> Any:
        if isinstance(base, dict) and isinstance(override, dict):
            result = base.copy()
            for key, value in override.items():
                result[key] = cls._merge(base.get(key), value)
            return result
        return override
