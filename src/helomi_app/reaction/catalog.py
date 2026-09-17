import hashlib
import random
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ..common import AbstractAsyncComponent, TextFile
from ..core.audio import AudioFile, RawAudio
from ..core.tts import TTSRequest, TTSWorker

if TYPE_CHECKING:
    from ..profile import ProfileCatalog
    from .domain import ReactionKind


class ReactionCatalog(AbstractAsyncComponent):
    _REACTIONS_DIR: ClassVar[str] = ".reactions"
    _FILE_NAME_LEN: ClassVar[int] = 10

    def __init__(self, profiles: ProfileCatalog, tts_worker: TTSWorker):
        super().__init__()
        self._profiles = profiles
        self._tts_worker = tts_worker
        self._cache: dict[str, dict[ReactionKind, list[RawAudio]]] = {}

    def get_audio(
        self,
        profile_id: str,
        reaction: ReactionKind,
    ) -> RawAudio | None:
        reactions = self._cache[profile_id][reaction]
        if not reactions:
            return None
        return random.choice(reactions)

    async def _do_open(self):
        for profile in self._profiles:
            self._cache[profile.id] = {}
            for reaction, texts in profile.reactions.items():
                reactions: list[RawAudio] = []

                self._cache[profile.id][reaction] = reactions

                if not texts or profile.tts.extract_adapter(require=False) is None:
                    continue

                for text in texts:
                    file_name = hashlib.sha256(text.encode("utf-8")).hexdigest()[
                        : self._FILE_NAME_LEN
                    ]

                    path = (
                        profile.root_path
                        / self._REACTIONS_DIR
                        / profile.tts.adapter
                        / reaction
                        / file_name
                    )

                    self._logger.trace(f"Preloading {reaction}: {text}")

                    audio = await self._preload_reaction_audio(
                        profile_id=profile.id,
                        path=path,
                        text=text,
                    )

                    if not audio:
                        continue

                    reactions.append(audio)

    async def _preload_reaction_audio(
        self,
        profile_id: str,
        path: Path,
        text: str,
    ) -> RawAudio | None:
        audio_file = AudioFile(path)

        if audio_file.exists:
            return audio_file.read()

        chunks: list[RawAudio] = []

        async for chunk in self._tts_worker.synthesize(
            TTSRequest(
                text=text,
                profile_id=profile_id,
            )
        ):
            chunks.append(chunk.audio)

        if not chunks:
            return None

        audio = RawAudio.concat(chunks)

        audio_file.write(audio)
        TextFile(path).write(text)

        return audio
