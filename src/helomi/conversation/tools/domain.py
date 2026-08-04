from dataclasses import dataclass
from typing import Any, Literal

type ToolMode = Literal["immediate", "background"]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    mode: ToolMode = "immediate"
    require_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False
    quit_requested: bool = False
