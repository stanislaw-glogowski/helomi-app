from dataclasses import dataclass, field
from enum import Enum

from helomi.app import ProgressSnapshot


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
    profile_name: str = "Helomi"
    selected_profile_id: str | None = None
    detail: str | None = None
    progress: ProgressSnapshot = field(default_factory=ProgressSnapshot)

    @property
    def retry_enabled(self) -> bool:
        return self.mode is DesktopMode.FAILED and self.selected_profile_id is not None

    @property
    def tray_title(self) -> str:
        match self.mode:
            case DesktopMode.RUNNING:
                return self.profile_name
            case DesktopMode.FAILED:
                return f"❌ {self.profile_name}"
            case _:
                return f"⏳ {self.profile_name}"
