from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WakeWordPrediction:
    matched: str | None
    scores: dict[str, float]
