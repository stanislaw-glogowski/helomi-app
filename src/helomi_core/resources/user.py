import os
from pathlib import Path
from typing import ClassVar

from platformdirs import user_data_dir

from .ports import ResourceCatalog


class UserData(ResourceCatalog):
    _HOME_ENV_VAR: ClassVar[str] = "HELOMI_HOME"
    _LOCAL_DIR: ClassVar[str] = "resources"
    _APP_DIR: ClassVar[str] = "HelomiApp"

    def __init__(self, root_path: Path | None = None) -> None:
        self._root_path = (
            root_path if root_path is not None else self._locate_root_path()
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    @classmethod
    def _locate_root_path(cls) -> Path:
        if value := os.getenv(cls._HOME_ENV_VAR):
            return Path(value).expanduser()

        start = Path.cwd()
        for directory in (start, *start.parents):
            local = directory / cls._LOCAL_DIR
            if local.is_dir():
                return local

        return Path(user_data_dir(cls._APP_DIR))
