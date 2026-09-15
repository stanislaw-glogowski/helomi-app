from collections.abc import Iterable, Iterator

import numpy as np
import soxr

from .domain import AudioChunk, AudioFormat, RawAudio


class AudioResampler:
    def __init__(self, format: AudioFormat) -> None:
        self._format = format
        self._block_size = format.block_size
        self._streams: dict[int, soxr.ResampleStream] = {}
        self._buffer = np.empty(0, dtype=np.float32)

    def resample(
        self, stream: Iterable[RawAudio] | RawAudio, last: bool = False
    ) -> Iterator[AudioChunk]:
        # Support single RawAudio chunk or an entire Iterable stream
        if isinstance(stream, RawAudio):
            yield from self._process_raw(stream, last=False)
            if last:
                yield from self._flush_all()
            return

        # Process stream of RawAudio and automatically flush on exhaustion
        for raw in stream:
            yield from self._process_raw(raw, last=False)

        yield from self._flush_all()

    def reset(self) -> None:
        """Reset internal resample streams and clear buffered audio."""
        for stream in self._streams.values():
            stream.clear()
        self._streams.clear()
        self._buffer = np.empty(0, dtype=np.float32)

    def _process_raw(self, raw: RawAudio, last: bool = False) -> Iterator[AudioChunk]:
        chunk = AudioChunk.from_raw(raw)
        samples = np.asarray(chunk.samples, dtype=np.float32).reshape(-1)

        stream = self._get_stream(chunk.format.sample_rate)
        if stream is not None:
            resampled = stream.resample_chunk(samples, last=last)
            converted = np.ascontiguousarray(resampled, dtype=np.float32).reshape(-1)
        else:
            converted = samples

        if converted.size:
            self._buffer = np.concatenate((self._buffer, converted))

        while self._buffer.size >= self._block_size:
            block = self._buffer[: self._block_size].copy()
            self._buffer = self._buffer[self._block_size :]

            yield AudioChunk(
                format=self._format,
                samples=block,
            )

    def _flush_all(self) -> Iterator[AudioChunk]:
        # 1. Flush soxr delay-line filters
        for stream in self._streams.values():
            resampled = stream.resample_chunk(
                np.empty(0, dtype=np.float32),
                last=True,
            )
            converted = np.ascontiguousarray(resampled, dtype=np.float32).reshape(-1)
            if converted.size:
                self._buffer = np.concatenate((self._buffer, converted))

        # 2. Yield remaining full blocks
        while self._buffer.size >= self._block_size:
            block = self._buffer[: self._block_size].copy()
            self._buffer = self._buffer[self._block_size :]
            yield AudioChunk(format=self._format, samples=block)

        # 3. Yield remaining partial block at end-of-stream
        if self._buffer.size > 0:
            remaining = self._buffer.copy()
            self._buffer = np.empty(0, dtype=np.float32)
            yield AudioChunk(format=self._format, samples=remaining)

    def _get_stream(self, in_sample_rate: int) -> soxr.ResampleStream | None:
        if in_sample_rate == self._format.sample_rate:
            return None

        stream = self._streams.get(in_sample_rate)
        if stream is None:
            stream = soxr.ResampleStream(
                in_sample_rate,
                self._format.sample_rate,
                num_channels=1,
                dtype="float32",
                quality="MQ",
            )
            self._streams[in_sample_rate] = stream

        return stream
