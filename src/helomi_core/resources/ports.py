from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal


class ResourceCatalog(ABC):
    _ASSETS_DIR: ClassVar[str] = "assets"
    _MODELS_DIR: ClassVar[str] = "models"
    _PROFILES_DIR: ClassVar[str] = "profiles"

    @property
    @abstractmethod
    def root_path(self) -> Path:
        raise NotImplementedError

    def build_path(
        self,
        resource: Literal["assets", "models", "profiles"],
        profile_id: str | None = None,
    ) -> Path:
        match resource, profile_id:
            case "assets", None:
                return self.root_path / self._ASSETS_DIR
            case "assets", str():
                return (
                    self.root_path / self._PROFILES_DIR / profile_id / self._ASSETS_DIR
                )
            case "models", None:
                return self.root_path / self._MODELS_DIR
            case "models", str():
                return (
                    self.root_path / self._PROFILES_DIR / profile_id / self._MODELS_DIR
                )
            case "profiles", None:
                return self.root_path / self._PROFILES_DIR
            case "profiles", str():
                return self.root_path / self._PROFILES_DIR / profile_id
            case _, _:
                return self.root_path
