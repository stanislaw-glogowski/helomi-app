import hashlib
from pathlib import Path

import pytest

from helomi_runtime.audio import AudioChunk
from helomi_runtime.config import Profile, ProfileCatalog
from helomi_runtime.reaction import ReactionCatalog, ReactionKind
from helomi_runtime.synthesis import SynthesisChunk, SynthesisRequest, SynthesisWorker
from helomi_runtime.transcription import (
    TranscriptionChunk,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptionWorker,
)
from tests.fixtures.audio import create_raw_audio
from tests.fixtures.mocks import MockSynthesisAdapter, MockTranscriptionAdapter


async def test_transcription_and_synthesis_workers_stream_and_propagate_errors():
    raw = create_raw_audio(num_samples=320)
    transcription_adapter = MockTranscriptionAdapter(
        chunks=[TranscriptionChunk("hello"), TranscriptionChunk("world")]
    )
    synthesis_adapter = MockSynthesisAdapter(
        chunks=[SynthesisChunk(raw), SynthesisChunk(raw)]
    )
    stt = TranscriptionWorker(transcription_adapter)
    tts = SynthesisWorker(synthesis_adapter)
    async with stt, tts:
        stt_results = [
            item
            async for item in stt.transcribe(
                TranscriptionRequest(AudioChunk.from_raw(raw), "alexa")
            )
        ]
        assert [item.text for item in stt_results] == [
            "hello",
            "world",
            "hello world",
        ]
        assert isinstance(stt_results[-1], TranscriptionResponse)
        tts_results = [
            item async for item in tts.synthesize(SynthesisRequest("Hello", "alexa"))
        ]
        assert len(tts_results) == 2
    assert not transcription_adapter.is_mounted and not synthesis_adapter.is_mounted

    async with TranscriptionWorker(
        MockTranscriptionAdapter(chunks=[RuntimeError("stt failed")])
    ) as worker:
        with pytest.raises(RuntimeError, match="stt failed"):
            _ = [
                item
                async for item in worker.transcribe(
                    TranscriptionRequest(AudioChunk.from_raw(raw), "alexa")
                )
            ]
    async with SynthesisWorker(
        MockSynthesisAdapter(chunks=[RuntimeError("tts failed")])
    ) as worker:
        with pytest.raises(RuntimeError, match="tts failed"):
            _ = [
                item
                async for item in worker.synthesize(SynthesisRequest("Hello", "alexa"))
            ]


def _profile(tmp_path: Path, reactions) -> Profile:
    return Profile.model_validate(
        {
            "name": "Alexa",
            "reactions": reactions,
            "synthesis": {"voxcpm2": {}},
            "transcription": {"parakeet": {}},
        },
        context={
            "id": "alexa",
            "config_path": tmp_path / "profile.yml",
            "root_path": tmp_path,
            "prompts": {},
        },
    )


async def test_reaction_catalog_synthesizes_and_reuses_cache(
    tmp_path: Path,
):
    raw = create_raw_audio(num_samples=320)
    profile = _profile(
        tmp_path,
        {
            "greeting": ["Hello", "Welcome"],
            "farewell": None,
        },
    )
    adapter = MockSynthesisAdapter(chunks=[SynthesisChunk(raw)])
    worker = SynthesisWorker(adapter)
    catalog = ReactionCatalog(
        ProfileCatalog({"alexa": profile}),
        worker,
        "voxcpm2",
    )
    async with worker, catalog:
        assert catalog.get_audio("alexa", ReactionKind.GREETING) == raw
        assert catalog.get_audio("alexa", ReactionKind.FAREWELL) is None
        assert catalog.get_audio("missing", ReactionKind.GREETING) is None
    assert len(adapter.calls) == 2
    reaction_path = tmp_path / ".reactions" / "voxcpm2" / "greeting"
    hello_key = hashlib.sha256(b"Hello").hexdigest()[:10]
    assert (reaction_path / f"{hello_key}.wav").exists()
    assert (reaction_path / f"{hello_key}.txt").exists()

    cached_adapter = MockSynthesisAdapter(chunks=[])
    cached_worker = SynthesisWorker(cached_adapter)
    cached = ReactionCatalog(
        ProfileCatalog({"alexa": profile}),
        cached_worker,
        "voxcpm2",
    )
    async with cached_worker, cached:
        assert cached.get_audio("alexa", ReactionKind.GREETING) is not None
    assert not cached_adapter.calls


async def test_reaction_catalog_skips_missing_profile_and_empty_synthesis(
    tmp_path: Path,
):
    profile = _profile(tmp_path, {"greeting": ["Hello"]})
    synthesis = profile.synthesis.model_copy(update={"voxcpm2": None})
    profile = profile.model_copy(update={"synthesis": synthesis})
    worker = SynthesisWorker(MockSynthesisAdapter(chunks=[]))
    catalog = ReactionCatalog(ProfileCatalog({"alexa": profile}), worker, "voxcpm2")
    async with worker, catalog:
        assert catalog.get_audio("alexa", ReactionKind.GREETING) is None
