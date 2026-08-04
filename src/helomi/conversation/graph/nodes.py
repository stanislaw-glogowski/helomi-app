import asyncio
from contextlib import suppress
from time import perf_counter
from typing import Any

from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langgraph.config import get_stream_writer

from ..model import (
    ConversationMessage,
    ConversationRole,
    LanguageModelRequest,
    LanguageModelRole,
    LanguageModelService,
)
from ..profile import ProfilePreparation
from ..reply import ConversationQuit, ConversationTextChunk
from ..tools.domain import ToolCall
from .context import ConversationContext, ConversationRuntime
from .routing import ResponseDepth, TurnIntent, TurnPlan, TurnPlanner
from .state import ConversationState


class ConversationNodes:
    OPENING = "opening"
    REPLY = "reply"
    SUMMARIZE = "summarize"
    BACKGROUND_RESULT = "background_result"

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
            get_stream_writer()(ConversationTextChunk(f"{reaction}\n", True))
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
        if pending := state.get("pending_tool"):
            return await self._resolve_confirmation(pending, user_text, context)
        plan = self._turn_planner.deterministic_plan(user_text)
        if plan is None:
            plan = await self._classify(state, context, summary, messages)
        if plan.intent in {TurnIntent.NO_RESPONSE, TurnIntent.CANCEL}:
            return {"messages": []}
        role = (
            LanguageModelRole.DETAILED
            if plan.depth is ResponseDepth.DETAILED
            else LanguageModelRole.FAST
        )
        instruction = self._response_instruction(plan)
        tool_context: list[SystemMessage] = []
        tool_history: list[AnyMessage] = []
        for _ in range(8):
            request = LanguageModelRequest(
                role,
                self._request_messages(
                    state,
                    context,
                    summary,
                    [SystemMessage(content=instruction), *messages, *tool_context],
                ),
                cache_prefix=self._cache_prefix(context),
                tools=(context.tools.definitions if context.tools is not None else ()),
            )
            response, calls = await self._stream_visible(
                request,
                acknowledgement_delay=max(
                    0.0,
                    context.acknowledgement_delay - (perf_counter() - reply_started),
                ),
            )
            if not calls:
                return {"messages": [*tool_history, AIMessage(response)]}
            if context.tools is None:
                return {"messages": [AIMessage("I cannot use tools right now.")]}
            background = False
            for call in calls:
                definition = context.tools.definition(call.name)
                if definition is None:
                    tool_context.append(
                        SystemMessage(content=f"Tool error: unknown tool {call.name}.")
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
                    if self._profile_preparation is not None and (
                        reaction := self._profile_preparation.next_background_reaction()
                    ):
                        get_stream_writer()(
                            ConversationTextChunk(f"{reaction}\n", True)
                        )
                    background = True
                    continue
                result = await context.tools.execute(call)
                if result.quit_requested:
                    tool_history.append(AIMessage(content="Quit requested."))
                    if self._profile_preparation is not None and (
                        reaction := self._profile_preparation.next_quit_reaction()
                    ):
                        get_stream_writer()(
                            ConversationTextChunk(f"{reaction}\n", True)
                        )
                    get_stream_writer()(ConversationQuit())
                    return {"messages": tool_history}
                tool_history.append(
                    AIMessage(content=f"Tool result for {call.name}: {result.content}")
                )
                tool_context.append(
                    SystemMessage(
                        content=f"Tool result for {call.name}: {result.content}"
                    )
                )
            if background:
                return {"messages": tool_history}
        return {
            "messages": [
                *tool_history,
                AIMessage("I could not complete the tool request."),
            ]
        }

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
                get_stream_writer()(ConversationTextChunk(f"{reaction}\n", True))
            return {"messages": [], "pending_tool": None}
        result = await context.tools.execute(call)
        if result.quit_requested:
            if self._profile_preparation is not None and (
                reaction := self._profile_preparation.next_quit_reaction()
            ):
                get_stream_writer()(ConversationTextChunk(f"{reaction}\n", True))
            get_stream_writer()(ConversationQuit())
            return {"messages": [], "pending_tool": None}
        return {
            "messages": [AIMessage(f"Tool result: {result.content}")],
            "pending_tool": None,
        }

    async def _classify(
        self,
        state: ConversationState,
        context: ConversationContext,
        summary: str,
        messages: list[AnyMessage],
    ) -> TurnPlan:
        classification = ""
        try:
            async for chunk in self._language_model.generate(
                LanguageModelRequest(
                    LanguageModelRole.CLASSIFIER,
                    self._request_messages(
                        state,
                        context,
                        summary,
                        [
                            SystemMessage(
                                content=self._turn_planner.CLASSIFICATION_PROMPT
                            ),
                            *messages,
                        ],
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
    ) -> dict[str, str]:
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
        return {"summary": content, "delivery_context": ""}

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
        acknowledgement_delay: float | None = None,
    ) -> tuple[str, tuple[ToolCall, ...]]:
        writer = get_stream_writer()
        content = ""
        calls: list[ToolCall] = []
        stream = self._language_model.generate(request)
        if acknowledgement_delay is not None:
            first_chunk = asyncio.ensure_future(anext(stream))
            try:
                chunk = await asyncio.wait_for(
                    asyncio.shield(first_chunk), acknowledgement_delay
                )
            except TimeoutError:
                if self._profile_preparation is not None and (
                    reaction := self._profile_preparation.next_reaction()
                ):
                    writer(ConversationTextChunk(f"{reaction}\n", True))
                chunk = await first_chunk
            except StopAsyncIteration:
                return content, tuple(calls)
            except asyncio.CancelledError:
                first_chunk.cancel()
                with suppress(asyncio.CancelledError):
                    await first_chunk
                await stream.aclose()
                raise
            content += chunk.content
            writer(ConversationTextChunk(chunk.content))
            calls.extend(chunk.tool_calls)

        async for chunk in stream:
            content += chunk.content
            writer(ConversationTextChunk(chunk.content))
            calls.extend(chunk.tool_calls)
        return content, tuple(calls)

    @classmethod
    def _request_messages(
        cls,
        state: ConversationState,
        context: ConversationContext,
        summary: str,
        messages: list[AnyMessage],
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
