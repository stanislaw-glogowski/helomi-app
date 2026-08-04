from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, model_validator

from helomi.common.validation import ConfigModel

from ..model.config import LanguageModelProfile


class ConversationPrompts(ConfigModel):
    system: str = Field(min_length=1)
    opening: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ConversationReactions(ConfigModel):
    wake: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    acknowledge: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    wait: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    background: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    quit: tuple[Annotated[str, Field(min_length=1)], ...] = ()


class StreamableHttpMcpEndpoint(ConfigModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    transport: Literal["streamable_http"] = "streamable_http"
    url: AnyHttpUrl
    mode: Literal["immediate", "background"] = "immediate"
    require_confirmation: bool = False
    headers_from_env: dict[str, str] = Field(default_factory=dict)


class StdioMcpEndpoint(ConfigModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    transport: Literal["stdio"] = "stdio"
    command: str = Field(min_length=1)
    args: tuple[str, ...] = ()
    mode: Literal["immediate", "background"] = "immediate"
    require_confirmation: bool = False
    env_from_env: dict[str, str] = Field(default_factory=dict)


type McpEndpoint = Annotated[
    StreamableHttpMcpEndpoint | StdioMcpEndpoint,
    Field(discriminator="transport"),
]


class McpConfiguration(ConfigModel):
    endpoints: tuple[McpEndpoint, ...] = ()

    @model_validator(mode="after")
    def _unique_ids(self) -> McpConfiguration:
        ids = [endpoint.id for endpoint in self.endpoints]
        if len(ids) != len(set(ids)):
            raise ValueError("MCP endpoint ids must be unique")
        return self


class ConversationProfile(LanguageModelProfile):
    recent_messages: int = Field(default=8, ge=2)
    prompts: ConversationPrompts
    reactions: ConversationReactions = ConversationReactions()
