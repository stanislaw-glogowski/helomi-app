import os
from pathlib import Path

import yaml
from platformdirs import user_data_dir

from .configuration import load_mapping, merge_mappings
from .models import ModelCatalog
from .profiles import Profile, ProfileCatalog, ProfileEntry
from .settings import Settings, SettingsStore


class LocalStore(ModelCatalog, ProfileCatalog, SettingsStore):
    _HOME_ENV_VAR = "HELOMI_HOME"
    _LOCAL_DIR = ".helomi"
    _USER_DIR = "Helomi"
    _LOCALES_PATH = "locales"

    def __init__(
        self,
        root_path: Path | None = None,
        *,
        language: str | None = None,
        selected_profile: str | None = None,
    ) -> None:
        self._root_path = (
            root_path if root_path is not None else self._locate_root_path()
        )
        self._language_override = language
        self._selected_profile_override = selected_profile

    def ensure_model_path(self, *paths: Path | str) -> Path:
        path = (self._root_path / self._MODELS_DIR).joinpath(*paths)
        if not path.is_file():
            raise FileNotFoundError(f"Model file does not exist: {path}")
        return path

    def load_profile(self, name: str) -> Profile:
        path = self._profiles_path / name
        if not path.is_dir():
            raise FileNotFoundError(f"Profile directory does not exist: {path}")
        return Profile.load_from_directory(path)

    def list_profiles(self) -> list[Profile]:
        if not self._profiles_path.is_dir():
            raise FileNotFoundError(
                f"Profiles directory does not exist: {self._profiles_path}"
            )

        return [
            Profile.load_from_directory(path)
            for path in sorted(self._profiles_path.iterdir())
            if path.is_dir()
        ]

    def inspect_profiles(self) -> list[ProfileEntry]:
        if not self._profiles_path.is_dir():
            return []

        entries: list[ProfileEntry] = []
        for path in sorted(self._profiles_path.iterdir()):
            if not path.is_dir():
                continue
            try:
                profile = Profile.load_from_directory(path)
            except Exception as error:
                entries.append(
                    ProfileEntry(
                        id=path.name,
                        name=self._profile_name(path),
                        error=str(error),
                    )
                )
            else:
                entries.append(
                    ProfileEntry(
                        id=profile.id,
                        name=profile.name,
                        profile=profile,
                    )
                )
        return entries

    def load_settings(self) -> Settings:
        path = self._root_path / self._SETTINGS_FILE
        if not path.is_file():
            raise FileNotFoundError(f"Settings file does not exist: {path}")
        root = load_mapping(path, label="Settings configuration")
        root_override = self._root_path / self._SETTINGS_OVERRIDE_FILE
        if root_override.is_file():
            root = merge_mappings(
                root,
                load_mapping(root_override, label="Settings override configuration"),
            )

        language = self._locale_name(
            self._language_override or root.get("language", "en-US")
        )
        locale_path = self._root_path / self._LOCALES_PATH / language
        locale_settings = locale_path / self._SETTINGS_FILE
        if not locale_settings.is_file():
            raise FileNotFoundError(
                f"Locale settings file does not exist: {locale_settings}"
            )
        locale = load_mapping(locale_settings, label="Locale settings configuration")
        self._reject_locale_language(locale_settings, locale)
        locale = self._without_empty_locale_sections(locale)
        settings = merge_mappings(root, locale)

        locale_override = locale_path / self._SETTINGS_OVERRIDE_FILE
        if locale_override.is_file():
            override = load_mapping(
                locale_override,
                label="Locale settings override configuration",
            )
            self._reject_locale_language(locale_override, override)
            override = self._without_empty_locale_sections(override)
            settings = merge_mappings(settings, override)

        settings["language"] = language
        if self._selected_profile_override is not None:
            settings = merge_mappings(
                settings,
                {"profiles": {"selected": self._selected_profile_override}},
            )
        return Settings.from_mapping(settings)

    def load_default_profile(self) -> Profile:
        profiles = tuple(
            entry.profile for entry in self.inspect_profiles() if entry.profile
        )
        if not profiles:
            raise FileNotFoundError("No valid profiles are available")
        default_profile = self.load_settings().profiles.default
        if default_profile is not None:
            for profile in profiles:
                if profile.id == default_profile:
                    return profile
        return profiles[0]

    @property
    def _profiles_path(self) -> Path:
        language = self.load_settings().language
        return self._root_path / self._LOCALES_PATH / language / self._PROFILES_PATH

    @staticmethod
    def _locale_name(value: object) -> str:
        if not isinstance(value, str) or not value or value in {".", ".."}:
            raise ValueError(f"Language must be a locale directory name; got {value!r}")
        if Path(value).name != value:
            raise ValueError(f"Language must be a locale directory name; got {value!r}")
        return value

    @staticmethod
    def _reject_locale_language(path: Path, data: dict) -> None:
        if "language" in data:
            raise ValueError(f"Locale settings must not define language: {path}")

    @staticmethod
    def _without_empty_locale_sections(data: dict) -> dict:
        return {
            key: value
            for key, value in data.items()
            if not (key in {"conversation", "speech"} and value is None)
        }

    def _locate_root_path(self) -> Path:
        if value := os.getenv(self._HOME_ENV_VAR):
            return Path(value).expanduser()

        start = Path.cwd()
        for directory in (start, *start.parents):
            local = directory / self._LOCAL_DIR
            if local.is_dir():
                return local

        return Path(user_data_dir(self._USER_DIR))

    @staticmethod
    def _profile_name(path: Path) -> str:
        profile_path = path / "profile.yml"
        if not profile_path.is_file():
            return path.name
        try:
            data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        except OSError, yaml.YAMLError:
            return path.name
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            name = data["name"].strip()
            if name:
                return name
        return path.name
