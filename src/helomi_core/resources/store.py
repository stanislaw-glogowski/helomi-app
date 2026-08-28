import os
from pathlib import Path
from typing import ClassVar

from platformdirs import user_data_dir

from .files import ConfigData, ConfigFile
from .ports import LocalCatalog


class LocalStore(LocalCatalog):
    _LOCAL_DIR: ClassVar[str] = ".helomi"
    _HOME_ENV_VAR: ClassVar[str] = "HELOMI_HOME"
    _USER_DIR: ClassVar[str] = "Helomi"
    _SETTINGS_FILE: ClassVar[str] = "settings"
    _PROFILE_DIR: ClassVar[str] = "profiles"
    _PROFILE_FILE: ClassVar[str] = "profile"
    _DEFAULTS_FILE: ClassVar[str] = "defaults"

    def __init__(self, root_path: Path | None = None) -> None:
        self._root_path = (
            root_path if root_path is not None else self._locate_root_path()
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    def read_settings_data(self) -> ConfigData:
        data = ConfigFile.read_configs(self._root_path, "settings")
        if data is None:
            raise FileNotFoundError(
                f"No settings file found: {self._root_path}",
            )

        return data

    def read_profiles_data(self) -> dict[str, ConfigData]:
        result: dict[str, ConfigData] = {}
        root_path = self._root_path / self._PROFILE_DIR

        if not root_path.is_dir():
            raise FileNotFoundError(f"Profiles directory does not exist: {root_path}")

        default_data = ConfigFile.read_configs(root_path, self._DEFAULTS_FILE)

        for path in sorted(root_path.iterdir()):
            data = ConfigFile.read_configs(path, self._PROFILE_FILE)
            if data is None:
                continue

            if data.get("disabled", None):
                continue

            data["id"] = path.name
            result[path.name] = default_data.extend(data) if default_data else data

        if not result:
            raise FileNotFoundError(
                f"No settings file found: {root_path}",
            )

        return result

    def _locate_root_path(self) -> Path:
        if value := os.getenv(self._HOME_ENV_VAR):
            return Path(value).expanduser()

        start = Path.cwd()
        for directory in (start, *start.parents):
            local = directory / self._LOCAL_DIR
            if local.is_dir():
                return local

        return Path(user_data_dir(self._USER_DIR))
