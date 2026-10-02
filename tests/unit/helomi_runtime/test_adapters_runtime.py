from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from helomi_foundation import HFModel, ManagedComponent
from helomi_runtime import Runtime
from helomi_runtime.adapters import (
    create_audio_drivers,
    create_synthesis_adapter,
    create_transcription_adapter,
    create_turn_adapter,
    create_vad_adapter,
    create_wakeword_adapter,
)
from helomi_runtime.audio.avfaudio.config import AVFAudioSettings
from helomi_runtime.audio.config import AudioRouterSettings
from helomi_runtime.audio.twilio.config import TwilioSettings
from helomi_runtime.detection.config import (
    TurnSettings,
    VADOptions,
    VADSettings,
    WakeWordSettings,
)
from helomi_runtime.detection.openwakeword.config import OpenWakeWordConfig
from helomi_runtime.detection.silero_vad.config import SileroVADConfig
from helomi_runtime.detection.smart_turn.config import SmartTurnConfig
from helomi_runtime.resources import ResourceCatalog
from helomi_runtime.synthesis.config import SynthesisSettings
from helomi_runtime.synthesis.piper.config import PiperSettings
from helomi_runtime.synthesis.supertonic.config import SupertonicSettings
from helomi_runtime.synthesis.voxcpm2.config import VoxCPM2Settings
from helomi_runtime.transcription.config import (
    TranscriptionOptions,
    TranscriptionSettings,
)
from helomi_runtime.transcription.parakeet.config import ParakeetSettings
from helomi_runtime.transcription.whisper.config import WhisperSettings


def _model(tmp_path: Path) -> HFModel:
    return HFModel.model_construct(
        id="namespace/model", name="model", namespace="namespace", path=tmp_path
    )


def _runtime(settings):
    profiles = MagicMock()
    profiles.collect_adapter_profiles.return_value = {"alexa": object()}
    profiles.collect_audio_profiles.return_value = {"alexa": object()}
    return SimpleNamespace(
        settings=settings,
        profiles=profiles,
    )


def test_audio_driver_factories():
    settings = SimpleNamespace(
        audio=AudioRouterSettings(
            initial_driver="avfaudio",
            drivers=["avfaudio", "twilio"],
            avfaudio=AVFAudioSettings(),
            twilio=TwilioSettings(
                auth_token="secret", public_url="https://example.test/"
            ),
        )
    )
    runtime = _runtime(settings)
    local = object()
    remote = object()
    with (
        patch(
            "helomi_runtime.audio.avfaudio.driver.AVFAudioDriver",
            return_value=local,
        ),
        patch(
            "helomi_runtime.audio.twilio.driver.TwilioDriver",
            return_value=remote,
        ),
    ):
        drivers = create_audio_drivers(runtime)  # type: ignore[arg-type]
    assert drivers == {"avfaudio": local, "twilio": remote}
    assert runtime.profiles.collect_audio_profiles.call_count == 2


@pytest.mark.parametrize(
    ("settings", "target"),
    [
        (
            ParakeetSettings.model_construct(model=MagicMock(), language="en"),
            "helomi_runtime.transcription.parakeet.adapter.ParakeetAdapter",
        ),
        (
            WhisperSettings.model_construct(model=MagicMock(), language="en"),
            "helomi_runtime.transcription.whisper.adapter.WhisperAdapter",
        ),
    ],
)
def test_transcription_factories(settings, target):
    adapter_id = "parakeet" if isinstance(settings, ParakeetSettings) else "whisper"
    selected = TranscriptionSettings.model_construct(
        adapter=adapter_id, **{adapter_id: settings}
    )
    runtime = _runtime(SimpleNamespace(transcription=selected))
    expected = object()
    with patch(target, return_value=expected):
        assert create_transcription_adapter(runtime) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("settings", "target"),
    [
        (
            SupertonicSettings.model_construct(model=MagicMock(), language="en"),
            "helomi_runtime.synthesis.supertonic.adapter.SupertonicAdapter",
        ),
        (
            VoxCPM2Settings.model_construct(model=MagicMock(), load_denoiser=False),
            "helomi_runtime.synthesis.voxcpm2.adapter.VoxCPM2Adapter",
        ),
        (
            PiperSettings(),
            "helomi_runtime.synthesis.piper.adapter.PiperAdapter",
        ),
    ],
)
def test_synthesis_factories(settings, target):
    adapter_id = (
        "supertonic"
        if isinstance(settings, SupertonicSettings)
        else "voxcpm2"
        if isinstance(settings, VoxCPM2Settings)
        else "piper"
    )
    selected = SynthesisSettings.model_construct(
        adapter=adapter_id, **{adapter_id: settings}
    )
    runtime = _runtime(SimpleNamespace(synthesis=selected))
    expected = object()
    with patch(target, return_value=expected):
        assert create_synthesis_adapter(runtime) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("adapter_path", "settings", "mount_hook", "unmount_hook"),
    [
        (
            "helomi_runtime.transcription.parakeet.adapter.ParakeetAdapter",
            ParakeetSettings.model_construct(model=MagicMock(), language="en"),
            "_load_model",
            "_release_model",
        ),
        (
            "helomi_runtime.transcription.whisper.adapter.WhisperAdapter",
            WhisperSettings.model_construct(model=MagicMock(), language="en"),
            "_prepare_model",
            None,
        ),
        (
            "helomi_runtime.synthesis.supertonic.adapter.SupertonicAdapter",
            SupertonicSettings.model_construct(model=MagicMock(), language="en"),
            "_load_model",
            "_release_model",
        ),
        (
            "helomi_runtime.synthesis.voxcpm2.adapter.VoxCPM2Adapter",
            VoxCPM2Settings.model_construct(model=MagicMock(), load_denoiser=False),
            "_load_model",
            "_release_model",
        ),
        (
            "helomi_runtime.synthesis.piper.adapter.PiperAdapter",
            PiperSettings(),
            "_load_models",
            "_release_models",
        ),
    ],
)
def test_synchronous_adapter_lifecycle_hooks(
    adapter_path,
    settings,
    mount_hook,
    unmount_hook,
):
    module_path, class_name = adapter_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    adapter_type = getattr(module, class_name)
    adapter = (
        adapter_type(settings, {}, TranscriptionOptions())
        if isinstance(settings, (ParakeetSettings, WhisperSettings))
        else adapter_type(settings, {})
    )
    mounted = MagicMock()
    setattr(adapter, mount_hook, mounted)
    unmounted = MagicMock()
    if unmount_hook is not None:
        setattr(adapter, unmount_hook, unmounted)

    adapter.mount()
    assert adapter.is_mounted
    mounted.assert_called_once_with()
    adapter.unmount()
    assert not adapter.is_mounted
    if unmount_hook is not None:
        unmounted.assert_called_once_with()


def test_detection_factories(tmp_path: Path):
    model = _model(tmp_path)
    settings = SimpleNamespace(
        detection=SimpleNamespace(
            turn=TurnSettings.model_construct(
                adapter="smart_turn",
                smart_turn=SmartTurnConfig.model_construct(model=model),
            ),
            vad=VADSettings.model_construct(
                adapter="silero_vad",
                silero_vad=SileroVADConfig.model_construct(model=model),
                options=VADOptions(),
            ),
            wakeword=None,
        )
    )
    runtime = _runtime(settings)
    with (
        patch("helomi_runtime.detection.smart_turn.adapter.SmartTurnAdapter") as turn,
        patch("helomi_runtime.detection.silero_vad.adapter.SileroVADAdapter") as vad,
    ):
        assert create_turn_adapter(runtime) is turn.return_value  # type: ignore[arg-type]
        assert create_vad_adapter(runtime) is vad.return_value  # type: ignore[arg-type]
    assert create_wakeword_adapter(runtime) is None  # type: ignore[arg-type]

    model_path = tmp_path / "model.onnx"
    model_path.touch()
    settings.detection.wakeword = WakeWordSettings.model_construct(
        adapter="openwakeword",
        openwakeword=OpenWakeWordConfig.model_construct(
            embedding_path=model_path,
            melspec_path=model_path,
            threshold=0.5,
            patience=1,
            frame_size=1280,
        ),
    )
    runtime.profiles.collect_adapter_profiles.return_value = {}
    assert create_wakeword_adapter(runtime) is None  # type: ignore[arg-type]
    runtime.profiles.collect_adapter_profiles.return_value = {"alexa": object()}
    with patch(
        "helomi_runtime.detection.openwakeword.adapter.OpenWakeWordAdapter"
    ) as wakeword:
        assert create_wakeword_adapter(runtime) is wakeword.return_value  # type: ignore[arg-type]


class DummyComponent(ManagedComponent):
    pass


@pytest.mark.asyncio
async def test_runtime_lazy_composition_and_cache(tmp_path: Path):
    resources = MagicMock(spec=ResourceCatalog)
    settings = MagicMock()
    settings.synthesis.adapter = "voxcpm2"
    settings.synthesis.model_dump_json.return_value = "{}"
    profiles = MagicMock()
    runtime = Runtime(resources)
    with (
        patch("helomi_runtime.runtime.Settings.load", return_value=settings) as load,
        patch(
            "helomi_runtime.runtime.ProfileCatalog.load", return_value=profiles
        ) as load_profiles,
    ):
        assert runtime.resources is resources
        assert runtime.settings is runtime.settings is settings
        assert runtime.profiles is runtime.profiles is profiles
    load.assert_called_once()
    load_profiles.assert_called_once()

    with pytest.raises(RuntimeError, match="not mounted"):
        await runtime.get_synthesis_worker()

    audio = DummyComponent()
    detection = DummyComponent()
    stt = DummyComponent()
    tts = DummyComponent()
    reaction = DummyComponent()
    with (
        patch("helomi_runtime.runtime.AudioRouter", return_value=audio),
        patch("helomi_runtime.runtime.DetectionWorker", return_value=detection),
        patch("helomi_runtime.runtime.TranscriptionWorker", return_value=stt),
        patch("helomi_runtime.runtime.SynthesisWorker", return_value=tts),
        patch("helomi_runtime.runtime.ReactionCatalog", return_value=reaction),
        patch("helomi_runtime.runtime.create_audio_drivers", return_value={}),
        patch("helomi_runtime.runtime.create_turn_adapter"),
        patch("helomi_runtime.runtime.create_vad_adapter"),
        patch("helomi_runtime.runtime.create_wakeword_adapter"),
        patch("helomi_runtime.runtime.create_transcription_adapter"),
        patch("helomi_runtime.runtime.create_synthesis_adapter"),
    ):
        async with runtime:
            assert await runtime.get_audio_router() is audio
            assert await runtime.get_detection_worker() is detection
            assert await runtime.get_transcription_worker() is stt
            assert await runtime.get_synthesis_worker() is tts
            assert await runtime.get_synthesis_worker() is tts
            assert await runtime.get_reaction_catalog() is reaction
            assert runtime._components
    assert not runtime._components


def test_runtime_accepts_path(tmp_path: Path):
    runtime = Runtime(tmp_path)
    assert runtime.resources.root_path == tmp_path
