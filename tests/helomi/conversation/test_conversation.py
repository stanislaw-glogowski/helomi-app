import asyncio
import sys
from collections.abc import AsyncIterator, Iterator
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar

import pytest
from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

import helomi.conversation.model as model_module
from helomi.common.events import EventBus, ShutdownEvent
from helomi.conversation import run_conversation_worker
from helomi.conversation.config import ConversationSettings
from helomi.conversation.events import (
    CancelReply,
    ConversationActivated,
    GenerateReply,
    ReplyChunk,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyPhrase,
    UserTurn,
)
from helomi.conversation.graph import (
    ConversationContext,
    ConversationGraph,
    ConversationNodes,
    ReactionPolicy,
    ResponseDepth,
    TurnIntent,
    TurnPlanner,
)
from helomi.conversation.model import (
    ConversationMessage,
    ConversationRole,
    LanguageModelChunk,
    LanguageModelRequest,
    LanguageModelRole,
    LanguageModelService,
    get_language_model,
)
from helomi.conversation.model.adapters.langchain import LangChainLanguageModel
from helomi.conversation.model.adapters.mlx import MLXLanguageModel
from helomi.conversation.model.config import (
    LangChainModelProfile,
    LangChainSettings,
    MLXModelProfile,
    MLXSettings,
)
from helomi.conversation.profile import (
    ConversationProfile,
    ConversationPrompts,
    ConversationReactions,
    ProfilePreparation,
)
from helomi.conversation.reply import (
    ConversationQuit,
    ConversationTextChunk,
    PreparedReactionKind,
    ReplySegmenter,
)
from helomi.conversation.tools.domain import ToolCall, ToolDefinition
from helomi.conversation.tools.service import ToolService
from helomi.conversation.worker import Worker
from helomi.resources import TextFileCatalog
from tests.support import FakeLanguageModel


def profile() -> ConversationProfile:
    return ConversationProfile(
        models={
            "fast": {"model_id": "test/fast", "max_tokens": 96},
            "detailed": {"model_id": "test/detailed", "max_tokens": 256},
            "classifier": {"model_id": "test/classifier", "max_tokens": 4},
        },
        recent_messages=4,
        prompts=ConversationPrompts(
            system="System {conversation_summary}",
            opening="Opening {conversation_summary} {recent_conversation}",
            summary="Summary {conversation_summary} {recent_conversation}",
        ),
    )


def context(delay: float = 0.5, wait_delay: float | None = None) -> ConversationContext:
    return ConversationContext.from_profile(
        profile(),
        ConversationSettings(
            acknowledgement_delay=delay,
            wait_reaction_delay=delay if wait_delay is None else wait_delay,
        ),
    )


def test_configuration_domain_events_and_routing() -> None:
    value = profile()
    assert value.models_langchain.fast.model_id == "test/fast"
    mlx_value = value.model_copy(
        update={
            "models": {
                **value.models,
                "fast": {**value.models["fast"], "top_k": 12},
            }
        }
    )
    assert mlx_value.models_mlx.fast.top_k == 12
    with pytest.raises(ValidationError, match="top_k"):
        _ = mlx_value.models_langchain
    assert isinstance(ConversationSettings().language_model, MLXSettings)
    assert isinstance(
        ConversationSettings.model_validate(
            {"language_model": {"adapter": "mlx"}}
        ).language_model,
        MLXSettings,
    )
    with pytest.raises(ValidationError, match="model_id"):
        _ = ConversationProfile(
            models={"fast": {}, "detailed": {}},
            prompts=value.prompts,
        ).models_langchain
    legacy = value.model_copy(
        update={
            "models": {
                "fast": {"langchain": "test:fast", "mlx": "test/fast"},
                "detailed": {
                    "langchain": "test:detailed",
                    "mlx": "test/detailed",
                },
            }
        }
    )
    with pytest.raises(ValidationError, match="model_id"):
        _ = legacy.models_langchain
    with pytest.raises(ValidationError):
        ConversationReactions(wake=("",))
    with pytest.raises(ValidationError):
        ConversationProfile(
            models=value.models,
            recent_messages=1,
            prompts=value.prompts,
        )

    activation = ConversationActivated()
    turn = UserTurn("Hello")
    assert GenerateReply(activation).input == activation
    assert GenerateReply(turn).input == turn
    assert CancelReply() == CancelReply()
    assert ReplyChunk(1, "a").text == "a"
    assert ReplyPhrase(1, 1, "line").text == "line"
    assert ReplyGenerationStarted(1) == ReplyGenerationStarted(1)
    assert ReplyGenerationCompleted(1) == ReplyGenerationCompleted(1)

    planner = TurnPlanner()
    assert planner.deterministic_plan("").intent is TurnIntent.NO_RESPONSE
    assert planner.deterministic_plan("anuluj").intent is TurnIntent.CANCEL
    for request in (
        "Close the app",
        "Could you quit Helomi?",
        "Zamknij aplikację",
        "Czy możesz się wyłączyć?",
    ):
        assert planner.deterministic_plan(request).intent is TurnIntent.QUIT
    assert planner.deterministic_plan("Nie zamykaj aplikacji") is None
    brief_question = planner.deterministic_plan("Jak masz na imię?")
    assert brief_question is not None
    assert brief_question.depth is ResponseDepth.BRIEF
    assert brief_question.reaction is ReactionPolicy.NONE
    punctuation_free = planner.deterministic_plan("Jaka jest stolica Kanady")
    assert punctuation_free is not None
    assert punctuation_free.depth is ResponseDepth.BRIEF
    embedded_question = planner.deterministic_plan("Opowiedz mi skąd bierze się tęcza")
    assert embedded_question is not None
    assert embedded_question.depth is ResponseDepth.BRIEF
    explicit_question = planner.deterministic_plan("Powiedz co to jest")
    assert explicit_question is not None
    assert explicit_question.depth is ResponseDepth.BRIEF
    explicit_request = planner.deterministic_plan("Przygotuj plan rodzinnej wycieczki")
    assert explicit_request is not None
    assert explicit_request.depth is ResponseDepth.STANDARD
    assert explicit_request.reaction is ReactionPolicy.ACKNOWLEDGE
    detailed = planner.deterministic_plan("Wyjaśnij dokładnie echo akustyczne")
    assert detailed is not None
    assert detailed.depth is ResponseDepth.DETAILED
    assert detailed.reaction is ReactionPolicy.ACKNOWLEDGE
    assert planner.classified_plan("STANDARD").reaction is ReactionPolicy.WAIT
    assert planner.deterministic_plan("Powiedz mi więcej") is None
    assert planner.classified_plan(" detailed ").depth is ResponseDepth.DETAILED
    assert planner.classified_plan("CLARIFY").intent is TurnIntent.CLARIFY
    assert planner.classified_plan("unexpected").depth is ResponseDepth.STANDARD


def test_reply_segmenter_emits_natural_phrases_and_validates_limits() -> None:
    segmenter = ReplySegmenter(soft_limit=20, hard_limit=40)
    assert segmenter.feed("Tak. Kolejna wartość to 3.14, a np.") == (
        "Tak.",
        "Kolejna wartość to 3.14,",
    )
    assert segmenter.feed(" ten skrót nie kończy zdania. ") == (
        "a np. ten skrót nie kończy zdania.",
    )
    assert segmenter.feed("To bardzo długa fraza, którą można już wypowiedzieć") == (
        "To bardzo długa fraza,",
    )
    assert segmenter.flush() == ("którą można już wypowiedzieć",)

    quoted = ReplySegmenter(soft_limit=10, hard_limit=12)
    assert quoted.feed('"Gotowe!"\nNastępna długa fraza bez końca') == (
        '"Gotowe!"',
        "Następna długa",
    )
    assert quoted.flush() == ("fraza bez końca",)
    protected = ReplySegmenter()
    assert protected.feed("Model U.S. działa przy wersji 3.14 i nazwie x.y") == ()
    assert protected.flush() == ("Model U.S. działa przy wersji 3.14 i nazwie x.y",)
    with pytest.raises(ValueError, match="limits"):
        ReplySegmenter(soft_limit=10, hard_limit=5)
    with pytest.raises(ValueError, match="limits"):
        ReplySegmenter(soft_limit=0)


def test_language_model_service_owns_resources_and_streams() -> None:
    async def scenario() -> None:
        adapter = FakeLanguageModel("Answer")
        service = LanguageModelService(adapter)
        request = LanguageModelRequest(
            LanguageModelRole.FAST,
            (ConversationMessage(ConversationRole.USER, "Question"),),
        )
        with pytest.raises(RuntimeError, match="not started"):
            await service.prepare(LanguageModelRole.FAST)
        async with service:
            await service.prepare(LanguageModelRole.FAST)
            chunks = [chunk async for chunk in service.generate(request)]
        assert "".join(chunk.content for chunk in chunks) == "Answer"
        assert adapter.requests == [request]
        thread_ids = {thread_id for _, thread_id in adapter.operations}
        assert len(thread_ids) == 1

        await service.stop()

    asyncio.run(scenario())


def test_language_model_service_propagates_generation_error() -> None:
    class FailingModel(FakeLanguageModel):
        def generate(self, request: LanguageModelRequest):
            raise RuntimeError("generation failed")
            yield

    async def scenario() -> None:
        async with LanguageModelService(FailingModel()) as service:
            with pytest.raises(RuntimeError, match="generation failed"):
                _ = [
                    chunk
                    async for chunk in service.generate(
                        LanguageModelRequest(LanguageModelRole.FAST, ())
                    )
                ]

    asyncio.run(scenario())


def test_profile_preparation_generates_shuffled_rotating_reactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "helomi.conversation.profile.preparation.shuffle",
        lambda reactions: reactions.reverse(),
    )

    async def scenario() -> None:
        model = FakeLanguageModel()
        async with LanguageModelService(model) as service:
            preparation = ProfilePreparation(
                service,
                ConversationReactions(
                    wake=("Wake one.", "Wake two."),
                    acknowledge=("Acknowledge one.", "Acknowledge two."),
                    wait=("Wait one.", "Wait two."),
                ),
            )
            await preparation.prepare()
            assert [preparation.next_acknowledgement_reaction() for _ in range(3)] == [
                "Acknowledge two.",
                "Acknowledge one.",
                "Acknowledge two.",
            ]
            assert [preparation.next_wait_reaction() for _ in range(3)] == [
                "Wait two.",
                "Wait one.",
                "Wait two.",
            ]
            assert [preparation.next_wake_reaction() for _ in range(3)] == [
                "Wake two.",
                "Wake one.",
                "Wake two.",
            ]
        assert any(
            operation == f"prepare:{LanguageModelRole.FAST}"
            for operation, _ in model.operations
        )

    asyncio.run(scenario())


def test_tool_service_executes_and_deduplicates_builtin_file_calls(tmp_path) -> None:
    async def scenario() -> None:
        service = ToolService(TextFileCatalog(tmp_path / "data"))
        await service.start()
        try:
            write_definition = service.definition("file_write")
            assert write_definition is not None
            assert write_definition.input_schema["properties"]["mode"] == {
                "type": "string",
                "enum": ["create", "replace"],
            }
            write = ToolCall(
                "write-1",
                "file_write",
                {"path": "note", "content": "hello", "mode": "create"},
            )
            assert not (await service.execute(write)).is_error
            assert (await service.execute(write)).content == "Text file saved."
            assert (tmp_path / "data" / "note.txt").read_text() == "hello"
            read = await service.execute(
                ToolCall("read-1", "file_read", {"path": "note"})
            )
            assert read.content == "hello"
            quit_result = await service.execute(ToolCall("quit-1", "app_quit", {}))
            assert quit_result.quit_requested
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_tool_service_covers_remote_background_and_error_paths(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Text:
        text = "remote text"

    class Response:
        content = (Text(),)
        structuredContent: ClassVar[dict[str, int]] = {"answer": 1}
        isError = False

    class Session:
        async def call_tool(self, name: str, *, arguments: dict):
            assert name == "remote"
            assert arguments == {"value": 1}
            return Response()

    async def scenario() -> None:
        completed: list[tuple[ToolCall, object]] = []

        async def on_completed(call: ToolCall, result: object) -> None:
            completed.append((call, result))

        service = ToolService(
            TextFileCatalog(tmp_path / "data"), on_background_result=on_completed
        )
        await service.start()
        try:
            service._tools["mcp__demo__remote"] = (
                ToolDefinition(
                    "mcp__demo__remote",
                    "Remote",
                    {"type": "object"},
                    mode="background",
                ),
                "demo",
                "remote",
            )
            service._sessions["demo"] = Session()
            call = ToolCall("remote-1", "mcp__demo__remote", {"value": 1})
            result = await service.execute(call)
            assert result.content == 'remote text\n{"answer": 1}'
            await service.enqueue(call)
            await asyncio.wait_for(service._background.join(), 1)
            assert completed and completed[0][0] == call
            with pytest.raises(ValueError, match="background"):
                await service.enqueue(ToolCall("x", "files_list", {}))
            assert (await service.execute(ToolCall("bad", "missing", {}))).is_error
            assert service._format_mcp_result(
                SimpleNamespace(content=(), structuredContent=None)
            ).startswith("Tool returned")
        finally:
            await service.stop()

    monkeypatch.setenv("HELOMI_TOKEN", "secret")
    assert ToolService._environment_mapping({"Authorization": "HELOMI_TOKEN"}) == {
        "Authorization": "secret"
    }
    asyncio.run(scenario())


def test_graph_routes_streams_and_preserves_thread_history() -> None:
    async def scenario() -> None:
        adapter = FakeLanguageModel("Welcome", "Answer", "Remembered", "Welcome back")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service), InMemorySaver()
            ).compiled
            config = {"configurable": {"thread_id": "helomi"}}
            opened = await graph.ainvoke(
                {"messages": [], "input_kind": "activation"},
                config=config,
                context=context(),
            )
            assert [message.text for message in opened["messages"]] == ["Welcome"]

            visible: list[ConversationTextChunk] = []
            async for event in graph.astream(
                {
                    "messages": [HumanMessage("Question?")],
                    "input_kind": "user_turn",
                },
                config=config,
                context=context(),
                stream_mode="custom",
            ):
                visible.append(event)
            assert "".join(event.content for event in visible) == "Answer"

            state = await graph.aget_state(config)
            assert not state.values.get("summary")
            await graph.ainvoke(
                {"messages": [], "input_kind": "maintenance"},
                config=config,
                context=context(),
            )
            state = await graph.aget_state(config)
            assert state.values["summary"] == "Remembered"
            reopened = await graph.ainvoke(
                {"messages": [], "input_kind": "activation"},
                config=config,
                context=context(),
            )
            assert reopened["messages"][-1].text == "Welcome back"

        assert adapter.requests[0].role is LanguageModelRole.FAST
        assert adapter.requests[1].role is LanguageModelRole.FAST
        assert adapter.requests[2].role is LanguageModelRole.FAST
        assert adapter.requests[0].messages[0].role is ConversationRole.SYSTEM
        assert adapter.requests[3].messages[0].role is ConversationRole.SYSTEM
        assert adapter.requests[0].messages[0] != adapter.requests[3].messages[0]
        assert all(
            message.role is not ConversationRole.SYSTEM
            for message in adapter.requests[0].messages[1:]
        )

    asyncio.run(scenario())


def test_graph_emits_acknowledgement_for_slow_explicit_detailed_reply() -> None:
    class Prepared:
        def next_wake_reaction(self) -> None:
            return None

        def next_acknowledgement_reaction(self) -> str:
            return "Jasne."

        def next_wait_reaction(self) -> None:
            return None

    async def scenario() -> None:
        long_question = "Wyjaśnij dokładnie " + " ".join(
            f"word{index}" for index in range(24)
        )
        adapter = FakeLanguageModel("Detailed", "Summary")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage(long_question)],
                        "input_kind": "user_turn",
                    },
                    context=context(delay=0),
                    stream_mode="custom",
                )
            ]
        assert events[0] == ConversationTextChunk(
            "Jasne.\n", PreparedReactionKind.ACKNOWLEDGEMENT
        )
        assert "".join(event.content for event in events[1:]) == "Detailed"
        assert adapter.requests[0].role is LanguageModelRole.DETAILED

    asyncio.run(scenario())


def test_graph_skips_wait_reaction_for_slow_brief_reply() -> None:
    class Prepared:
        def next_wake_reaction(self) -> None:
            return None

        def next_acknowledgement_reaction(self) -> str:
            return "Jasne."

        def next_wait_reaction(self) -> str:
            return "Moment."

    async def scenario() -> None:
        adapter = FakeLanguageModel("Answer")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Jak masz na imię?")],
                        "input_kind": "user_turn",
                    },
                    context=context(delay=0),
                    stream_mode="custom",
                )
            ]
        assert "".join(event.content for event in events) == "Answer"
        assert not any(event.reaction for event in events)
        assert [request.role for request in adapter.requests] == [
            LanguageModelRole.FAST
        ]

    asyncio.run(scenario())


def test_graph_emits_wait_reaction_for_slow_classified_standard_reply() -> None:
    class Prepared:
        def next_wake_reaction(self) -> None:
            return None

        def next_acknowledgement_reaction(self) -> str:
            return "Jasne."

        def next_wait_reaction(self) -> str:
            return "Moment."

    async def scenario() -> None:
        adapter = FakeLanguageModel("STANDARD", "Answer")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Powiedz mi więcej")],
                        "input_kind": "user_turn",
                    },
                    context=context(delay=0),
                    stream_mode="custom",
                )
            ]
        assert events[0] == ConversationTextChunk(
            "Moment.\n", PreparedReactionKind.WAIT
        )
        assert "".join(event.content for event in events[1:]) == "Answer"
        assert [request.role for request in adapter.requests] == [
            LanguageModelRole.CLASSIFIER,
            LanguageModelRole.FAST,
        ]

    asyncio.run(scenario())


def test_graph_uses_optional_classifier_for_ambiguous_turn() -> None:
    async def scenario() -> None:
        question = " ".join(f"word{index}" for index in range(18))
        adapter = FakeLanguageModel("DETAILED", "Answer")
        settings = ConversationSettings(acknowledgement_delay=10)
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(ConversationNodes(service)).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage(question)],
                        "input_kind": "user_turn",
                    },
                    context=ConversationContext.from_profile(profile(), settings),
                    stream_mode="custom",
                )
            ]
        assert "".join(event.content for event in events) == "Answer"
        assert [request.role for request in adapter.requests] == [
            LanguageModelRole.CLASSIFIER,
            LanguageModelRole.DETAILED,
        ]

    asyncio.run(scenario())


def test_graph_skips_classifier_for_explicit_response_request() -> None:
    class Prepared:
        def next_acknowledgement_reaction(self) -> str:
            return "Jasne."

        def next_wait_reaction(self) -> str:
            return "Moment."

    async def scenario() -> None:
        adapter = FakeLanguageModel("Answer")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Przygotuj listę zakupów")],
                        "input_kind": "user_turn",
                    },
                    context=context(delay=10),
                    stream_mode="custom",
                )
            ]
        assert "".join(event.content for event in events) == "Answer"
        assert not any(event.reaction for event in events)
        assert [request.role for request in adapter.requests] == [
            LanguageModelRole.FAST
        ]

    asyncio.run(scenario())


def test_graph_executes_tool_only_chunk_after_acknowledgement_delay(tmp_path) -> None:
    poem = "Noc nad Wisłą, cichy blask."

    class ToolCallingLanguageModel(FakeLanguageModel):
        def generate(
            self, request: LanguageModelRequest
        ) -> Iterator[LanguageModelChunk]:
            self.requests.append(request)
            if any(tool.name == "file_write" for tool in request.tools):
                yield LanguageModelChunk(
                    tool_calls=(
                        ToolCall(
                            "write-poem",
                            "file_write",
                            {
                                "path": "wiersz.txt",
                                "content": poem,
                                "mode": "create",
                            },
                        ),
                    )
                )
                return
            yield LanguageModelChunk("Wiersz został zapisany.")

    class Prepared:
        def next_acknowledgement_reaction(self) -> str:
            return "Jasne."

        def next_wait_reaction(self) -> str:
            return "Moment."

    async def scenario() -> None:
        tools = ToolService(TextFileCatalog(tmp_path / "data"))
        await tools.start()
        try:
            adapter = ToolCallingLanguageModel()
            async with LanguageModelService(adapter) as service:
                graph = ConversationGraph(
                    ConversationNodes(service, profile_preparation=Prepared())
                ).compiled
                events = [
                    event
                    async for event in graph.astream(
                        {
                            "messages": [
                                HumanMessage("Napisz wiersz do pliku wiersz.txt")
                            ],
                            "input_kind": "user_turn",
                        },
                        context=ConversationContext.from_profile(
                            profile(),
                            ConversationSettings(acknowledgement_delay=0),
                            tools,
                        ),
                        stream_mode="custom",
                    )
                ]
        finally:
            await tools.stop()

        assert events == [
            ConversationTextChunk("Jasne.\n", PreparedReactionKind.ACKNOWLEDGEMENT),
            ConversationTextChunk("Wiersz został zapisany."),
        ]
        assert (tmp_path / "data" / "wiersz.txt").read_text(encoding="utf-8") == poem
        assert len(adapter.requests) == 2
        assert adapter.requests[1].tools == ()
        assert (
            ConversationNodes.TOOL_INSTRUCTION
            in adapter.requests[0].messages[0].content
        )
        assert any(
            (
                'Tool call file_write({"content_length": 27, "mode": "create", '
                '"path": "wiersz.txt"}) succeeded: '
                "Text file saved."
            )
            in message.content
            for message in adapter.requests[1].messages
        )

    asyncio.run(scenario())


def test_mlx_adapter_assigns_unique_ids_to_parser_calls() -> None:
    adapter = MLXLanguageModel(profile().models_mlx)

    first = adapter._tool_call_id({}, 0)
    second = adapter._tool_call_id({}, 0)

    assert first != second
    assert adapter._tool_call_id({"id": "provider-id"}, 0) == "provider-id"


def test_graph_handles_empty_response_after_acknowledgement_delay() -> None:
    async def scenario() -> None:
        adapter = FakeLanguageModel("")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(ConversationNodes(service)).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Napisz krótki wiersz")],
                        "input_kind": "user_turn",
                    },
                    context=context(delay=0),
                    stream_mode="custom",
                )
            ]
        assert events == []

    asyncio.run(scenario())


def test_graph_quits_deterministically_without_model_generation() -> None:
    class Prepared:
        def next_quit_reaction(self) -> str:
            return "Do usłyszenia."

    async def scenario() -> None:
        adapter = FakeLanguageModel("must not be generated")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Zamknij aplikację")],
                        "input_kind": "user_turn",
                    },
                    context=context(),
                    stream_mode="custom",
                )
            ]
        assert events == [
            ConversationTextChunk("Do usłyszenia.\n"),
            ConversationQuit(),
        ]
        assert adapter.requests == []

    asyncio.run(scenario())


def test_graph_handles_silent_cancel_and_invalid_classifier_plans() -> None:
    async def scenario() -> None:
        adapter = FakeLanguageModel("invalid classifier output", "Standard answer")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service), InMemorySaver()
            ).compiled
            config = {"configurable": {"thread_id": "helomi"}}
            canceled = [
                event
                async for event in graph.astream(
                    {"messages": [HumanMessage("anuluj")], "input_kind": "user_turn"},
                    config=config,
                    context=context(),
                    stream_mode="custom",
                )
            ]
            assert canceled == []
            state = await graph.aget_state(config)
            assert state.values["messages"][-1].text == "anuluj"

            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Powiedz mi więcej")],
                        "input_kind": "user_turn",
                    },
                    config=config,
                    context=context(),
                    stream_mode="custom",
                )
            ]
        assert "".join(event.content for event in events) == "Standard answer"
        assert [request.role for request in adapter.requests] == [
            LanguageModelRole.CLASSIFIER,
            LanguageModelRole.FAST,
        ]
        assert "two to four" in adapter.requests[-1].messages[0].content

    asyncio.run(scenario())


def test_graph_falls_back_when_classifier_fails() -> None:
    class FailingClassifier(FakeLanguageModel):
        def generate(self, request: LanguageModelRequest):
            if request.role is LanguageModelRole.CLASSIFIER:
                raise RuntimeError("classifier unavailable")
            return super().generate(request)

    async def scenario() -> None:
        adapter = FailingClassifier("Standard answer")
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(ConversationNodes(service)).compiled
            events = [
                event
                async for event in graph.astream(
                    {
                        "messages": [HumanMessage("Powiedz mi więcej")],
                        "input_kind": "user_turn",
                    },
                    context=context(),
                    stream_mode="custom",
                )
            ]
        assert "".join(event.content for event in events) == "Standard answer"
        assert adapter.requests[-1].role is LanguageModelRole.FAST

    asyncio.run(scenario())


def test_graph_uses_prepared_wake_reaction_without_model_generation() -> None:
    class Prepared:
        def next_wake_reaction(self) -> str:
            return "Listening."

        def next_acknowledgement_reaction(self) -> None:
            return None

        def next_wait_reaction(self) -> None:
            return None

    async def scenario() -> None:
        adapter = FakeLanguageModel()
        async with LanguageModelService(adapter) as service:
            graph = ConversationGraph(
                ConversationNodes(service, profile_preparation=Prepared())
            ).compiled
            events = [
                event
                async for event in graph.astream(
                    {"messages": [], "input_kind": "activation"},
                    context=context(),
                    stream_mode="custom",
                )
            ]
        assert events == [ConversationTextChunk("Listening.\n")]
        assert adapter.requests == []

    asyncio.run(scenario())


class FakeCompiled:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    async def astream(self, **kwargs: Any) -> AsyncIterator[ConversationTextChunk]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        yield SimpleNamespace(content="ignored")
        yield ConversationTextChunk("")
        yield ConversationTextChunk("Hello\n", PreparedReactionKind.ACKNOWLEDGEMENT)
        yield ConversationTextChunk("world")

    async def ainvoke(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return {}


class FakeGraph:
    def __init__(self, compiled: FakeCompiled) -> None:
        self.compiled = compiled


def test_worker_streams_chunks_phrases_and_inputs() -> None:
    async def scenario() -> None:
        bus = EventBus()
        compiled = FakeCompiled()
        worker = Worker(bus, FakeGraph(compiled), context())
        with bus.subscribe(
            ReplyGenerationStarted,
            ReplyChunk,
            ReplyPhrase,
            ReplyGenerationCompleted,
        ) as replies:
            task = asyncio.create_task(worker.run())
            await asyncio.wait_for(_wait_until(lambda: len(bus._subscriptions) == 2), 1)
            bus.publish(GenerateReply(ConversationActivated()))
            received = []
            while not any(
                isinstance(event, ReplyGenerationCompleted) for event in received
            ):
                event = await asyncio.wait_for(replies.__anext__(), 1)
                received.append(event)
                replies.task_done()
            assert received == [
                ReplyGenerationStarted(1),
                ReplyChunk(1, "Hello\n"),
                ReplyPhrase(1, 1, "Hello", PreparedReactionKind.ACKNOWLEDGEMENT),
                ReplyChunk(1, "world"),
                ReplyPhrase(1, 2, "world"),
                ReplyGenerationCompleted(1),
            ]
            bus.publish(GenerateReply(UserTurn("Question")))
            while not isinstance(
                event := await asyncio.wait_for(replies.__anext__(), 1),
                ReplyGenerationCompleted,
            ):
                replies.task_done()
            replies.task_done()
            bus.publish(ShutdownEvent())
            await asyncio.wait_for(task, 1)

        assert compiled.calls[0]["input"]["input_kind"] == "activation"
        assert compiled.calls[1]["input"]["messages"] == [HumanMessage("Question")]
        assert compiled.calls[0]["stream_mode"] == "custom"

    asyncio.run(scenario())


def test_worker_cancels_active_and_queued_replies() -> None:
    class BlockingCompiled(FakeCompiled):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def astream(self, **kwargs: Any) -> AsyncIterator[ConversationTextChunk]:
            self.calls.append(kwargs)
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
            if False:
                yield ConversationTextChunk("")

    async def scenario() -> None:
        bus = EventBus()
        compiled = BlockingCompiled()
        worker = Worker(bus, FakeGraph(compiled), context())
        with bus.subscribe(ReplyGenerationStarted, ReplyGenerationCompleted) as replies:
            task = asyncio.create_task(worker.run())
            await asyncio.wait_for(_wait_until(lambda: len(bus._subscriptions) == 2), 1)
            bus.publish(GenerateReply(UserTurn("Question")))
            assert isinstance(await replies.__anext__(), ReplyGenerationStarted)
            replies.task_done()
            await compiled.started.wait()
            bus.publish(CancelReply("Delivered phrase."))
            await asyncio.wait_for(compiled.cancelled.wait(), 1)
            assert isinstance(await replies.__anext__(), ReplyGenerationCompleted)
            replies.task_done()
            assert "Delivered phrase." in worker._delivery_context
            bus.publish(ShutdownEvent())
            await asyncio.wait_for(task, 1)

        queued = Worker(EventBus(), FakeGraph(FakeCompiled()), context())
        queued._graph_queue.put_nowait(UserTurn("Obsolete"))
        await queued._cancel_reply("", None)
        await queued._graph_queue.join()
        await queued._stream(1, UserTurn("Next"))
        assert (
            "before any part was delivered"
            in (queued._graph.compiled.calls[0]["input"]["delivery_context"])
        )

        stale = Worker(EventBus(), FakeGraph(FakeCompiled()), context())
        stale._active_reply_id = 2
        stale._last_reply_id = 1
        await stale._cancel_reply("old reply", 1)
        assert stale._delivery_context == ""

    asyncio.run(scenario())


def test_worker_propagates_graph_failure_after_completion() -> None:
    async def scenario() -> None:
        bus = EventBus()
        worker = Worker(
            bus, FakeGraph(FakeCompiled(error=RuntimeError("graph"))), context()
        )
        with bus.subscribe(ReplyGenerationStarted, ReplyGenerationCompleted) as replies:
            task = asyncio.create_task(worker.run())
            await asyncio.wait_for(_wait_until(lambda: len(bus._subscriptions) == 2), 1)
            bus.publish(GenerateReply(UserTurn("Question")))
            assert isinstance(await replies.__anext__(), ReplyGenerationStarted)
            replies.task_done()
            assert isinstance(await replies.__anext__(), ReplyGenerationCompleted)
            replies.task_done()
            with pytest.raises(ExceptionGroup) as raised:
                await task
            assert any(
                isinstance(error, RuntimeError) and str(error) == "graph"
                for error in raised.value.exceptions
            )

    asyncio.run(scenario())


def test_worker_treats_profile_preparation_as_optional() -> None:
    class Preparation:
        def __init__(self, error: Exception | None = None) -> None:
            self.error = error
            self.called = False

        async def prepare(self) -> None:
            self.called = True
            if self.error is not None:
                raise self.error

    async def scenario() -> None:
        worker = Worker(EventBus(), FakeGraph(FakeCompiled()), context())
        await worker._prepare_profile()

        successful = Preparation()
        worker._profile_preparation = successful
        await worker._prepare_profile()
        assert successful.called

        failing = Preparation(RuntimeError("profile preparation failed"))
        worker._profile_preparation = failing
        with pytest.raises(RuntimeError, match="profile preparation failed"):
            await worker._prepare_profile()
        assert failing.called

    asyncio.run(scenario())


def test_langchain_adapter_maps_messages_and_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeChat:
        def stream(self, messages):
            assert [message.type for message in messages] == ["system", "human"]
            yield SimpleNamespace(text="answer")

    def init_chat_model(model: str, **kwargs: Any) -> FakeChat:
        calls.append((model, kwargs))
        return FakeChat()

    monkeypatch.setattr("langchain.chat_models.init_chat_model", init_chat_model)
    adapter = LangChainLanguageModel(
        profile().models_langchain,
        LangChainSettings(),
    )
    with adapter:
        adapter.prepare(LanguageModelRole.FAST)
        chunks = list(
            adapter.generate(
                LanguageModelRequest(
                    LanguageModelRole.FAST,
                    (
                        ConversationMessage(ConversationRole.SYSTEM, "system"),
                        ConversationMessage(ConversationRole.USER, "question"),
                    ),
                )
            )
        )
    assert chunks == [LanguageModelChunk("answer")]
    assert calls[0][0] == "test/fast"
    assert calls[0][1]["num_predict"] == 96
    assert calls[0][1]["reasoning"] is False

    ollama_profile = profile().models_langchain.model_copy(
        update={
            "fast": LangChainModelProfile(
                model_id="ollama:gpt-oss:20b",
                max_tokens=96,
            )
        }
    )
    with LangChainLanguageModel(
        ollama_profile,
        LangChainSettings(base_url="http://test.local"),
    ) as ollama_adapter:
        ollama_adapter.prepare(LanguageModelRole.FAST)
    assert calls[1][1]["reasoning"] == "low"
    assert calls[1][1]["base_url"] == "http://test.local"


def test_mlx_adapter_loads_lazily_and_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {
        "templates": [],
        "cache_count": 0,
        "models": [],
        "generations": [],
    }

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            calls["templates"].append((messages, kwargs))
            return (
                f"{messages[0]['content']}-prompt"
                if len(messages) > 1
                else messages[0]["content"]
            )

        def encode(self, text):
            return [ord(character) for character in text]

    mlx_lm = ModuleType("mlx_lm")
    loaded_model = "loaded-model"

    def load(model):
        calls["models"].append(model)
        return loaded_model, Tokenizer()

    mlx_lm.load = load

    def stream_generate(*args, **kwargs):
        calls["generations"].append(kwargs)
        for text in (
            "<|",
            "channel>thought\n",
            "internal reasoning",
            "<channel|>",
            "chunk",
        ):
            yield SimpleNamespace(text=text)

    mlx_lm.stream_generate = stream_generate
    mlx = ModuleType("mlx")
    mlx_core = ModuleType("mlx.core")
    mlx_core.array = lambda value: value
    mlx.core = mlx_core
    generate = ModuleType("mlx_lm.generate")
    generate.generate_step = lambda *args, **kwargs: iter(())
    models = ModuleType("mlx_lm.models")
    cache = ModuleType("mlx_lm.models.cache")

    def make_prompt_cache(model):
        calls["cache_count"] += 1
        return {"model": model}

    cache.make_prompt_cache = make_prompt_cache
    sample_utils = ModuleType("mlx_lm.sample_utils")
    sample_utils.make_sampler = lambda **kwargs: calls.setdefault("sampler", kwargs)
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", mlx_core)
    monkeypatch.setitem(sys.modules, "mlx_lm", mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.generate", generate)
    monkeypatch.setitem(sys.modules, "mlx_lm.models", models)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", cache)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", sample_utils)

    models = profile().models_mlx.model_copy(
        update={
            "fast": MLXModelProfile(model_id="test/detailed", max_tokens=96),
        }
    )
    adapter = MLXLanguageModel(models)
    with adapter:
        chunks = list(
            adapter.generate(
                LanguageModelRequest(
                    LanguageModelRole.DETAILED,
                    (
                        ConversationMessage(ConversationRole.SYSTEM, "system"),
                        ConversationMessage(ConversationRole.USER, "question"),
                    ),
                    cache_prefix="system",
                    tools=(ToolDefinition("demo", "Demo tool", {"type": "object"}),),
                )
            )
        )
        _ = list(
            adapter.generate(
                LanguageModelRequest(
                    LanguageModelRole.DETAILED,
                    (
                        ConversationMessage(
                            ConversationRole.SYSTEM, "system\nsummary changed"
                        ),
                        ConversationMessage(ConversationRole.USER, "question"),
                    ),
                    cache_prefix="system",
                )
            )
        )
        _ = list(
            adapter.generate(
                LanguageModelRequest(
                    LanguageModelRole.FAST,
                    (ConversationMessage(ConversationRole.USER, "question"),),
                )
            )
        )
    assert chunks == [LanguageModelChunk("chunk")]
    assert calls["models"] == ["test/detailed"]
    assert calls["generations"][0]["max_tokens"] == 256
    assert calls["templates"][0][0] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
    ]
    assert calls["templates"][0][1]["enable_thinking"] is False
    assert calls["cache_count"] == 1
    assert calls["generations"][0]["prompt"] == [
        ord(character) for character in "-prompt"
    ]
    assert calls["generations"][0]["prompt_cache"] == {"model": loaded_model}
    assert calls["generations"][1]["prompt"] == [
        ord(character) for character in "\nsummary changed-prompt"
    ]


def test_mlx_adapter_generates_without_unsupported_system_prefix_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated: dict[str, Any] = {}

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            if len(messages) == 1:
                raise RuntimeError("A user message is required")
            return "complete-prompt"

        def encode(self, text):
            return [1]

    mlx_lm = ModuleType("mlx_lm")
    mlx_lm.load = lambda model: (object(), Tokenizer())

    def stream_generate(*args, **kwargs):
        generated.update(kwargs)
        yield SimpleNamespace(text="answer")

    mlx_lm.stream_generate = stream_generate
    mlx = ModuleType("mlx")
    mlx_core = ModuleType("mlx.core")
    mlx_core.array = lambda value: value
    mlx.core = mlx_core
    generate = ModuleType("mlx_lm.generate")
    generate.generate_step = lambda *args, **kwargs: iter(())
    models = ModuleType("mlx_lm.models")
    cache = ModuleType("mlx_lm.models.cache")
    cache.make_prompt_cache = lambda model: object()
    sample_utils = ModuleType("mlx_lm.sample_utils")
    sample_utils.make_sampler = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", mlx_core)
    monkeypatch.setitem(sys.modules, "mlx_lm", mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.generate", generate)
    monkeypatch.setitem(sys.modules, "mlx_lm.models", models)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", cache)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", sample_utils)

    adapter = MLXLanguageModel(profile().models_mlx)
    with adapter:
        chunks = list(
            adapter.generate(
                LanguageModelRequest(
                    LanguageModelRole.FAST,
                    (
                        ConversationMessage(ConversationRole.SYSTEM, "system"),
                        ConversationMessage(ConversationRole.USER, "question"),
                    ),
                )
            )
        )

    assert chunks == [LanguageModelChunk("answer")]
    assert generated["prompt"] == "complete-prompt"
    assert generated["prompt_cache"] is None


def test_adapter_factory_and_public_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(
        get_language_model(profile(), LangChainSettings()),
        LangChainLanguageModel,
    )
    assert isinstance(
        get_language_model(profile(), MLXSettings()),
        MLXLanguageModel,
    )
    with pytest.raises(ValueError, match="Unsupported"):
        get_language_model(profile(), SimpleNamespace(adapter="unknown"))
    incomplete = profile().model_copy(
        update={
            "models": {"fast": {"model_id": "only"}},
        }
    )
    with pytest.raises(ValidationError, match="detailed"):
        get_language_model(incomplete, MLXSettings())
    no_classifier = profile().model_copy(
        update={
            "models": {
                "fast": {"model_id": "test/fast"},
                "detailed": {"model_id": "test/detailed"},
            }
        }
    )
    with pytest.raises(ValueError, match="requires a classifier"):
        get_language_model(
            no_classifier,
            LangChainSettings(),
            require_classifier=True,
        )

    async def scenario() -> None:
        calls: list[Worker] = []
        fake_model = FakeLanguageModel("One.\nTwo.")

        async def fake_run(self: Worker) -> None:
            calls.append(self)

        monkeypatch.setattr(Worker, "run", fake_run)
        monkeypatch.setattr(
            model_module,
            "get_language_model",
            lambda *_, **__: fake_model,
        )
        await run_conversation_worker(EventBus(), profile(), ConversationSettings())
        assert len(calls) == 1
        assert isinstance(calls[0]._graph, ConversationGraph)

    asyncio.run(scenario())


def test_studio_uses_default_profile_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import helomi.conversation.studio as studio_module

    conversation_profile = profile()
    conversation_settings = ConversationSettings()
    fake_model = FakeLanguageModel()
    calls: list[tuple[str, object, object, bool]] = []

    class FakeStore:
        def load_default_profile(self) -> SimpleNamespace:
            calls.append(("profile", None, None, False))
            return SimpleNamespace(conversation=conversation_profile)

        def load_settings(self) -> SimpleNamespace:
            calls.append(("settings", None, None, False))
            return SimpleNamespace(conversation=conversation_settings)

    def fake_get_language_model(
        profile_value: ConversationProfile,
        settings_value: object,
        *,
        require_classifier: bool = False,
    ) -> FakeLanguageModel:
        calls.append(
            (
                "adapter",
                profile_value,
                settings_value,
                require_classifier,
            )
        )
        return fake_model

    monkeypatch.setattr(studio_module, "LocalStore", FakeStore)
    monkeypatch.setattr(
        studio_module,
        "get_language_model",
        fake_get_language_model,
    )

    async def scenario() -> None:
        async with studio_module.conversation_graph() as graph:
            assert set(graph.nodes) == {
                "__start__",
                "opening",
                "reply",
                "summarize",
                "background_result",
            }

    asyncio.run(scenario())
    assert calls == [
        ("profile", None, None, False),
        ("settings", None, None, False),
        (
            "adapter",
            conversation_profile,
            conversation_settings.language_model,
            True,
        ),
    ]


async def _wait_until(predicate) -> None:
    while not predicate():
        await asyncio.sleep(0)
