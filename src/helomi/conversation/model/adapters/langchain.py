from collections.abc import Iterator
from typing import Any

from ...tools.domain import ToolCall
from ..config import (
    LangChainModelProfile,
    LangChainModelsProfile,
    LangChainSettings,
)
from ..domain import (
    ConversationRole,
    LanguageModelChunk,
    LanguageModelProtocolError,
    LanguageModelRequest,
    LanguageModelRole,
    ToolChoice,
)
from ..ports import LanguageModel


class LangChainLanguageModel(LanguageModel):
    def __init__(
        self,
        profiles: LangChainModelsProfile,
        settings: LangChainSettings,
    ) -> None:
        super().__init__()
        self._profiles = profiles
        self._settings = settings
        self._models: dict[LanguageModelRole, Any] = {}
        self._init_chat_model: Any = None

    def open(self) -> None:
        if self._init_chat_model is not None:
            raise RuntimeError("LangChain language model adapter is already open")
        from langchain.chat_models import init_chat_model

        self._init_chat_model = init_chat_model
        self._logger.debug("Adapter OPENED")

    def close(self) -> None:
        self._models.clear()
        self._init_chat_model = None
        self._logger.debug("Adapter CLOSED")

    def prepare(self, role: LanguageModelRole) -> None:
        self._model(role)

    def generate(self, request: LanguageModelRequest) -> Iterator[LanguageModelChunk]:
        from langchain.messages import AIMessage, HumanMessage, SystemMessage

        message_types = {
            ConversationRole.SYSTEM: SystemMessage,
            ConversationRole.USER: HumanMessage,
            ConversationRole.ASSISTANT: AIMessage,
        }
        messages = [
            message_types[message.role](content=message.content)
            for message in request.messages
        ]
        model = self._model(request.role)
        if request.tools:
            bind_kwargs: dict[str, Any] = {}
            if request.tool_choice is ToolChoice.REQUIRED:
                bind_kwargs["tool_choice"] = "any"
            model = model.bind_tools(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                    for tool in request.tools
                ],
                **bind_kwargs,
            )
        calls: list[ToolCall] = []
        for chunk in model.stream(messages):
            if chunk.text and request.tool_choice is not ToolChoice.REQUIRED:
                yield LanguageModelChunk(chunk.text)
            for call in getattr(chunk, "tool_calls", ()):
                if call.get("name") and call.get("id"):
                    calls.append(
                        ToolCall(
                            id=str(call["id"]),
                            name=str(call["name"]),
                            arguments=dict(call.get("args", {})),
                        )
                    )
        if calls:
            yield LanguageModelChunk(tool_calls=tuple(calls))
        elif request.tool_choice is ToolChoice.REQUIRED:
            raise LanguageModelProtocolError("Required tool call was not produced")

    def _model(self, role: LanguageModelRole) -> Any:
        if model := self._models.get(role):
            return model

        profile = self._profile(role)
        model_id = profile.model_id
        if self._init_chat_model is None:
            raise RuntimeError("LangChain language model adapter is not open")
        model = self._init_chat_model(
            model_id,
            temperature=profile.temperature,
            top_p=profile.top_p,
            num_predict=profile.max_tokens,
            reasoning=self._reasoning(model_id, profile.thinking),
            base_url=self._settings.base_url,
        )
        self._models[role] = model
        self._logger.debug("Model LOADED: role='{}', model='{}'", role, model_id)
        return model

    @staticmethod
    def _reasoning(model_id: str, thinking: bool) -> bool | str:
        # GPT-OSS does not support disabling reasoning; low is its shortest mode.
        if not thinking and model_id.startswith("ollama:gpt-oss"):
            return "low"
        return thinking

    def _profile(self, role: LanguageModelRole) -> LangChainModelProfile:
        profile = getattr(self._profiles, role.value)
        if profile is None:
            raise RuntimeError(f"Language model role is not configured: {role!r}")
        return profile
