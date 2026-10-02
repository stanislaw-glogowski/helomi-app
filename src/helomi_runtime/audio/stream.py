from collections.abc import Iterator

from .domain import AudioFormat, RawAudio


class AudioStreamBuffer:
    """Coalesce model output into fixed-duration Float32 playback portions."""

    def __init__(self, duration_seconds: float = 0.1):
        if duration_seconds <= 0:
            raise ValueError("Audio portion duration must be positive")
        self._duration_seconds = duration_seconds
        self._format: AudioFormat | None = None
        self._pending = bytearray()

    def feed(self, audio: RawAudio) -> Iterator[RawAudio]:
        if len(audio.data) % (4 * audio.format.channels):
            raise ValueError("Audio contains an incomplete Float32 sample")
        if self._format is not None and self._format != audio.format:
            raise ValueError("Audio format changed during synthesis")
        self._format = audio.format
        size = max(1, round(audio.format.sample_rate * self._duration_seconds)) * 4
        view = memoryview(audio.data)
        while view:
            length = min(size - len(self._pending), len(view))
            self._pending.extend(view[:length])
            view = view[length:]
            if len(self._pending) == size:
                yield RawAudio(audio.format, bytes(self._pending))
                self._pending.clear()

    def finish(self) -> RawAudio | None:
        if self._format is None or not self._pending:
            return None
        audio = RawAudio(self._format, bytes(self._pending))
        self._pending.clear()
        return audio
