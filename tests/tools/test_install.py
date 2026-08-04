from pathlib import Path

import pytest

from tools.install import cli as install_module

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_install_prepares_default_data_and_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshots: list[str] = []
    files: list[tuple[str, str]] = []

    def fake_retrieve(_url: str, destination: Path):
        Path(destination).write_bytes(b"openwakeword")
        return str(destination), None

    monkeypatch.setattr(install_module, "urlretrieve", fake_retrieve)
    monkeypatch.setattr(
        install_module,
        "snapshot_download",
        lambda *, repo_id: snapshots.append(repo_id),
    )
    monkeypatch.setattr(
        install_module,
        "hf_hub_download",
        lambda *, repo_id, filename: files.append((repo_id, filename)),
    )

    data_root = install_module.install(REPOSITORY_ROOT, tmp_path / ".helomi")

    assert (data_root / "settings.yml").read_text() == (
        REPOSITORY_ROOT / ".helomi" / "settings.yml"
    ).read_text()
    assert (
        data_root
        / "locales"
        / "en-US"
        / "profiles"
        / "alexa"
        / "prompts"
        / "system.md"
    ).is_file()
    assert {path.name for path in (data_root / "models").iterdir()} == {
        "alexa_v0.1.onnx",
        "embedding_model.onnx",
        "melspectrogram.onnx",
        "silero_vad.onnx",
    }
    assert snapshots == [
        "mlx-community/gemma-4-26b-a4b-it-4bit",
        "mlx-community/silero-vad",
        "mlx-community/parakeet-tdt-0.6b-v3",
    ]
    assert files == [
        (
            "rhasspy/piper-voices",
            "en/en_US/amy/medium/en_US-amy-medium.onnx",
        ),
        (
            "rhasspy/piper-voices",
            "en/en_US/amy/medium/en_US-amy-medium.onnx.json",
        ),
    ]


def test_install_preserves_existing_local_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    downloads = 0

    def fake_retrieve(_url: str, destination: Path):
        nonlocal downloads
        downloads += 1
        Path(destination).write_bytes(b"openwakeword")
        return str(destination), None

    monkeypatch.setattr(install_module, "urlretrieve", fake_retrieve)
    monkeypatch.setattr(install_module, "snapshot_download", lambda **_: None)
    monkeypatch.setattr(install_module, "hf_hub_download", lambda **_: None)

    data_root = install_module.install(REPOSITORY_ROOT, tmp_path / ".helomi")
    system_prompt = (
        data_root
        / "locales"
        / "en-US"
        / "profiles"
        / "alexa"
        / "prompts"
        / "system.md"
    )
    wakeword = data_root / "models" / "alexa_v0.1.onnx"
    system_prompt.write_text("Local prompt", encoding="utf-8")
    wakeword.write_bytes(b"local model")

    install_module.install(REPOSITORY_ROOT, data_root)

    assert system_prompt.read_text(encoding="utf-8") == "Local prompt"
    assert wakeword.read_bytes() == b"local model"
    assert downloads == 4


def test_failed_openwakeword_download_leaves_no_partial_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "model.onnx"

    def fail(_url: str, temporary: Path):
        Path(temporary).write_bytes(b"partial")
        raise OSError("download failed")

    monkeypatch.setattr(install_module, "urlretrieve", fail)

    with pytest.raises(OSError, match="download failed"):
        install_module._download_openwakeword_file("https://example.test", destination)

    assert not destination.exists()


def test_install_uses_helomi_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "custom-home"
    monkeypatch.setenv("HELOMI_HOME", str(home))
    monkeypatch.setattr(
        install_module,
        "_install_local_data",
        lambda repository_root, data_root: data_root.mkdir(parents=True),
    )
    monkeypatch.setattr(install_module.LocalStore, "load_settings", lambda _: object())
    monkeypatch.setattr(
        install_module.LocalStore,
        "load_default_profile",
        lambda *_: object(),
    )
    monkeypatch.setattr(install_module, "_install_openwakeword_models", lambda _: None)
    monkeypatch.setattr(
        install_module,
        "_download_hugging_face_models",
        lambda *_: None,
    )

    assert install_module.install(REPOSITORY_ROOT) == home


def test_main_uses_repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    monkeypatch.setattr(install_module, "install", lambda root: roots.append(root))

    install_module.main()

    assert roots == [REPOSITORY_ROOT]
