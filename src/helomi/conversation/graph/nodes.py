import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from time import perf_counter
from typing import Any

from langchain.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.prompts import PromptTemplate
from langgraph.config import get_stream_writer
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from loguru import logger

from ..model import (
    ConversationMessage,
    ConversationRole,
    LanguageModelProtocolError,
    LanguageModelRequest,
    LanguageModelRole,
    LanguageModelService,
    ToolChoice,
)
from ..profile import ProfilePreparation
from ..reply import ConversationQuit, ConversationTextChunk, PreparedReactionKind
from ..tools.domain import ToolCall, ToolResult
from .context import ConversationContext, ConversationRuntime
from .routing import (
    ReactionPolicy,
    ResponseDepth,
    ToolPolicy,
    TurnIntent,
    TurnPlan,
    TurnPlanner,
)
from .state import ConversationState


class ConversationNodes:
    OPENING = "opening"
    REPLY = "reply"
    SUMMARIZE = "summarize"
    BACKGROUND_RESULT = "background_result"
    TOOL_INSTRUCTION = (
        "Use an available tool whenever the request depends on external state or "
        "requires a side effect. To report a file's contents, call file_read even "
        "if the conversation appears to contain or imply those contents. A tool "
        "action succeeded only when its result explicitly says succeeded. If a "
        "tool result says failed, correct the call or state the failure plainly; "
        "never claim completion."
    )

    def __init__(
        self,
        language_model: LanguageModelService,
        turn_planner: TurnPlanner | None = None,
        profile_preparation: ProfilePreparation | None = None,
    ) -> None:
        self._language_model = language_model
        self._turn_planner = turn_planner or TurnPlanner()
        self._profile_preparation = profile_preparation

    async def opening(
        self,
        state: ConversationState,
        runtime: ConversationRuntime,
    ) -> dict[str, list[AnyMessage] | str]:
        context = runtime.context
        if self._profile_preparation is not None and (
            reaction := self._profile_preparation.next_wake_reaction()
        ):
            get_stream_writer()(ConversationTextChunk(f"{reaction}\n"))
            return {"messages": [], "delivery_context": ""}

        summary = state.get("summary", "")
        messages = state.get("messages", [])[-context.recent_messages :]
        opening_prompt = PromptTemplate.from_template(context.opening_prompt).format(
            conversation_summary=summary or "No previous conversation.",
            recent_conversation=self._format_messages(messages),
        )
        request = LanguageModelRequest(
            LanguageModelRole.FAST,
            self._request_messages(
                state,
                context,
                summary,
                [*messages, HumanMessage(content=opening_prompt)],
            ),
            cache_prefix=self._cache_prefix(context),
        )
        response, _ = await self._stream_visible(request)
        return {"messages": [AIMessage(response)], "delivery_context": ""}

    async def reply(
        self,
        state: ConversationState,
        runtime: ConversationRuntime,
    ) -> dict[str, Any]:
        reply_started = perf_counter()
        context = runtime.context
        summary = state.get("summary", "")
        messages = state["messages"][-context.recent_messages :]
        user_text = next(
            (
                message.text
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        memories = (
            await context.memory.search(user_text) if context.memory is not None else ()
        )
        memory_context = self._memory_context(memories)
        if pending := state.get("pending_tool"):
            reaction_task = self._start_reaction_timer(
                ReactionPolicy.ACKNOWLEDGE, context, reply_started
            )
            try:
                return await self._resolve_confirmation(pending, user_text, context)
            finally:
                await self._stop_reaction_timer(reaction_task)
        plan = self._turn_planner.deterministic_plan(user_text)
        if plan is None:
            plan = await self._classify(
                state, context, summary, messages, memory_context
            )
        if plan.intent is TurnIntent.QUIT:
            self._emit_quit()
            return {"messages": [AIMessage("Quit requested.")]}
        if plan.intent in {TurnIntent.NO_RESPONSE, TurnIntent.CANCEL}:
            return {"messages": []}
        role = (
            LanguageModelRole.DETAILED
            if plan.depth is ResponseDepth.DETAILED
            else LanguageModelRole.FAST
        )
        instruction = f"{self._response_instruction(plan)} {self.TOOL_INSTRUCTION}"
        tool_context: list[SystemMessage] = []
        tool_history: list[AnyMessage] = []
        available_tools = {
            definition.name: definition
            for definition in (
                context.tools.definitions if context.tools is not None else ()
            )
        }
        reaction_task = self._start_reaction_timer(
            plan.reaction, context, reply_started
        )

        def delivered() -> None:
            if reaction_task is not None:
                reaction_task.cancel()

        try:
            repair_attempted = False
            for _ in range(8):
                tool_required = plan.tool_policy is ToolPolicy.REQUIRED and bool(
                    available_tools
                )
                request = LanguageModelRequest(
                    role,
                    self._request_messages(
                        state,
                        context,
                        summary,
                        [
                            SystemMessage(content=instruction),
                            *messages,
                            *tool_context,
                        ],
                        memory_context,
                    ),
                    cache_prefix=self._cache_prefix(context),
                    tools=tuple(available_tools.values()),
                    tool_choice=(
                        ToolChoice.REQUIRED if tool_required else ToolChoice.AUTO
                    ),
                )
                try:
                    response, calls = await self._stream_visible(
                        request,
                        deliver=not tool_required,
                        on_visible=delivered,
                    )
                except LanguageModelProtocolError as error:
                    logger.warning(
                        "Model tool protocol error: {}: {}", type(error).__name__, error
                    )
                    if tool_required and not repair_attempted:
                        repair_attempted = True
                        tool_context.append(
                            SystemMessage(
                                content=(
                                    "The previous response was invalid. Return "
                                    "exactly one available tool call and no prose."
                                )
                            )
                        )
                        continue
                    return self._tool_protocol_failure(tool_history)
                if not calls:
                    if tool_required:
                        if not repair_attempted:
                            repair_attempted = True
                            tool_context.append(
                                SystemMessage(
                                    content=(
                                        "Return exactly one available tool call "
                                        "and no prose."
                                    )
                                )
                            )
                            continue
                        return self._tool_protocol_failure(tool_history)
                    return {"messages": [AIMessage(response)]}
                if context.tools is None:
                    return {"messages": [AIMessage("I cannot use tools right now.")]}
                background = False
                for call in calls:
                    definition = context.tools.definition(call.name)
                    if definition is None:
                        tool_context.append(
                            SystemMessage(
                                content=f"Tool error: unknown tool {call.name}."
                            )
                        )
                        continue
                    if definition.require_confirmation:
                        return {
                            "messages": [
                                AIMessage("Please confirm that I should run this tool.")
                            ],
                            "pending_tool": {
                                "id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                    if definition.mode == "background":
                        await context.tools.enqueue(call)
                        tool_history.append(
                            AIMessage(content=f"Background tool accepted: {call.name}.")
                        )
                        delivered()
                        if self._profile_preparation is not None and (
                            reaction := (
                                self._profile_preparation.next_background_reaction()
                            )
                        ):
                            get_stream_writer()(ConversationTextChunk(f"{reaction}\n"))
                        background = True
                        continue
                    result = await context.tools.execute(call)
                    result_message = self._tool_result_message(call, result)
                    if result.quit_requested:
                        tool_history.append(AIMessage(content="Quit requested."))
                        delivered()
                        self._emit_quit()
                        return {"messages": tool_history}
                    tool_context.append(SystemMessage(content=result_message))
                    if not result.is_error:
                        available_tools.clear()
                if background:
                    return {"messages": tool_history}
            return {
                "messages": [
                    *tool_history,
                    AIMessage("I could not complete the tool request."),
                ]
            }
        finally:
            await self._stop_reaction_timer(reaction_task)

    async def _resolve_confirmation(
        self,
        pending: dict[str, Any],
        user_text: str,
        context: ConversationContext,
    ) -> dict[str, Any]:
        affirmative = {"yes", "yeah", "y", "tak", "jasne", "potwierdzam"}
        if user_text.strip().lower() not in affirmative:
            return {
                "messages": [AIMessage("The pending tool request was cancelled.")],
                "pending_tool": None,
            }
        if context.tools is None:
            return {
                "messages": [AIMessage("I cannot use tools right now.")],
                "pending_tool": None,
            }
        call = ToolCall(
            id=str(pending["id"]),
            name=str(pending["name"]),
            arguments=dict(pending["arguments"]),
        )
        definition = context.tools.definition(call.name)
        if definition is None:
            return {
                "messages": [AIMessage("The requested tool is no longer available.")],
                "pending_tool": None,
            }
        if definition.mode == "background":
            await context.tools.enqueue(call)
            if self._profile_preparation is not None and (
                reaction := self._profile_preparation.next_background_reaction()
            ):
                get_stream_writer()(ConversationTextChunk(f"{reaction}\n"))
            return {"messages": [], "pending_tool": None}
        result = await context.tools.execute(call)
        if result.quit_requested:
            self._emit_quit()
            return {"messages": [], "pending_tool": None}
        return {
            "messages": [AIMessage(self._tool_result_message(call, result))],
            "pending_tool": None,
        }

    def _emit_quit(self) -> None:
        writer = get_stream_writer()
        if self._profile_preparation is not None and (
            reaction := self._profile_preparation.next_quit_reaction()
        ):
            writer(ConversationTextChunk(f"{reaction}\n"))
        writer(ConversationQuit())

    async def _classify(
        self,
        state: ConversationState,
        context: ConversationContext,
        summary: str,
        messages: list[AnyMessage],
        memory_context: SystemMessage | None = None,
    ) -> TurnPlan:
        classification = ""
        tool_catalog = "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in (context.tools.definitions if context.tools is not None else ())
        )
        classifier_prompt = self._turn_planner.CLASSIFICATION_PROMPT
        if tool_catalog:
            classifier_prompt = f"{classifier_prompt}\nAvailable tools:\n{tool_catalog}"
        try:
            async for chunk in self._language_model.generate(
                LanguageModelRequest(
                    LanguageModelRole.CLASSIFIER,
                    self._request_messages(
                        state,
                        context,
                        summary,
                        [
                            SystemMessage(content=classifier_prompt),
                            *messages,
                        ],
                        memory_context,
                    ),
                    cache_prefix=self._cache_prefix(context),
                )
            ):
                classification += chunk.content
        except Exception:
            return TurnPlan(TurnIntent.RESPOND, ResponseDepth.STANDARD)
        return self._turn_planner.classified_plan(classification)

    @staticmethod
    def _response_instruction(plan: TurnPlan) -> str:
        if plan.intent is TurnIntent.CLARIFY:
            return "Ask exactly one concise clarification question. Do not answer yet."
        instructions = {
            ResponseDepth.BRIEF: "Answer in one or two concise sentences.",
            ResponseDepth.STANDARD: "Answer in two to four concise sentences.",
            ResponseDepth.DETAILED: (
                "Give a comprehensive answer at an appropriate length."
            ),
        }
        return instructions[plan.depth]

    async def summarize(
        self,
        state: ConversationState,
        runtime: ConversationRuntime,
    ) -> dict[str, Any]:
        context = runtime.context
        summary_prompt = PromptTemplate.from_template(context.summary_prompt).format(
            conversation_summary=state.get("summary", "") or "No previous summary.",
            recent_conversation=self._format_messages(
                state["messages"][-context.recent_messages :]
            ),
        )
        content = ""
        async for chunk in self._language_model.generate(
            LanguageModelRequest(
                LanguageModelRole.FAST,
                self._domain_messages(
                    [
                        *self._delivery_messages(state),
                        HumanMessage(content=summary_prompt),
                    ]
                ),
            )
        ):
            content += chunk.content
        recent = state["messages"][-context.recent_messages :]
        return {
            "summary": content,
            "delivery_context": "",
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *recent],
        }

    async def background_result(
        self,
        state: ConversationState,
        runtime: ConversationRuntime,
    ) -> dict[str, list[AnyMessage]]:
        context = runtime.context
        messages = state["messages"][-context.recent_messages :]
        request = LanguageModelRequest(
            LanguageModelRole.FAST,
            self._request_messages(
                state,
                context,
                state.get("summary", ""),
                [
                    SystemMessage(
                        content=(
                            "Summarize this completed background tool result concisely "
                            "for the user. State failures plainly."
                        )
                    ),
                    *messages,
                ],
            ),
            cache_prefix=self._cache_prefix(context),
        )
        response, _ = await self._stream_visible(request)
        return {"messages": [AIMessage(response)]}

    async def _stream_visible(
        self,
        request: LanguageModelRequest,
        deliver: bool = True,
        on_visible: Callable[[], None] | None = None,
    ) -> tuple[str, tuple[ToolCall, ...]]:
        writer = get_stream_writer()
        content = ""
        calls: list[ToolCall] = []
        async for chunk in self._language_model.generate(request):
            content += chunk.content
            if deliver and chunk.content:
                if on_visible is not None:
                    on_visible()
                    on_visible = None
                writer(ConversationTextChunk(chunk.content))
            calls.extend(chunk.tool_calls)
        return content, tuple(calls)

    def _start_reaction_timer(
        self,
        policy: ReactionPolicy,
        context: ConversationContext,
        reply_started: float,
    ) -> asyncio.Task[None] | None:
        if policy is ReactionPolicy.NONE:
            return None
        delay = (
            context.acknowledgement_delay
            if policy is ReactionPolicy.ACKNOWLEDGE
            else context.wait_reaction_delay
        )
        delay = max(0.0, delay - (perf_counter() - reply_started))
        return asyncio.create_task(
            self._emit_reaction_after(policy, delay), name="helomi-reaction"
        )

    async def _emit_reaction_after(self, policy: ReactionPolicy, delay: float) -> None:
        await asyncio.sleep(delay)
        reaction = self._next_reaction(policy)
        if reaction is None:
            return
        get_stream_writer()(
            ConversationTextChunk(
                f"{reaction}\n",
                reaction=(
                    PreparedReactionKind.ACKNOWLEDGEMENT
                    if policy is ReactionPolicy.ACKNOWLEDGE
                    else PreparedReactionKind.WAIT
                ),
            )
        )

    @staticmethod
    async def _stop_reaction_timer(task: asyncio.Task[None] | None) -> None:
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @staticmethod
    def _tool_protocol_failure(tool_history: list[AnyMessage]) -> dict[str, Any]:
        content = "I could not complete the tool request."
        get_stream_writer()(ConversationTextChunk(content))
        return {"messages": [*tool_history, AIMessage(content)]}

    def _next_reaction(self, policy: ReactionPolicy) -> str | None:
        if self._profile_preparation is None:
            return None
        if policy is ReactionPolicy.ACKNOWLEDGE:
            return self._profile_preparation.next_acknowledgement_reaction()
        if policy is ReactionPolicy.WAIT:
            return self._profile_preparation.next_wait_reaction()
        return None

    @staticmethod
    def _tool_result_message(call: ToolCall, result: ToolResult) -> str:
        status = "failed" if result.is_error else "succeeded"
        arguments = dict(call.arguments)
        if call.name == "file_write" and "content" in arguments:
            arguments["content_length"] = len(str(arguments.pop("content")))
        arguments_json = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return f"Tool call {call.name}({arguments_json}) {status}: {result.content}"

    @classmethod
    def _request_messages(
        cls,
        state: ConversationState,
        context: ConversationContext,
        summary: str,
        messages: list[AnyMessage],
        memory_context: SystemMessage | None = None,
    ) -> tuple[ConversationMessage, ...]:
        return cls._domain_messages(
            [
                SystemMessage(
                    content=PromptTemplate.from_template(context.system_prompt).format(
                        conversation_summary=(
                            "The current conversation summary is supplied in the "
                            "next system message."
                        )
                    )
                ),
                SystemMessage(
                    content="Conversation summary: "
                    f"{summary or 'No previous conversation.'}"
                ),
                *([memory_context] if memory_context is not None else []),
                *cls._delivery_messages(state),
                *messages,
            ]
        )

    @staticmethod
    def _cache_prefix(context: ConversationContext) -> str:
        return PromptTemplate.from_template(context.system_prompt).format(
            conversation_summary=(
                "The current conversation summary is supplied in the next system "
                "message."
            )
        )

    @staticmethod
    def _domain_messages(
        messages: list[AnyMessage],
    ) -> tuple[ConversationMessage, ...]:
        roles = {
            "system": ConversationRole.SYSTEM,
            "human": ConversationRole.USER,
            "ai": ConversationRole.ASSISTANT,
        }
        system_content = "\n\n".join(
            message.text
            for message in messages
            if message.type == "system" and message.text
        )
        conversation = tuple(
            ConversationMessage(roles[message.type], message.text)
            for message in messages
            if message.type != "system" and message.text
        )
        if not system_content:
            return conversation
        return (
            ConversationMessage(ConversationRole.SYSTEM, system_content),
            *conversation,
        )

    @staticmethod
    def _format_messages(messages: list[AnyMessage]) -> str:
        if not messages:
            return "No recent conversation."
        return "\n".join(
            f"{message.type}: {message.text}" for message in messages if message.text
        )

    @staticmethod
    def _delivery_messages(state: ConversationState) -> list[SystemMessage]:
        context = state.get("delivery_context", "")
        return [SystemMessage(content=context)] if context else []

    @staticmethod
    def _memory_context(memories: tuple[Any, ...]) -> SystemMessage | None:
        if not memories:
            return None
        content = "\n".join(f"- {memory.key}: {memory.content}" for memory in memories)
        return SystemMessage(
            content=(
                "Relevant durable profile memories follow. Use them as user-provided "
                "context, but do not claim more certainty than they support:\n"
                f"{content}"
            )
        )
