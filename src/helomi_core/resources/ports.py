from abc import ABC, abstractmethod
from pathlib import Path

from .files import ConfigData


class LocalCatalog(ABC):
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
