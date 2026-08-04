import copy
import json
import re
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from huggingface_hub.utils import disable_progress_bars

from ...tools.domain import ToolCall, ToolDefinition
from ..config import MLXModelProfile, MLXModelsProfile
from ..domain import (
    LanguageModelChunk,
    LanguageModelProtocolError,
    LanguageModelRequest,
    LanguageModelRole,
    ToolChoice,
)
from ..ports import LanguageModel


@dataclass(slots=True)
class _LoadedModel:
    model: Any
    tokenizer: Any
    prompt_caches: OrderedDict[str, tuple[tuple[int, ...], Any]]


class _VisibleTextFilter:
    """Remove a leading model-internal channel block without delaying normal text."""

    _START = "<|channel>"
    _END = "<channel|>"

    def __init__(self, start: str = _START, end: str = _END) -> None:
        self._start = start
        self._end = end
        self._pending = ""
        self._resolved = False

    def feed(self, text: str) -> str:
        if self._resolved:
            return text
        self._pending += text
        if self._start.startswith(self._pending):
            return ""
        if not self._pending.startswith(self._start):
            self._resolved = True
            visible, self._pending = self._pending, ""
            return visible
        if self._end not in self._pending:
            return ""
        _, visible = self._pending.split(self._end, 1)
        self._pending = ""
        self._resolved = True
        return visible.lstrip("\n")

    def finish(self) -> str:
        pending, self._pending = self._pending, ""
        self._resolved = True
        return "" if pending.startswith(self._start) else pending


_GENERIC_THINKING_BLOCK = re.compile(
    r"<(?:thinking|think|thought)>.*?</(?:thinking|think|thought)?>",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_THINKING_OPEN = re.compile(r"<(?:thinking|think|thought)>", re.IGNORECASE)
_GENERIC_THINKING_CLOSE = re.compile(r"</(?:thinking|think|thought)?>", re.IGNORECASE)


class MLXLanguageModel(LanguageModel):
    _TOOL_ALIASES: ClassVar[dict[str, str]] = {
        "default_list_files": "files_list",
        "default_read_file": "file_read",
        "default_write_file": "file_write",
    }

    def __init__(self, profiles: MLXModelsProfile) -> None:
        super().__init__()
        self._profiles = profiles
        self._models: dict[str, _LoadedModel] = {}
        self._load: Any = None
        self._stream_generate: Any = None
        self._make_sampler: Any = None
        self._make_prompt_cache: Any = None
        self._generate_step: Any = None
        self._array: Any = None
        self._tool_call_sequence = 0

    def open(self) -> None:
        if self._load is not None:
            raise RuntimeError("MLX language model adapter is already open")
        import mlx.core as mx
        from mlx_lm import load, stream_generate
        from mlx_lm.generate import generate_step
        from mlx_lm.models.cache import make_prompt_cache
        from mlx_lm.sample_utils import make_sampler

        self._load = load
        self._stream_generate = stream_generate
        self._make_sampler = make_sampler
        self._make_prompt_cache = make_prompt_cache
        self._generate_step = generate_step
        self._array = mx.array
        self._logger.debug("Adapter OPENED")

    def close(self) -> None:
        self._models.clear()
        self._load = None
        self._stream_generate = None
        self._make_sampler = None
        self._make_prompt_cache = None
        self._generate_step = None
        self._array = None
        self._logger.debug("Adapter CLOSED")

    def prepare(self, role: LanguageModelRole) -> None:
        self._model(role)

    def generate(self, request: LanguageModelRequest) -> Iterator[LanguageModelChunk]:
        loaded = self._model(request.role)
        profile = self._profile(request.role)
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        ]
        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in request.tools
        ]
        prompt = loaded.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=profile.thinking,
            **({"tools": tool_schemas} if tool_schemas else {}),
        )
        if self._stream_generate is None or self._make_sampler is None:
            raise RuntimeError("MLX language model adapter is not open")
        sampler = self._make_sampler(
            temp=profile.temperature,
            top_p=profile.top_p,
            top_k=profile.top_k,
        )
        prompt_value, prompt_cache = self._cached_prompt(
            loaded,
            request,
            prompt,
            profile.thinking,
        )
        if request.tools:
            content = "".join(
                response.text
                for response in self._stream_generate(
                    loaded.model,
                    loaded.tokenizer,
                    prompt=prompt_value,
                    max_tokens=profile.max_tokens,
                    sampler=sampler,
                    prompt_cache=prompt_cache,
                )
                if response.text
            )
            if calls := self._tool_calls(
                content, loaded.tokenizer, tool_schemas, request.tools
            ):
                yield LanguageModelChunk(tool_calls=calls)
                return
            visible = self._visible_text(content, loaded.tokenizer)
            if request.tool_choice is ToolChoice.REQUIRED:
                raise LanguageModelProtocolError("Required tool call was not produced")
            if visible:
                yield LanguageModelChunk(visible)
            return
        content = "".join(
            response.text
            for response in self._stream_generate(
                loaded.model,
                loaded.tokenizer,
                prompt=prompt_value,
                max_tokens=profile.max_tokens,
                sampler=sampler,
                prompt_cache=prompt_cache,
            )
            if response.text
        )
        if visible := self._visible_text(content, loaded.tokenizer):
            yield LanguageModelChunk(visible)

    @staticmethod
    def _visible_text(content: str, tokenizer: Any | None = None) -> str:
        """Remove model protocol channels from a complete response."""
        start = getattr(tokenizer, "think_start", None) or _VisibleTextFilter._START
        end = getattr(tokenizer, "think_end", None) or _VisibleTextFilter._END
        if start in content:
            if end not in content:
                raise LanguageModelProtocolError("Unclosed model reasoning channel")
            content = re.sub(
                rf"(?:^|\s)thought\s*{re.escape(start)}.*?{re.escape(end)}",
                " ",
                content,
                flags=re.DOTALL,
            )
            content = re.sub(
                rf"{re.escape(start)}.*?{re.escape(end)}",
                " ",
                content,
                flags=re.DOTALL,
            )
        content = _GENERIC_THINKING_BLOCK.sub(" ", content)
        if _GENERIC_THINKING_OPEN.search(content) or _GENERIC_THINKING_CLOSE.search(
            content
        ):
            raise LanguageModelProtocolError("Unclosed model thinking block")
        if "<|tool_call" in content or "<tool_call|>" in content:
            raise LanguageModelProtocolError("Unparsed model tool-call syntax")
        return content.strip()

    def _tool_calls(
        self,
        content: str,
        tokenizer: Any,
        tool_schemas: list[dict[str, Any]],
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[ToolCall, ...]:
        """Normalize tokenizer-native and legacy tool-call formats."""
        parser = getattr(tokenizer, "tool_parser", None)
        if parser is not None:
            try:
                parsed = parser(content, tool_schemas)
                parsed_calls = parsed if isinstance(parsed, list) else [parsed]
                if calls := self._validated_calls(parsed_calls, tools):
                    return calls
            except KeyError, TypeError, ValueError, json.JSONDecodeError:
                pass
        return self._fallback_tool_calls(content, tools)

    def _validated_calls(
        self,
        parsed_calls: list[dict[str, Any]],
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[ToolCall, ...]:
        available = {tool.name for tool in tools}
        calls: list[ToolCall] = []
        for index, call in enumerate(parsed_calls):
            name = self._TOOL_ALIASES.get(str(call["name"]), str(call["name"]))
            arguments = call["arguments"]
            if name not in available or not isinstance(arguments, dict):
                return ()
            calls.append(
                ToolCall(
                    id=self._tool_call_id(call, index), name=name, arguments=arguments
                )
            )
        return tuple(calls)

    def _tool_call_id(self, call: dict[str, Any], index: int) -> str:
        if call_id := call.get("id"):
            return str(call_id)
        self._tool_call_sequence += 1
        return f"mlx-{self._tool_call_sequence}-{index}"

    def _fallback_tool_calls(
        self,
        content: str,
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[ToolCall, ...]:
        """Parse known Qwen tool-call wire formats when tokenizer parsing fails."""
        available = {tool.name for tool in tools}
        calls: list[ToolCall] = []
        decoder = json.JSONDecoder()
        for match in re.finditer(r"tool_call:([a-zA-Z0-9_-]+)\s*\(", content):
            name = match.group(1)
            if name not in available:
                continue
            try:
                arguments, end = decoder.raw_decode(content[match.end() :])
            except json.JSONDecodeError:
                continue
            if not isinstance(arguments, dict):
                continue
            if not content[match.end() + end :].lstrip().startswith(")"):
                continue
            calls.append(
                ToolCall(
                    id=self._tool_call_id({}, len(calls)),
                    name=name,
                    arguments=arguments,
                )
            )
        tagged_start = "<|tool_call|>call:"
        tagged_end = "<tool_call|>"
        offset = 0
        while (start := content.find(tagged_start, offset)) >= 0:
            name_start = start + len(tagged_start)
            arguments_start = content.find("{", name_start)
            end = content.find(tagged_end, name_start)
            if arguments_start < 0 or end < 0 or arguments_start >= end:
                offset = name_start
                continue
            raw_name = content[name_start:arguments_start].strip()
            name = self._TOOL_ALIASES.get(raw_name, raw_name)
            arguments = self._tagged_arguments(content[arguments_start:end])
            if name in available and arguments is not None:
                calls.append(
                    ToolCall(
                        id=self._tool_call_id({}, len(calls)),
                        name=name,
                        arguments=arguments,
                    )
                )
            offset = end + len(tagged_end)
        return tuple(calls)

    @staticmethod
    def _tagged_arguments(value: str) -> dict[str, Any] | None:
        """Decode Qwen's JSON-like object with its known unquoted argument keys."""
        normalized = re.sub(
            r"([,{]\s*)(content|mode|path)\s*:",
            r'\1"\2":',
            value.strip(),
        )
        try:
            arguments = json.loads(normalized)
        except json.JSONDecodeError:
            return None
        return arguments if isinstance(arguments, dict) else None

    def _model(self, role: LanguageModelRole) -> _LoadedModel:
        profile = self._profile(role)
        model_id = profile.model_id
        if loaded := self._models.get(model_id):
            return loaded
        if self._load is None:
            raise RuntimeError("MLX language model adapter is not open")
        with disable_progress_bars():
            model, tokenizer = self._load(model_id)
        loaded = _LoadedModel(model, tokenizer, OrderedDict())
        self._models[model_id] = loaded
        self._logger.debug("Model LOADED: role='{}', model='{}'", role, model_id)
        return loaded

    def _cached_prompt(
        self,
        loaded: _LoadedModel,
        request: LanguageModelRequest,
        prompt: str,
        thinking: bool,
    ) -> tuple[str | list[int], Any]:
        if (
            len(request.messages) < 2
            or request.messages[0].role.value != "system"
            or self._make_prompt_cache is None
            or self._generate_step is None
            or self._array is None
        ):
            return prompt, None

        system_content = request.messages[0].content
        cache_prefix = request.cache_prefix or system_content
        if not system_content.startswith(cache_prefix):
            return prompt, None
        cache_key = f"{thinking}:{cache_prefix}"
        if cached := loaded.prompt_caches.get(cache_key):
            prefix_tokens, prompt_cache = cached
            loaded.prompt_caches.move_to_end(cache_key)
        else:
            prefix_tokens = self._prompt_prefix_tokens(
                loaded, prompt, cache_prefix, thinking
            )
            if prefix_tokens is None:
                return prompt, None
            prompt_cache = self._make_prompt_cache(loaded.model)
            for _ in self._generate_step(
                self._array(prefix_tokens),
                loaded.model,
                max_tokens=0,
                prompt_cache=prompt_cache,
            ):
                pass
            loaded.prompt_caches[cache_key] = (prefix_tokens, prompt_cache)
            if len(loaded.prompt_caches) > 4:
                loaded.prompt_caches.popitem(last=False)

        prompt_tokens = loaded.tokenizer.encode(prompt)
        prefix_length = len(prefix_tokens)
        if tuple(prompt_tokens[:prefix_length]) != prefix_tokens:
            return prompt, None
        return prompt_tokens[prefix_length:], copy.deepcopy(prompt_cache)

    def _prompt_prefix_tokens(
        self,
        loaded: _LoadedModel,
        prompt: str,
        cache_prefix: str,
        thinking: bool,
    ) -> tuple[int, ...] | None:
        marker = "__HELOMI_PROMPT_CACHE_BOUNDARY__"
        try:
            rendered_prefix = loaded.tokenizer.apply_chat_template(
                [{"role": "system", "content": f"{cache_prefix}{marker}"}],
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=thinking,
            )
        except Exception as error:
            self._logger.debug(
                "Prompt prefix cache unavailable: {}", type(error).__name__
            )
            return None
        prefix_end = rendered_prefix.find(marker)
        if prefix_end < 0:
            self._logger.debug("Prompt prefix cache unavailable: marker not rendered")
            return None
        prefix_tokens = tuple(loaded.tokenizer.encode(rendered_prefix[:prefix_end]))
        prompt_tokens = tuple(loaded.tokenizer.encode(prompt))
        while prefix_tokens and prompt_tokens[: len(prefix_tokens)] != prefix_tokens:
            prefix_tokens = prefix_tokens[:-1]
        if not prefix_tokens:
            self._logger.debug("Prompt prefix cache unavailable: token boundary")
            return None
        return prefix_tokens

    def _profile(self, role: LanguageModelRole) -> MLXModelProfile:
        profile = getattr(self._profiles, role.value)
        if profile is None:
            raise RuntimeError(f"Language model role is not configured: {role!r}")
        return profile
