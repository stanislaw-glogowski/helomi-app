from dataclasses import dataclass, field
from enum import Enum

from helomi.app import ProgressSnapshot
from helomi.resources import ProfileEntry


class DesktopMode(Enum):
    READY = "Ready"
    STARTING = "Starting"
    RETRYING = "Retrying"
    RUNNING = "Running"
    FAILED = "Failed"
    SHUTTING_DOWN = "Shutting down"


@dataclass(frozen=True, slots=True)
class DesktopSnapshot:
    mode: DesktopMode
    profiles: tuple[ProfileEntry, ...] = ()
    default_profile_id: str | None = None
    selected_profile_id: str | None = None
    detail: str | None = None
    progress: ProgressSnapshot = field(default_factory=ProgressSnapshot)

    @property
    def profiles_enabled(self) -> bool:
        return self.mode in {DesktopMode.READY, DesktopMode.FAILED}

    @property
    def retry_enabled(self) -> bool:
        return self.mode is DesktopMode.FAILED and self.selected_profile_id is not None
