import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

import helomi.resources.local as local_module
from helomi.conversation.profile import McpConfiguration
from helomi.resources import LocalStore, Settings, TextFileCatalog
from helomi.resources.profiles import Profile


def write_profile(root: Path, name: str = "helomi") -> Path:
    (root / "settings.yml").write_text("language: en-US\n", encoding="utf-8")
    locale = root / "locales" / "en-US"
    (locale / "settings.yml").parent.mkdir(parents=True, exist_ok=True)
    (locale / "settings.yml").write_text("{}\n", encoding="utf-8")
    profile = locale / "profiles" / name
    prompts = profile / "prompts"
    reactions = profile / "reactions"
    prompts.mkdir(parents=True)
    reactions.mkdir()
    (profile / "profile.yml").write_text(
        """
name: Henry
conversation:
  models:
    fast:
      model_id: ollama:gpt-oss:20b
    detailed:
      model_id: ollama:gpt-oss:20b
  recent_messages: 6
wakeword:
  label: Wakeword
  model_path: wakeword.onnx
tts:
  model_path: voice.onnx
stt:
  model_id: profile/stt
""".strip(),
        encoding="utf-8",
    )
    (prompts / "system.md").write_text(
        "System Polish {conversation_summary}", encoding="utf-8"
    )
    (prompts / "opening.md").write_text(
        "Open Polish {conversation_summary} {recent_conversation}",
        encoding="utf-8",
    )
    (prompts / "summary.md").write_text(
        "Summarize {conversation_summary} {recent_conversation}",
        encoding="utf-8",
    )
    (reactions / "wake.txt").write_text("Tak, słucham.\nJestem.\n", encoding="utf-8")
    (reactions / "wait.txt").write_text(
        "Chwileczkę.\nJuż sprawdzam.\n", encoding="utf-8"
    )
    (reactions / "background.txt").write_text("Sprawdzam.\n", encoding="utf-8")
    (reactions / "quit.txt").write_text("Do usłyszenia.\n", encoding="utf-8")
    return profile


def write_settings(root: Path) -> None:
    (root / "settings.yml").write_text(
        "language: en-US\n",
        encoding="utf-8",
    )
    (root / "locales" / "en-US" / "settings.yml").write_text(
        "profiles:\n  default: second\n",
        encoding="utf-8",
    )
    (root / "settings.override.yml").write_text(
        """
conversation:
  language_model:
    adapter: langchain
    base_url: http://models.local:11434
speech:
  audio:
    driver: pyaudio
""".strip(),
        encoding="utf-8",
    )


def test_local_store_loads_profile_settings_and_models(tmp_path: Path) -> None:
    profile_path = write_profile(tmp_path)
    write_profile(tmp_path, "second")
    write_settings(tmp_path)
    model_path = tmp_path / "models" / "nested" / "model.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"model")

    store = LocalStore(tmp_path)
    profile = store.load_profile("helomi")

    assert profile.id == "helomi"
    assert profile.path == profile_path
    assert profile.name == "Henry"
    assert profile.wakeword.label == "Wakeword"
    assert profile.stt == {"model_id": "profile/stt"}
    assert profile.conversation.recent_messages == 6
    assert profile.conversation.prompts.system.startswith("System")
    assert profile.conversation.reactions.wake == ("Tak, słucham.", "Jestem.")
    assert "id" not in profile.model_dump()
    assert [item.id for item in store.list_profiles()] == ["helomi", "second"]
    inspected = store.inspect_profiles()
    assert [item.id for item in inspected] == ["helomi", "second"]
    assert all(item.is_valid for item in inspected)
    settings = store.load_settings()
    assert settings.conversation.language_model.adapter == "langchain"
    assert settings.conversation.language_model.base_url == "http://models.local:11434"
    assert settings.speech.audio.driver == "pyaudio"
    assert settings.profiles.selected is None
    assert store.load_default_profile().id == "second"
    assert store.ensure_model_path("nested", "model.onnx") == model_path


def test_profile_can_omit_wakeword_for_always_listening_mode(tmp_path: Path) -> None:
    profile_path = write_profile(tmp_path)
    profile_file = profile_path / "profile.yml"
    profile_file.write_text(
        profile_file.read_text(encoding="utf-8").replace(
            "wakeword:\n  label: Wakeword\n  model_path: wakeword.onnx\n", ""
        ),
        encoding="utf-8",
    )

    profile = LocalStore(tmp_path).load_profile("helomi")

    assert profile.wakeword is None
    entry = LocalStore(tmp_path).inspect_profiles()[0]
    assert entry.is_valid


def test_local_store_merges_locale_and_profile_overrides(tmp_path: Path) -> None:
    profile_path = write_profile(tmp_path)
    (tmp_path / "settings.override.yml").write_text(
        "conversation:\n  acknowledgement_delay: 0.4\n",
        encoding="utf-8",
    )
    locale_settings = tmp_path / "locales" / "en-US" / "settings.yml"
    locale_settings.write_text(
        "conversation:\n  acknowledgement_delay: 0.6\n",
        encoding="utf-8",
    )
    (locale_settings.with_name("settings.override.yml")).write_text(
        "conversation:\n  acknowledgement_delay: 1.0\n",
        encoding="utf-8",
    )
    (profile_path / "profile.override.yml").write_text(
        """
conversation:
  models:
    fast:
      max_tokens: 99
wakeword: null
""".strip(),
        encoding="utf-8",
    )

    store = LocalStore(tmp_path, selected_profile="helomi")
    settings = store.load_settings()
    profile = store.load_profile("helomi")

    assert settings.conversation.acknowledgement_delay == 1.0
    assert settings.profiles.selected == "helomi"
    assert profile.conversation.models_mlx.fast.max_tokens == 99
    assert profile.wakeword is None


def test_local_store_loads_locale_stt_language_override(tmp_path: Path) -> None:
    write_profile(tmp_path)
    (tmp_path / "settings.yml").write_text(
        "language: en-US\nspeech:\n  stt:\n    adapter: mlx:parakeet-tdt\n",
        encoding="utf-8",
    )
    locale_settings = tmp_path / "locales" / "en-US" / "settings.yml"
    locale_settings.write_text(
        "speech:\n  stt:\n    language: pl\n",
        encoding="utf-8",
    )

    settings = LocalStore(tmp_path).load_settings()

    assert settings.speech.stt.language == "pl"


def test_local_store_rejects_language_in_locale_settings(tmp_path: Path) -> None:
    write_profile(tmp_path)
    (tmp_path / "locales" / "en-US" / "settings.yml").write_text(
        "language: pl-PL\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not define language"):
        LocalStore(tmp_path).load_settings()


def test_profile_override_rejects_non_mapping_conversation(tmp_path: Path) -> None:
    profile_path = write_profile(tmp_path)
    (profile_path / "profile.override.yml").write_text(
        "conversation: invalid\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conversation configuration"):
        Profile.load_from_directory(profile_path)


def test_local_store_reports_missing_or_unsafe_locale_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="Settings file does not exist"):
        LocalStore(tmp_path).load_settings()

    (tmp_path / "settings.yml").write_text("language: en-US\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Locale settings file does not exist"):
        LocalStore(tmp_path).load_settings()

    (tmp_path / "settings.yml").write_text("language: ../private\n", encoding="utf-8")
    with pytest.raises(ValueError, match="locale directory name"):
        LocalStore(tmp_path).load_settings()

    (tmp_path / "settings.yml").write_text("language: .\n", encoding="utf-8")
    with pytest.raises(ValueError, match="locale directory name"):
        LocalStore(tmp_path).load_settings()


def test_local_store_reports_missing_resources(tmp_path: Path) -> None:
    (tmp_path / "settings.yml").write_text("language: en-US\n", encoding="utf-8")
    (tmp_path / "locales" / "en-US" / "settings.yml").parent.mkdir(parents=True)
    (tmp_path / "locales" / "en-US" / "settings.yml").write_text(
        "{}\n", encoding="utf-8"
    )
    store = LocalStore(tmp_path)
    with pytest.raises(FileNotFoundError, match="Model file does not exist"):
        store.ensure_model_path("missing")
    with pytest.raises(FileNotFoundError, match="Profile directory does not exist"):
        store.load_profile("missing")
    with pytest.raises(FileNotFoundError, match="Profiles directory does not exist"):
        store.list_profiles()
    assert store.inspect_profiles() == []
    assert store.load_settings().language == "en-US"


def test_profile_requires_fixed_prompt_files_and_valid_configuration(
    tmp_path: Path,
) -> None:
    profile_path = write_profile(tmp_path)
    (profile_path / "prompts" / "opening.md").unlink()
    with pytest.raises(FileNotFoundError, match=r"opening\.md"):
        Profile.load_from_directory(profile_path)

    (profile_path / "prompts" / "opening.md").write_text("open", encoding="utf-8")
    (profile_path / "reactions" / "wait.txt").unlink()
    with pytest.raises(FileNotFoundError, match=r"wait\.txt"):
        Profile.load_from_directory(profile_path)

    (profile_path / "reactions" / "wait.txt").write_text("wait", encoding="utf-8")
    (profile_path / "profile.yml").write_text("name: Henry\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        Profile.load_from_directory(profile_path)


def test_store_root_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HELOMI_HOME", str(home))
    assert LocalStore()._root_path == home

    monkeypatch.delenv("HELOMI_HOME")
    project = tmp_path / "project"
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    local = project / ".helomi"
    local.mkdir()
    monkeypatch.chdir(nested)
    assert LocalStore()._root_path == local

    local.rmdir()
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(local_module, "user_data_dir", lambda _: str(fallback))
    assert LocalStore()._root_path == fallback


def test_profile_inspection_keeps_invalid_profiles_visible(tmp_path: Path) -> None:
    valid = write_profile(tmp_path)
    invalid = write_profile(tmp_path, "invalid")
    (invalid / "prompts" / "system.md").unlink()
    missing = tmp_path / "locales" / "en-US" / "profiles" / "missing"
    missing.mkdir()
    malformed = tmp_path / "locales" / "en-US" / "profiles" / "malformed"
    malformed.mkdir()
    (malformed / "profile.yml").write_text("name: [", encoding="utf-8")
    blank = tmp_path / "locales" / "en-US" / "profiles" / "blank"
    blank.mkdir()
    (blank / "profile.yml").write_text("name: '   '", encoding="utf-8")
    scalar = tmp_path / "locales" / "en-US" / "profiles" / "scalar"
    scalar.mkdir()
    (scalar / "profile.yml").write_text("profile", encoding="utf-8")

    entries = {entry.id: entry for entry in LocalStore(tmp_path).inspect_profiles()}
    assert entries[valid.name].is_valid
    assert entries["invalid"].name == "Henry"
    assert "system.md" in entries["invalid"].error
    assert entries["missing"].name == "missing"
    assert entries["malformed"].name == "malformed"
    assert entries["blank"].name == "blank"
    assert entries["scalar"].name == "scalar"


def test_settings_and_profile_validation(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.override.yml"
    settings_path.write_text("unknown: true\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        Settings.load_from_file(settings_path)

    settings_path.write_text(
        "conversation:\n  adapter: mlx\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="adapter"):
        Settings.load_from_file(settings_path)

    settings_path.write_text(
        "conversation:\n  model:\n    adapter: mlx\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match=r"conversation\.model"):
        Settings.load_from_file(settings_path)

    profile_path = write_profile(tmp_path)
    profile_file = profile_path / "profile.yml"
    profile_file.write_text(
        profile_file.read_text(encoding="utf-8").replace(
            "wakeword.onnx", "wakeword.bin"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="ONNX"):
        Profile.load_from_directory(profile_path)


def test_default_profile_falls_back_to_first_valid_profile(tmp_path: Path) -> None:
    write_profile(tmp_path, "zeta")
    write_profile(tmp_path, "alpha")
    (tmp_path / "settings.yml").write_text(
        "language: en-US\n",
        encoding="utf-8",
    )
    (tmp_path / "locales" / "en-US" / "settings.yml").write_text(
        "profiles:\n  default: missing\n",
        encoding="utf-8",
    )

    assert LocalStore(tmp_path).load_default_profile().id == "alpha"


def test_default_profile_requires_a_valid_profile(tmp_path: Path) -> None:
    (tmp_path / "settings.yml").write_text("language: en-US\n", encoding="utf-8")
    (tmp_path / "locales" / "en-US" / "settings.yml").parent.mkdir(parents=True)
    (tmp_path / "locales" / "en-US" / "settings.yml").write_text(
        "{}\n", encoding="utf-8"
    )

    with pytest.raises(FileNotFoundError, match="No valid profiles"):
        LocalStore(tmp_path).load_default_profile()


def test_default_profile_uses_first_valid_profile_without_configuration(
    tmp_path: Path,
) -> None:
    write_profile(tmp_path, "alpha")
    (tmp_path / "settings.yml").write_text("language: en-US\n", encoding="utf-8")
    (tmp_path / "locales" / "en-US" / "settings.yml").write_text(
        "{}\n", encoding="utf-8"
    )

    assert LocalStore(tmp_path).load_default_profile().id == "alpha"


def test_settings_rejects_non_mapping_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.yml"
    path.write_text("- invalid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        Settings.load_from_file(path)


def test_settings_override_can_add_a_scalar_value(tmp_path: Path) -> None:
    default = tmp_path / "settings.yml"
    override = tmp_path / "settings.override.yml"
    default.write_text("{}\n", encoding="utf-8")
    override.write_text(
        "profiles:\n  default: alexa\n  selected: henry\n", encoding="utf-8"
    )

    settings = Settings.load_from_files(default, override)
    assert settings.profiles.default == "alexa"
    assert settings.profiles.selected == "henry"


def test_settings_override_merges_nested_sections(tmp_path: Path) -> None:
    default = tmp_path / "settings.yml"
    override = tmp_path / "settings.override.yml"
    default.write_text(
        "conversation:\n  acknowledgement_delay: 0.5\n",
        encoding="utf-8",
    )
    override.write_text(
        "conversation:\n  acknowledgement_delay: 1.0\n",
        encoding="utf-8",
    )

    settings = Settings.load_from_files(default, override)
    assert settings.conversation.acknowledgement_delay == 1.0


def test_settings_normalizes_legacy_classifier_and_supports_no_override(
    tmp_path: Path,
) -> None:
    default = tmp_path / "settings.yml"
    default.write_text(
        "conversation:\n  classify_ambiguous: true\n",
        encoding="utf-8",
    )

    settings = Settings.load_from_files(default)

    assert settings.conversation.acknowledgement_delay == 0.8


def test_versioned_default_profile_is_valid() -> None:
    root = Path(__file__).parents[3] / ".helomi"
    alexa_path = root / "locales" / "en-US" / "profiles" / "alexa"
    alexa = Profile.load_from_directory(alexa_path)

    assert alexa.name == "Alexa"
    assert LocalStore(root, language="en-US").load_default_profile().id == "alexa"
    assert alexa.conversation.prompts.system
    assert alexa.conversation.models_mlx.fast.model_id
    assert alexa.conversation.models_mlx.detailed.model_id
    assert alexa.conversation.reactions.wake
    assert alexa.conversation.reactions.wait


def test_versioned_settings_list_all_defaults() -> None:
    path = Path(__file__).parents[3] / ".helomi" / "settings.yml"

    settings = Settings.load_from_file(path)
    assert settings.language == "en-US"
    assert settings.profiles.default is None
    assert settings.profiles.selected is None


def test_versioned_reactions_are_short_and_complete() -> None:
    root = Path(__file__).parents[3] / ".helomi" / "locales"
    for reaction_path in root.glob("*/profiles/*/reactions/*.txt"):
        lines = tuple(
            line.strip()
            for line in reaction_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        assert len(lines) >= 20, reaction_path
        assert len(set(lines)) == len(lines), reaction_path
        if reaction_path.name == "wait.txt":
            assert all(len(line.replace(",", "").split()) <= 4 for line in lines)


def test_mcp_profile_configuration_discriminates_transports() -> None:
    configuration = McpConfiguration.model_validate(
        {
            "endpoints": [
                {
                    "id": "remote",
                    "transport": "streamable_http",
                    "url": "https://example.test/mcp",
                    "headers_from_env": {"Authorization": "HELOMI_TOKEN"},
                },
                {
                    "id": "local",
                    "transport": "stdio",
                    "command": "uvx",
                    "args": ["example"],
                    "mode": "background",
                },
            ]
        }
    )
    assert [endpoint.id for endpoint in configuration.endpoints] == ["remote", "local"]
    with pytest.raises(ValidationError, match="unique"):
        McpConfiguration.model_validate(
            {
                "endpoints": [
                    {
                        "id": "same",
                        "transport": "stdio",
                        "command": "one",
                    },
                    {
                        "id": "same",
                        "transport": "stdio",
                        "command": "two",
                    },
                ]
            }
        )


def test_text_file_catalog_contains_paths_and_enforces_write_modes(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        catalog = TextFileCatalog(tmp_path / "data")
        await catalog.start()
        try:
            catalog.write("notes/today.txt", "hello", mode="create")
            assert catalog.list() == ("notes/today.txt",)
            assert catalog.read("notes/today.txt") == "hello"
            with pytest.raises(FileExistsError):
                catalog.write("notes/today.txt", "again", mode="create")
            catalog.write("notes/today.txt", "again", mode="replace")
            assert catalog.read("notes/today.txt") == "again"
            with pytest.raises(ValueError, match=r"relative .txt"):
                catalog.read("/tmp/outside.txt")
            with pytest.raises(ValueError, match="stay inside"):
                catalog.read("../outside.txt")
        finally:
            await catalog.stop()

    asyncio.run(scenario())
