from typing import Any, Literal, overload


class AdapterExtractor:
    """Connect a selected global adapter to a profile-owned configuration."""

    @staticmethod
    @overload
    def extract[T](
        adapter: str,
        configs: object,
        *,
        required: Literal[True] = True,
        profile_id: str | None = None,
        path: object | None = None,
        section: str = "adapter",
    ) -> T: ...

    @staticmethod
    @overload
    def extract[T](
        adapter: str,
        configs: object,
        *,
        required: Literal[False],
        profile_id: str | None = None,
        path: object | None = None,
        section: str = "adapter",
    ) -> T | None: ...

    @staticmethod
    def extract[T](
        adapter: str,
        configs: object,
        *,
        required: bool = True,
        profile_id: str | None = None,
        path: object | None = None,
        section: str = "adapter",
    ) -> T | None:
        value: Any = getattr(configs, adapter, None)
        if value is not None:
            return value
        if not required:
            return None

        owner = f" for profile {profile_id!r}" if profile_id is not None else ""
        source = f" in {path}" if path is not None else ""
        raise ValueError(f"Missing {section}.{adapter} configuration{owner}{source}")
