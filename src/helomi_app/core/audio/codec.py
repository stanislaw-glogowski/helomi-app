import numpy as np
from numpy.typing import NDArray


def _build_mulaw_to_int16_table() -> NDArray:
    table = np.zeros(256, dtype=np.int16)
    for i in range(256):
        u_val = ~i & 0xFF
        t = ((u_val & 0x0F) << 3) + 0x84
        t <<= (u_val & 0x70) >> 4
        table[i] = (0x84 - t) if (u_val & 0x80) else (t - 0x84)
    return table


def _build_int16_to_mulaw_table() -> NDArray:
    seg_end = [0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF]
    table = np.zeros(65536, dtype=np.uint8)
    for pcm in range(-32768, 32768):
        val = pcm >> 2
        if val < 0:
            val = -val
            mask = 0x7F
        else:
            mask = 0xFF
        if val > 32635:
            val = 32635
        val += 0x84 >> 2
        seg = 8
        for s in range(8):
            if val <= seg_end[s]:
                seg = s
                break
        if seg >= 8:
            uval = 0x7F ^ mask
        else:
            uval = ((seg << 4) | ((val >> (seg + 1)) & 0x0F)) ^ mask
        table[pcm + 32768] = uval
    return table


_MULAW_TO_INT16: NDArray = _build_mulaw_to_int16_table()
_MULAW_TO_FLOAT32: NDArray = _MULAW_TO_INT16.astype(np.float32) / 32768.0
_INT16_TO_MULAW: NDArray = _build_int16_to_mulaw_table()


def mulaw_to_float32(data: bytes) -> bytes:
    """Decode 8-bit G.711 mu-law audio to 32-bit float PCM bytes."""
    if not data:
        return b""
    indices = np.frombuffer(data, dtype=np.uint8)
    return _MULAW_TO_FLOAT32[indices].tobytes()


def int16_to_mulaw(data: bytes) -> bytes:
    """Encode 16-bit signed PCM audio bytes to 8-bit G.711 mu-law."""
    if not data:
        return b""
    remainder = len(data) % 2
    if remainder:
        data = data[:-remainder]
        if not data:
            return b""
    samples = np.frombuffer(data, dtype=np.int16)
    indices = samples.astype(np.int32) + 32768
    return _INT16_TO_MULAW[indices].tobytes()


def int16_to_float32(data: bytes) -> bytes:
    samples = np.frombuffer(data, dtype=np.int16)
    samples = samples.astype(np.float32).flatten()
    samples = np.clip(samples / 32767.0, -1.0, 1.0)
    return samples.tobytes()


def float32_to_int16(data: bytes | NDArray) -> bytes:
    samples = np.frombuffer(data, dtype=np.float32) if isinstance(data, bytes) else data
    samples = samples.astype(np.float32).flatten()
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767).astype(np.int16).tobytes()


def float32_to_mulaw(data: bytes | NDArray) -> bytes:
    return int16_to_mulaw(float32_to_int16(data))
