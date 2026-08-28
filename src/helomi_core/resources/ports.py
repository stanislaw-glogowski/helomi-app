from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from .files import ConfigData


class LocalCatalog(ABC):
    ASSETS_DIR: ClassVar[str] = "assets"
    MODELS_DIR: ClassVar[str] = "models"
    PROFILES_DIR: ClassVar[str] = "profiles"

    @property
    @abstractmethod
    def root_path(self) -> Path:
        raise NotImplementedError

    @abstractmethod
    def read_settings_data(self) -> ConfigData:
        raise NotImplementedError

    @abstractmethod
    def read_profiles_data(self) -> dict[str, ConfigData]:
        raise NotImplementedError
