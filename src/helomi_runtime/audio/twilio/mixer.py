from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soxr
from numpy.typing import NDArray

from ..domain import AudioChunk, AudioFile, AudioFormat, RawAudio
from ..room_voice import RoomVoiceProfile


@dataclass(frozen=True, slots=True)
class MixedFrame:
    data: bytes
    completed_playbacks: tuple[str, ...]


@dataclass(slots=True)
class _Playback:
    id: str
    turn_id: int | None
    samples: NDArray[np.float32]
    offset: int = 0


class TwilioMixer:
    """Mix speech and ambient audio into paced 20 ms Twilio frames."""

    SAMPLE_RATE = 8_000
    FRAME_SAMPLES = 160

    def __init__(self, max_pending_playbacks: int):
        self._max_pending_playbacks = max_pending_playbacks
        self._playbacks: deque[_Playback] = deque()
        self._room_samples = np.empty(0, dtype=np.float32)
        self._room_offset = 0
        self._room_volume = 0.0
        self._room_ducking = 0.0
        self._turn_id: int | None = None

    @property
    def has_output(self) -> bool:
        return bool(self._playbacks) or self._room_samples.size > 0

    @property
    def pending_playbacks(self) -> int:
        return len(self._playbacks)

    @property
    def room_voice_active(self) -> bool:
        return self._room_samples.size > 0

    def enqueue(
        self,
        audio: RawAudio,
        playback_id: str,
        turn_id: int | None,
    ) -> bool:
        if turn_id is not None:
            if self._turn_id is not None and turn_id < self._turn_id:
                return False
            if self._turn_id is None or turn_id > self._turn_id:
                self._turn_id = turn_id
                self._playbacks.clear()

        if len(self._playbacks) >= self._max_pending_playbacks:
            return False

        samples = self._convert(audio)
        self._playbacks.append(
            _Playback(
                id=playback_id,
                turn_id=turn_id,
                samples=samples,
            )
        )
        return True

    def interrupt(self, turn_id: int | None = None) -> None:
        self._playbacks.clear()
        self._turn_id = turn_id

    def start_room_voice(self, profile: RoomVoiceProfile) -> None:
        self._room_samples = self._load_room_voice(profile.path)
        self._room_offset = 0
        self._room_volume = profile.volume
        self._room_ducking = profile.ducking

    def stop_room_voice(self) -> None:
        self._room_samples = np.empty(0, dtype=np.float32)
        self._room_offset = 0

    def next_frame(self) -> MixedFrame | None:
        if not self.has_output:
            return None

        speech = np.zeros(self.FRAME_SAMPLES, dtype=np.float32)
        completed: list[str] = []
        written = 0
        while self._playbacks and written < self.FRAME_SAMPLES:
            playback = self._playbacks[0]
            available = playback.samples.size - playback.offset
            length = min(self.FRAME_SAMPLES - written, available)
            if length > 0:
                speech[written : written + length] = playback.samples[
                    playback.offset : playback.offset + length
                ]
                playback.offset += length
                written += length
            if playback.offset >= playback.samples.size:
                completed.append(playback.id)
                self._playbacks.popleft()

        ambient = self._room_frame()
        speech_active = bool(np.any(np.abs(speech) > 1e-5))
        ambient_gain = self._room_volume * (
            self._room_ducking if speech_active else 1.0
        )
        mixed = np.clip(speech + ambient * ambient_gain, -1.0, 1.0)
        return MixedFrame(
            data=AudioChunk(
                format=AudioFormat.MONO_8,
                samples=np.asarray(mixed, dtype=np.float32),
            ).to_mulaw(),
            completed_playbacks=tuple(completed),
        )

    def _room_frame(self) -> NDArray[np.float32]:
        if self._room_samples.size == 0:
            return np.zeros(self.FRAME_SAMPLES, dtype=np.float32)

        frame = np.empty(self.FRAME_SAMPLES, dtype=np.float32)
        written = 0
        while written < self.FRAME_SAMPLES:
            available = self._room_samples.size - self._room_offset
            length = min(self.FRAME_SAMPLES - written, available)
            frame[written : written + length] = self._room_samples[
                self._room_offset : self._room_offset + length
            ]
            written += length
            self._room_offset = (self._room_offset + length) % self._room_samples.size
        return frame

    @classmethod
    def _load_room_voice(cls, path: Path) -> NDArray[np.float32]:
        return cls._convert(AudioFile(path).read())

    @classmethod
    def _convert(cls, audio: RawAudio) -> NDArray[np.float32]:
        samples = np.asarray(
            AudioChunk.from_raw(audio).samples,
            dtype=np.float32,
        ).reshape(-1)
        if audio.format.sample_rate != cls.SAMPLE_RATE:
            samples = soxr.resample(
                samples,
                audio.format.sample_rate,
                cls.SAMPLE_RATE,
                quality="MQ",
            )
        return np.ascontiguousarray(samples, dtype=np.float32)
