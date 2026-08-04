import asyncio
from contextlib import suppress

from langchain.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from helomi.common.components import Component
from helomi.common.events import EventBus, ShutdownEvent

from .events import (
    BackgroundResult,
    CancelReply,
    ConversationActivated,
    ConversationInput,
    ConversationReady,
    GenerateReply,
    QuitRequested,
    ReplyChunk,
    ReplyDraftUpdated,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyId,
    ReplyPhrase,
    UserTurn,
)
from .graph import ConversationContext, ConversationGraph
from .profile import ProfilePreparation
from .reply import ConversationQuit, ConversationTextChunk, ReplySegmenter


class Worker(Component):
    THREAD_ID = "helomi"

    def __init__(
        self,
        event_bus: EventBus,
        graph: ConversationGraph,
        context: ConversationContext,
        profile_preparation: ProfilePreparation | None = None,
        start_event: asyncio.Event | None = None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._graph = graph
        self._context = context
        self._profile_preparation = profile_preparation
        self._graph_queue: asyncio.Queue[tuple[ConversationInput, bool]] = (
            asyncio.Queue()
        )
        self._active_reply: asyncio.Task[None] | None = None
        self._active_reply_id: ReplyId | None = None
        self._last_reply_id: ReplyId | None = None
        self._maintenance_task: asyncio.Task[None] | None = None
        self._delivery_context = ""
        self._shutdown_event = asyncio.Event()
        self._start_event = start_event
        self._events_ready = asyncio.Event()
        self._reply_sequence = 0
        self._logger.debug("INITIALIZED")

    async def run(self) -> None:
        self._logger.debug("Starting tasks")

        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(self._events_loop()),
                group.create_task(self._graph_loop()),
            ]
            await self._events_ready.wait()
            await self._prepare_profile()
            self._event_bus.publish(ConversationReady())

            if self._start_event is not None:
                await self._start_event.wait()

            await self._shutdown_event.wait()
            self._logger.debug("Canceling tasks")

            await self._preempt_maintenance()
            for task in tasks:
                task.cancel()

    async def _prepare_profile(self) -> None:
        preparation = self._profile_preparation
        if preparation is None:
            return
        await preparation.prepare()

    async def _events_loop(self) -> None:
        with self._event_bus.subscribe(
            CancelReply,
            GenerateReply,
            ShutdownEvent,
        ) as events:
            self._events_ready.set()
            async for event in events:
                try:
                    match event:
                        case GenerateReply(input, protected_delivery):
                            await self._preempt_maintenance()
                            self._graph_queue.put_nowait((input, protected_delivery))
                        case CancelReply(spoken_text, reply_id):
                            await self._cancel_reply(spoken_text, reply_id)
                        case ShutdownEvent():
                            await self._preempt_maintenance()
                            self._shutdown_event.set()
                finally:
                    events.task_done()

    async def _graph_loop(self) -> None:
        while not self._shutdown_event.is_set():
            conversation_input, protected_delivery = await self._graph_queue.get()
            reply_id = self._next_reply_id()
            completed = False

            try:
                self._event_bus.publish(
                    ReplyGenerationStarted(reply_id, protected_delivery)
                )
                self._active_reply_id = reply_id
                self._active_reply = asyncio.create_task(
                    self._stream(reply_id, conversation_input)
                )
                try:
                    await self._active_reply
                    completed = True
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise
            finally:
                self._active_reply = None
                self._active_reply_id = None
                self._last_reply_id = reply_id
                self._event_bus.publish(ReplyGenerationCompleted(reply_id))
                self._graph_queue.task_done()
            if (
                completed
                and isinstance(conversation_input, UserTurn)
                and not self._shutdown_event.is_set()
            ):
                self._maintenance_task = asyncio.create_task(self._summarize())

    async def _cancel_reply(self, spoken_text: str, reply_id: ReplyId | None) -> None:
        if reply_id is not None:
            expected_reply_id = (
                self._active_reply_id
                if self._active_reply_id is not None
                else self._last_reply_id
            )
            if reply_id != expected_reply_id:
                return
        await self._preempt_maintenance()
        active_reply = self._active_reply
        if active_reply is not None:
            active_reply.cancel()
            with suppress(asyncio.CancelledError):
                await active_reply

        while True:
            try:
                self._graph_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                self._graph_queue.task_done()

        self._delivery_context = (
            # The next graph run receives delivery state as input instead of
            # mutating a checkpoint while its current run is being cancelled.
            "The previous answer was interrupted. The user heard only this "
            f"prefix: {spoken_text!r}. Do not assume they heard the remainder."
            if spoken_text
            else "The previous answer was interrupted before any part was delivered. "
            "Do not assume the user heard it."
        )

    async def _preempt_maintenance(self) -> None:
        maintenance = self._maintenance_task
        if maintenance is None:
            return
        self._maintenance_task = None
        maintenance.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance

    async def _summarize(self) -> None:
        config: RunnableConfig = {"configurable": {"thread_id": self.THREAD_ID}}
        await self._graph.compiled.ainvoke(
            input={"input_kind": "maintenance", "messages": []},
            config=config,
            context=self._context,
        )

    async def _stream(
        self,
        reply_id: ReplyId,
        conversation_input: ConversationInput,
    ) -> None:
        delivery_context, self._delivery_context = self._delivery_context, ""
        match conversation_input:
            case ConversationActivated():
                graph_input = {
                    "delivery_context": delivery_context,
                    "input_kind": "activation",
                    "messages": [],
                }
            case UserTurn(text):
                graph_input = {
                    "delivery_context": delivery_context,
                    "input_kind": "user_turn",
                    "messages": [HumanMessage(content=text)],
                }
            case BackgroundResult(tool_name, content, failed):
                graph_input = {
                    "delivery_context": delivery_context,
                    "input_kind": "background_result",
                    "messages": [
                        HumanMessage(
                            content=(
                                f"Background tool {'failed' if failed else 'result'} "
                                f"from {tool_name}: {content}"
                            )
                        )
                    ],
                }

        config: RunnableConfig = {
            "configurable": {"thread_id": self.THREAD_ID},
        }
        segmenter = ReplySegmenter()
        phrase_id = 0
        quit_requested = False

        async for event in self._graph.compiled.astream(
            input=graph_input,
            config=config,
            context=self._context,
            stream_mode="custom",
        ):
            if isinstance(event, ConversationQuit):
                quit_requested = True
                continue
            if not isinstance(event, ConversationTextChunk):
                continue

            chunk = event.content
            if not chunk:
                continue

            self._event_bus.publish(ReplyChunk(reply_id=reply_id, text=chunk))
            for phrase in segmenter.feed(chunk):
                phrase_id += 1
                self._event_bus.publish(
                    ReplyPhrase(
                        reply_id=reply_id,
                        phrase_id=phrase_id,
                        text=phrase,
                    )
                )
            self._event_bus.publish(
                ReplyDraftUpdated(reply_id=reply_id, text=segmenter.draft)
            )

        for phrase in segmenter.flush():
            phrase_id += 1
            self._event_bus.publish(
                ReplyPhrase(
                    reply_id=reply_id,
                    phrase_id=phrase_id,
                    text=phrase,
                )
            )
        self._event_bus.publish(ReplyDraftUpdated(reply_id=reply_id, text=""))
        if quit_requested:
            self._event_bus.publish(QuitRequested(reply_id, phrase_id))

    def _next_reply_id(self) -> ReplyId:
        self._reply_sequence += 1
        return self._reply_sequence
