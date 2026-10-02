from pathlib import Path

import pytest
from pydantic import ValidationError

from helomi_foundation import ConfigFile
from helomi_runtime.audio.config import AudioRouterSettings
from helomi_runtime.config import Profile, ProfileCatalog, Settings
from helomi_runtime.resources import FileSystemResourceCatalog


def test_settings_and_profiles_load_without_default_profile(
    temp_helomi_store: Path,
):
    resources = FileSystemResourceCatalog(temp_helomi_store)
    settings = Settings.load(resources)
    profiles = ProfileCatalog.load(settings, resources)

    assert settings.audio.initial_driver == "avfaudio"
    assert settings.transcription.adapter == "parakeet"
    assert settings.synthesis.adapter == "voxcpm2"
    assert profiles.get("alexa").id == "alexa"
    assert "profile" not in Settings.model_fields


@pytest.mark.parametrize(
    "data, message",
    [
        (
            {
                "initial_driver": "avfaudio",
                "drivers": ["avfaudio", "avfaudio"],
                "avfaudio": {},
            },
            "Duplicate audio drivers",
        ),
        (
            {"initial_driver": "twilio", "drivers": ["avfaudio"], "avfaudio": {}},
            "Initial audio driver is not configured",
        ),
        (
            {
                "initial_driver": "avfaudio",
                "monitor_driver": "twilio",
                "drivers": ["avfaudio", "twilio"],
                "avfaudio": {},
                "twilio": {
                    "auth_token": "secret",
                    "public_url": "https://example.test/voice/",
                },
            },
            "Twilio cannot be used as a monitor",
        ),
    ],
)
def test_audio_router_rejects_invalid_driver_layout(data: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        AudioRouterSettings.model_validate(data)


def test_audio_driver_union_rejects_unknown_variant():
    with pytest.raises(ValidationError, match="literal_error"):
        AudioRouterSettings.model_validate(
            {"initial_driver": "unknown", "drivers": ["unknown"], "unknown": {}}
        )


def test_audio_configuration_resolves_driver_settings_and_profiles():
    settings = AudioRouterSettings.model_validate(
        {"initial_driver": "avfaudio", "drivers": ["avfaudio"], "avfaudio": {}}
    )
    profile = Profile.model_validate(
        {"name": "Alexa"},
        context={
            "id": "alexa",
            "config_path": Path("profile.yml"),
            "root_path": Path("."),
            "prompts": {},
        },
    )

    assert settings.require_driver_settings("avfaudio").voice_processing is True
    assert profile.audio.find_driver_profile("avfaudio") is None
    assert profile.audio.find_driver_profile("twilio") is None
    with pytest.raises(KeyError, match="Audio driver is not configured"):
        settings.require_driver_settings("twilio")


def test_config_file_resolves_paths_and_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "settings.yml"
    asset_path = tmp_path / "asset.bin"
    asset_path.touch()
    config_path.write_text(
        "path: path://asset.bin\ntoken: env://HELOMI_TEST_TOKEN\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HELOMI_TEST_TOKEN", "value")

    data = ConfigFile.read_merged(tmp_path / "settings")

    assert data == {"path": asset_path, "token": "value"}


def test_config_file_reports_missing_environment_variable(tmp_path: Path):
    config_path = tmp_path / "settings.yml"
    config_path.write_text("token: env://HELOMI_MISSING_TOKEN\n", encoding="utf-8")

    with pytest.raises(ValueError, match="HELOMI_MISSING_TOKEN"):
        ConfigFile.read_merged(tmp_path / "settings")


def test_missing_selected_profile_adapter_has_source_context(tmp_path: Path):
    config_path = tmp_path / "profile.yml"
    profile = Profile.model_validate(
        {"name": "Alexa"},
        context={
            "id": "alexa",
            "config_path": config_path,
            "root_path": tmp_path,
            "prompts": {},
        },
    )

    with pytest.raises(ValueError) as raised:
        profile.get_synthesis_profile("piper")

    assert "profile 'alexa'" in str(raised.value)
    assert str(config_path) in str(raised.value)


def test_duplicate_twilio_callee_is_rejected(tmp_path: Path):
    def create_profile(profile_id: str) -> Profile:
        return Profile.model_validate(
            {
                "name": profile_id,
                "audio": {"twilio": {"callees": ["+15555550100"]}},
            },
            context={
                "id": profile_id,
                "config_path": tmp_path / profile_id / "profile.yml",
                "root_path": tmp_path / profile_id,
                "prompts": {},
            },
        )

    with pytest.raises(ValueError, match="assigned to both"):
        ProfileCatalog(
            {
                "first": create_profile("first"),
                "second": create_profile("second"),
            }
        )


def test_profile_public_data_and_catalog_queries(tmp_path: Path):
    room_voice = tmp_path / "room.wav"
    room_voice.touch()
    model = tmp_path / "wake.onnx"
    model.touch()
    config_path = tmp_path / "profile.yml"
    profile = Profile.model_validate(
        {
            "name": "Alexa",
            "emoji": "",
            "readonly": True,
            "reactions": {"greeting": "Hello"},
            "audio": {
                "avfaudio": {"room_voice": {"path": room_voice}},
                "twilio": {"callees": ["+15555550100"]},
            },
            "transcription": {"parakeet": {}},
            "synthesis": {"voxcpm2": {}},
            "wakeword": {"openwakeword": {"model_path": model}},
        },
        context={
            "id": "alexa",
            "config_path": config_path,
            "root_path": tmp_path,
            "prompts": {"system": "Hello"},
        },
    )
    assert profile.id == "alexa"
    assert profile.root_path == tmp_path
    assert profile.config_path == config_path
    assert profile.prompts == {"system": "Hello"}
    assert profile.emoji == "👤"
    assert profile.has_room_voice
    assert profile.reactions["greeting"] == ["Hello"]
    assert profile.get_audio_profile("avfaudio") is not None
    assert profile.get_transcription_profile("parakeet") is not None
    assert profile.get_synthesis_profile("voxcpm2") is not None
    assert profile.get_wakeword_profile("openwakeword") is not None
    assert profile.to_public_dict(require_prompt="missing") == {}
    dumped = profile.to_public_dict(require_prompt="system", active_id="alexa")
    assert dumped["prompt"] == "Hello"
    assert dumped["is_active"] is True
    assert dumped["is_readonly"] is True
    assert "is_default" not in dumped

    catalog = ProfileCatalog({"alexa": profile})
    assert len(catalog) == 1
    assert list(catalog) == [profile]
    assert catalog.find_by_callee("+15555550100") is profile
    assert catalog.find_by_callee("+404") is None
    assert catalog.get("missing") is None
    with pytest.raises(KeyError, match="Profile not found"):
        catalog.require("missing")
    assert catalog.collect_adapter_profiles("transcription", "parakeet") == {
        "alexa": profile.transcription.parakeet
    }
    assert catalog.collect_adapter_profiles("synthesis", "voxcpm2")
    assert catalog.collect_adapter_profiles("wakeword", "openwakeword")
    assert catalog.collect_audio_profiles("avfaudio")
    assert profile.config_path == config_path


def test_profile_loading_disabled_invalid_and_missing(tmp_path: Path):
    root = tmp_path / "alexa"
    root.mkdir()
    assert Profile.load(root, {}) is None
    ConfigFile(root / "profile.yml").write({"name": "Alexa", "disabled": True})
    assert Profile.load(root, {}) is None
    ConfigFile(root / "profile.yml").write({"name": "Alexa", "emoji": "invalid"})
    with pytest.raises(ValueError, match="Invalid profile 'alexa'"):
        Profile.load(root, {})
    assert Profile._resolve_config_path(root / "missing") == root / "missing"


def test_profile_catalog_empty_store_and_user_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resources = FileSystemResourceCatalog(tmp_path)
    assert resources.path_for("assets") == tmp_path / "assets"
    assert resources.path_for("models") == tmp_path / "models"
    assert resources.path_for("profiles") == tmp_path / "profiles"
    assert resources.path_for("assets", "alexa") == (
        tmp_path / "profiles" / "alexa" / "assets"
    )
    assert resources.path_for("models", "alexa") == (
        tmp_path / "profiles" / "alexa" / "models"
    )
    assert resources.path_for("profiles", "alexa") == (tmp_path / "profiles" / "alexa")
    assert resources.path_for("unknown") == tmp_path  # type: ignore[arg-type]

    settings = type("SettingsStub", (), {"prompts": {}})()
    with pytest.raises(RuntimeError, match="No supported profiles"):
        ProfileCatalog.load(settings, resources)  # type: ignore[arg-type]

    env_home = tmp_path / "env"
    monkeypatch.setenv("HELOMI_HOME", str(env_home))
    assert FileSystemResourceCatalog().root_path == env_home
    monkeypatch.delenv("HELOMI_HOME")
    project = tmp_path / "project"
    resources_dir = project / "resources"
    resources_dir.mkdir(parents=True)
    nested = project / "one" / "two"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert FileSystemResourceCatalog().root_path == resources_dir


@pytest.mark.parametrize("adapter", ["piper", "supertonic", "voxcpm2"])
def test_only_selected_synthesis_settings_are_validated(adapter, monkeypatch, tmp_path):
    from helomi_runtime.synthesis.config import SynthesisSettings

    resolved = []

    def resolve_model(*, repo_id, local_files_only):
        assert local_files_only
        resolved.append(repo_id)
        return str(tmp_path)

    monkeypatch.setattr(
        "helomi_foundation.validation.hf.snapshot_download", resolve_model
    )
    data = {"adapter": adapter, "piper": 42, "supertonic": 42, "voxcpm2": 42}
    data.pop(adapter)
    settings = SynthesisSettings.model_validate(data)
    assert getattr(settings, adapter) is not None
    assert all(getattr(settings, name) is None for name in data if name != "adapter")
    assert len(resolved) == (0 if adapter == "piper" else 1)


@pytest.mark.parametrize("selected", [None, {}])
def test_selected_driver_uses_defaults_and_inactive_driver_is_discarded(selected):
    settings = AudioRouterSettings.model_validate(
        {
            "initial_driver": "avfaudio",
            "drivers": ["avfaudio"],
            "avfaudio": selected,
            "twilio": {"port": "invalid"},
        }
    )
    assert settings.avfaudio.voice_processing
    assert settings.twilio is None
    assert settings.monitor_driver is None


@pytest.mark.parametrize(
    "data",
    [
        {"adapter": "unknown"},
        {"adapter": "piper", "pipre": {}},
        {"adapter": "piper", "piper": {"unknown": True}},
    ],
)
def test_adapter_selection_rejects_unknown_names_and_active_fields(data):
    from helomi_runtime.synthesis.config import SynthesisSettings

    with pytest.raises(ValidationError):
        SynthesisSettings.model_validate(data)


def test_active_twilio_requires_its_configuration():
    with pytest.raises(ValidationError, match="auth_token"):
        AudioRouterSettings.model_validate(
            {"initial_driver": "twilio", "drivers": ["twilio"]}
        )


def test_settings_prune_inactive_references_before_resolution(temp_helomi_store):
    root = temp_helomi_store
    ConfigFile(root / "settings.override.yml").write(
        {
            "audio": {
                "twilio": {
                    "auth_token": "env://HELOMI_UNUSED_TWILIO_TOKEN",
                    "public_url": "env://HELOMI_UNUSED_TWILIO_URL",
                }
            },
            "transcription": {"whisper": {"model_id": "env://HELOMI_UNUSED_MODEL"}},
            "synthesis": {"piper": {"volume": "env://HELOMI_UNUSED_VOLUME"}},
        }
    )
    settings = Settings.load(FileSystemResourceCatalog(root))
    assert settings.audio.twilio is None
    assert settings.transcription.whisper is None
    assert settings.synthesis.piper is None


def test_active_references_are_resolved_with_source_context(temp_helomi_store):
    root = temp_helomi_store
    ConfigFile(root / "settings.override.yml").write(
        {"synthesis": {"voxcpm2": {"model_id": "env://HELOMI_MISSING_ACTIVE_MODEL"}}}
    )
    with pytest.raises(ValueError) as raised:
        Settings.load(FileSystemResourceCatalog(root))
    assert "HELOMI_MISSING_ACTIVE_MODEL" in str(raised.value)
    assert "synthesis.voxcpm2.model_id" in str(raised.value)
    assert "settings.override.yml" in str(raised.value)


@pytest.mark.parametrize("synthesis", [None, {}, {"voxcpm2": None}])
def test_catalog_skips_profiles_without_active_synthesis(temp_helomi_store, synthesis):
    root = temp_helomi_store
    profile_path = root / "profiles" / "alexa" / "profile.yml"
    ConfigFile(profile_path).write(
        {
            "name": "Alexa",
            "synthesis": synthesis,
            "wakeword": {
                "openwakeword": {"model_path": "env://HELOMI_UNUSED_WAKEWORD"}
            },
        }
    )
    resources = FileSystemResourceCatalog(root)
    with pytest.raises(RuntimeError, match="No supported profiles"):
        ProfileCatalog.load(Settings.load(resources), resources)


def test_profiles_use_defaults_prune_inactive_variants_and_allow_no_wakeword(
    temp_helomi_store,
):
    root = temp_helomi_store
    ConfigFile(root / "profiles" / "defaults.yml").write(
        {"synthesis": {"voxcpm2": {}}, "audio": {"avfaudio": {}}}
    )
    ConfigFile(root / "profiles" / "alexa" / "profile.yml").write(
        {
            "name": "Alexa",
            "synthesis": {"piper": {"model_path": "env://HELOMI_UNUSED_PIPER"}},
            "transcription": {
                "whisper": {"initial_prompt": "env://HELOMI_UNUSED_PROMPT"}
            },
            "audio": {"twilio": {"callees": ["env://HELOMI_UNUSED_CALLEE"]}},
        }
    )
    resources = FileSystemResourceCatalog(root)
    catalog = ProfileCatalog.load(Settings.load(resources), resources)
    profile = catalog.require("alexa")
    assert profile.synthesis.voxcpm2 is not None
    assert profile.synthesis.piper is None
    assert profile.transcription.parakeet is not None
    assert profile.transcription.whisper is None
    assert profile.audio.avfaudio is not None
    assert profile.audio.twilio is None
    assert profile.wakeword.openwakeword is None
    assert profile.to_public_dict()["has_wakeword"] is False
    assert catalog.collect_adapter_profiles("wakeword", "openwakeword") == {}


def test_disabled_global_wakeword_drops_profile_model_references(temp_helomi_store):
    root = temp_helomi_store
    ConfigFile(root / "settings.override.yml").write({"detection": {"wakeword": None}})
    ConfigFile(root / "profiles" / "alexa" / "profile.override.yml").write(
        {"wakeword": {"openwakeword": {"model_path": "env://HELOMI_DISABLED_WAKEWORD"}}}
    )
    resources = FileSystemResourceCatalog(root)
    profile = ProfileCatalog.load(Settings.load(resources), resources).require("alexa")
    assert not profile.to_public_dict()["has_wakeword"]


def test_invalid_active_profile_configuration_is_not_silently_skipped(
    temp_helomi_store,
):
    root = temp_helomi_store
    ConfigFile(root / "profiles" / "alexa" / "profile.override.yml").write(
        {"synthesis": {"voxcpm2": {"ref_audio": "path://missing.wav"}}}
    )
    resources = FileSystemResourceCatalog(root)
    with pytest.raises(ValueError, match="Invalid profile 'alexa'"):
        ProfileCatalog.load(Settings.load(resources), resources)


def test_profile_defaults_keep_their_original_reference_directory(temp_helomi_store):
    root = temp_helomi_store
    defaults_audio = root / "profiles" / "default.wav"
    defaults_audio.touch()
    ConfigFile(root / "profiles" / "defaults.yml").write(
        {"synthesis": {"voxcpm2": {"ref_audio": "path://default.wav"}}}
    )
    resources = FileSystemResourceCatalog(root)
    catalog = ProfileCatalog.load(Settings.load(resources), resources)
    assert catalog.require("alexa").synthesis.voxcpm2.ref_audio == defaults_audio


def test_application_settings_stay_untyped_until_application_parses_them(
    temp_helomi_store,
):
    root = temp_helomi_store
    ConfigFile(root / "settings.override.yml").write({"app": {"custom_key": True}})
    settings = Settings.load(FileSystemResourceCatalog(root))
    assert settings.app == {"custom_key": True}


def test_old_application_key_has_a_migration_error(temp_helomi_store):
    root = temp_helomi_store
    ConfigFile(root / "settings.override.yml").write({"application": {}})
    with pytest.raises(ValueError, match="Rename 'application' to 'app'"):
        Settings.load(FileSystemResourceCatalog(root))


def test_selectors_can_use_environment_references(temp_helomi_store, monkeypatch):
    root = temp_helomi_store
    monkeypatch.setenv("HELOMI_SELECTED_SYNTHESIS", "piper")
    monkeypatch.setenv("HELOMI_SELECTED_DRIVER", "avfaudio")
    ConfigFile(root / "settings.override.yml").write(
        {
            "audio": {"drivers": ["env://HELOMI_SELECTED_DRIVER"]},
            "synthesis": {
                "adapter": "env://HELOMI_SELECTED_SYNTHESIS",
                "voxcpm2": {"model_id": "env://HELOMI_UNUSED_MODEL"},
            },
        }
    )
    settings = Settings.load(FileSystemResourceCatalog(root))
    assert settings.audio.avfaudio is not None
    assert settings.synthesis.piper is not None
    assert settings.synthesis.voxcpm2 is None
