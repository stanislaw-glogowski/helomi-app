from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TypedDict

from helomi_core.audio import RawAudio
from helomi_core.pipeline import PipelineExtensionKey
from helomi_core.server import ServerExtension


class AppStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    QUITING = auto()


@dataclass(frozen=True, slots=True)
class AppState:
    class Update(TypedDict, total=False):
        status: AppStatus
        active_profile: str | None
        active_extension: PipelineExtensionKey
        server_url: str | None
        recording: list[RawAudio] | None

    status: AppStatus = AppStatus.STARTING
    active_profile: str | None = None
    active_extension: PipelineExtensionKey = ServerExtension
    recording: list[RawAudio] | None = None
    server_url: str | None = None
