from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class PipelineRequest[TData]:
    _current_generation: ClassVar[int] = 0

    @classmethod
    def current_generation(cls) -> int:
        return cls._current_generation

    @classmethod
    def bump_generation(cls) -> None:
        cls._current_generation += 1

    data: TData
    trace_id: str | None = None
    generation: int = field(
        default_factory=lambda: PipelineRequest.current_generation(),
    )

    @property
    def is_current_generation(self) -> bool:
        return self.generation == PipelineRequest.current_generation()
