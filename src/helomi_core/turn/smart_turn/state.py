from collections import deque

import numpy as np

from ...audio import AudioChunk
from .config import SmartTurnConfig


class SmartTurnState:
    def __init__(self, config: SmartTurnConfig, chunk: AudioChunk) -> None:
        sample_rate = chunk.format.sample_rate
        chunk_size = chunk.samples.size

        self.format = chunk.format
        self.pre_roll_frames = max(
            1,
            round(config.pre_roll_seconds * sample_rate / chunk_size),
        )
        self.post_roll_frames = max(
            1,
            round(config.post_roll_seconds * sample_rate / chunk_size),
        )
        self.min_speech_samples = round(config.min_speech_seconds * sample_rate)
        self.silence_samples_required = round(config.silence_seconds * sample_rate)
        self.fallback_silence_samples = round(
            config.fallback_silence_seconds * sample_rate
        )
        self.conversation_timeout_samples = round(
            config.conversation_timeout_seconds * sample_rate
        )
        self.max_turn_samples = round(config.max_audio_seconds * sample_rate)

        self.pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_frames)
        self.turn_frames: list[np.ndarray] = []
        self.last_voice_frame_idx: int = 0

        self.active = False
        self.waiting_for_continuation = False
        self.speech_samples = 0
        self.silence_samples = 0
        self.idle_silence_samples = 0

    def reset(self, full: bool = True) -> None:
        if full:
            self.pre_roll.clear()
            self.idle_silence_samples = 0

        self.turn_frames.clear()
        self.active = False
        self.waiting_for_continuation = False
        self.speech_samples = 0
        self.silence_samples = 0
        self.last_voice_frame_idx = 0
