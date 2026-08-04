import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlretrieve

from huggingface_hub import hf_hub_download, snapshot_download

from helomi.conversation.model.config import LangChainSettings, MLXSettings
from helomi.resources import LocalStore, Profile, Settings
from helomi.speech.capture.config import MLX_SILERO_VAD_MODEL_ID
from helomi.speech.synthesis.config import MLXChatterboxSettings, PiperSettings
from helomi.speech.transcription.config import (
    MLXParakeetTDTSettings,
    MLXQwen3ASRSettings,
    MLXWhisperSettings,
)

_OPENWAKEWORD_RELEASE_URL = (
    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
)
_OPENWAKEWORD_FILES = (
    "embedding_model.onnx",
    "alexa_v0.1.onnx",
    "melspectrogram.onnx",
    "silero_vad.onnx",
)


def _exists(path: Path) -> bool:
    return os.path.lexists(path)


def _install_file(
    destination: Path,
    writer: Callable[[Path], None],
) -> bool:
    if _exists(destination):
        print(f"Already exists: {destination}")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)

    try:
        writer(temporary)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            print(f"Already exists: {destination}")
            return False
    finally:
        temporary.unlink(missing_ok=True)

    print(f"Installed: {destination}")
    return True


def _copy_file(source: Path, destination: Path) -> None:
    def copy(temporary: Path) -> None:
        shutil.copy2(source, temporary)

    _install_file(destination, copy)


def _copy_directory(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not path.name.endswith(".override.yml"):
            _copy_file(path, destination / relative)


def _download_openwakeword_file(url: str, destination: Path) -> None:
    def download(temporary: Path) -> None:
        urlretrieve(url, temporary)

    _install_file(destination, download)


def _install_local_data(repository_root: Path, data_root: Path) -> None:
    source = repository_root / ".helomi"
    _copy_file(source / "settings.yml", data_root / "settings.yml")
    locales = source / "locales"
    locale_directories = sorted(
        directory for directory in locales.iterdir() if directory.is_dir()
    )
    for locale in locale_directories:
        destination = data_root / "locales" / locale.name
        _copy_file(locale / "settings.yml", destination / "settings.yml")
        source_profiles = locale / "profiles"
        destination_profiles = destination / "profiles"
        _copy_file(source_profiles / ".gitignore", destination_profiles / ".gitignore")
        for profile_id in _profile_allowlist(source_profiles / ".gitignore"):
            _copy_directory(
                source_profiles / profile_id,
                destination_profiles / profile_id,
            )


def _profile_allowlist(path: Path) -> tuple[str, ...]:
    return tuple(
        line[1:].rstrip("/")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("!") and line not in {"!.gitignore", "!"}
    )


def _install_openwakeword_models(data_root: Path) -> None:
    destination = data_root / "models"
    for filename in _OPENWAKEWORD_FILES:
        _download_openwakeword_file(
            f"{_OPENWAKEWORD_RELEASE_URL}/{filename}",
            destination / filename,
        )


def _conversation_models(profile: Profile, settings: Settings) -> tuple[str, ...]:
    match settings.conversation.language_model:
        case MLXSettings():
            models = profile.conversation.models_mlx
            selected = [models.fast.model_id, models.detailed.model_id]
            if models.classifier is None:
                raise ValueError("Natural conversation requires a classifier model")
            selected.append(models.classifier.model_id)
            return tuple(selected)
        case LangChainSettings():
            models = profile.conversation.models_langchain
            if models.classifier is None:
                raise ValueError("Natural conversation requires a classifier model")
            return ()


def _stt_model(profile: Profile, settings: Settings) -> str:
    selected = settings.speech.stt
    match selected:
        case MLXParakeetTDTSettings():
            configured = profile.stt_mlx_parakeet_tdt.model_id
        case MLXQwen3ASRSettings():
            configured = profile.stt_mlx_qwen3_asr.model_id
        case MLXWhisperSettings():
            configured = profile.stt_mlx_whisper.model_id
    return configured or selected.model_id


def _tts_models(
    profile: Profile,
    settings: Settings,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    selected = settings.speech.tts
    match selected:
        case PiperSettings():
            configured = profile.tts_piper
            repository = configured.repo_id or selected.repo_id
            filename = configured.model_path
            return (), ((repository, filename), (repository, filename + ".json"))
        case MLXChatterboxSettings():
            configured = profile.tts_mlx_chatterbox
            return (configured.model_id or selected.model_id,), ()


def _hugging_face_models(
    profile: Profile,
    settings: Settings,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    repositories = list(_conversation_models(profile, settings))
    if settings.speech.vad.adapter == "mlx:silero_vad":
        repositories.append(MLX_SILERO_VAD_MODEL_ID)
    repositories.append(_stt_model(profile, settings))
    tts_repositories, files = _tts_models(profile, settings)
    repositories.extend(tts_repositories)
    return tuple(dict.fromkeys(repositories)), tuple(dict.fromkeys(files))


def _download_hugging_face_models(profile: Profile, settings: Settings) -> None:
    repositories, files = _hugging_face_models(profile, settings)
    for repository in repositories:
        if Path(repository).expanduser().exists():
            print(f"Local model exists: {repository}")
            continue
        print(f"Downloading Hugging Face model: {repository}")
        snapshot_download(repo_id=repository)

    for repository, filename in files:
        print(f"Downloading Hugging Face file: {repository}/{filename}")
        hf_hub_download(repo_id=repository, filename=filename)


def install(
    repository_root: Path,
    data_root: Path | None = None,
) -> Path:
    repository_root = repository_root.resolve()
    if data_root is None:
        configured_root = os.getenv("HELOMI_HOME")
        data_root = (
            Path(configured_root).expanduser()
            if configured_root
            else repository_root / ".helomi"
        )
    data_root = data_root.resolve()

    print(f"Initializing Helomi data: {data_root}")
    _install_local_data(repository_root, data_root)

    store = LocalStore(data_root)
    settings = store.load_settings()
    profile = store.load_default_profile()

    _install_openwakeword_models(data_root)
    _download_hugging_face_models(profile, settings)
    print(f"Helomi is ready: {data_root}")
    return data_root


def main() -> None:
    install(Path(__file__).parents[2])


if __name__ == "__main__":
    main()
