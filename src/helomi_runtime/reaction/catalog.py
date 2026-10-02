import asyncio
import hashlib
import random
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from helomi_foundation import ManagedComponent, TextFile, on_mount

from ..audio import AudioFile, RawAudio
from ..synthesis import SynthesisRequest, SynthesisWorker

if TYPE_CHECKING:
    from ..config import ProfileCatalog
    from .domain import ReactionKind


class ReactionCatalog(ManagedComponent):
    _REACTIONS_DIR: ClassVar[str] = ".reactions"
    _FILE_NAME_LEN: ClassVar[int] = 10

    def __init__(
        self,
        profiles: ProfileCatalog,
        synthesis_worker: SynthesisWorker,
        synthesis_adapter: str,
    ):
        super().__init__()
        self._profiles = profiles
        self._synthesis_worker = synthesis_worker
        self._synthesis_adapter = synthesis_adapter
        self._cache: dict[str, dict[ReactionKind, list[RawAudio]]] = {}

    def get_audio(
        self,
        profile_id: str,
        reaction: ReactionKind,
    ) -> RawAudio | None:
        reactions = self._cache.get(profile_id, {}).get(reaction, [])
        if not reactions:
            return None
        return random.choice(reactions)

    @on_mount()
    async def _preload(self):
        for profile in self._profiles:
            self._cache[profile.id] = {}
            for reaction, texts in profile.reactions.items():
                reactions: list[RawAudio] = []

                self._cache[profile.id][reaction] = reactions

                synthesis_profile = profile.get_synthesis_profile(
                    self._synthesis_adapter,
                    required=False,
                )
                if not texts or synthesis_profile is None:
                    continue

                for text in texts:
                    file_name = hashlib.sha256(text.encode("utf-8")).hexdigest()[
                        : self._FILE_NAME_LEN
                    ]

                    path = (
                        profile.root_path
                        / self._REACTIONS_DIR
                        / self._synthesis_adapter
                        / reaction
                        / file_name
                    )

                    try:
                        audio = await self._preload_reaction_audio(
                            profile_id=profile.id,
                            path=path,
                            reaction=reaction,
                            text=text,
                        )
                    except Exception as error:
                        self._logger.warning(
                            "Failed to preload {} for {}: {}",
                            reaction,
                            profile.id,
                            error,
                        )
                        continue

                    if not audio:
                        continue

                    reactions.append(audio)

    async def _preload_reaction_audio(
        self,
        profile_id: str,
        path: Path,
        reaction: ReactionKind,
        text: str,
    ) -> RawAudio | None:
        audio_file = AudioFile(path)

        if audio_file.exists:
            self._logger.trace(f"Detected {reaction}: {text}")

            return await asyncio.to_thread(audio_file.read)

        chunks: list[RawAudio] = []

        self._logger.debug(f"Synthesizing {reaction}: {text}")

        async for chunk in self._synthesis_worker.synthesize(
            SynthesisRequest(
                text=text,
                profile_id=profile_id,
            )
        ):
            chunks.append(chunk.audio)

        if not chunks:
            return None

        audio = RawAudio.concat(chunks)

        await asyncio.to_thread(
            self._write_cache,
            audio_file,
            path,
            audio,
            text,
        )

        return audio

    @staticmethod
    def _write_cache(
        audio_file: AudioFile,
        path: Path,
        audio: RawAudio,
        text: str,
    ) -> None:
        audio_file.write(audio)
        TextFile(path).write(text)
