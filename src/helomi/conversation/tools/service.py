from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from helomi.conversation.profile import McpEndpoint, StdioMcpEndpoint
from helomi.resources import TextFileCatalog

from .domain import ToolCall, ToolDefinition, ToolResult


class ToolService:
    """Own built-in/MCP tools, deduplicate calls, and run background work."""

    _IMMEDIATE_TIMEOUT = 30.0
    _BACKGROUND_TIMEOUT = 300.0

    def __init__(
        self,
        text_files: TextFileCatalog,
        endpoints: tuple[McpEndpoint, ...] = (),
        *,
        on_background_result: Any = None,
    ) -> None:
        self._text_files = text_files
        self._endpoints = endpoints
        self._on_background_result = on_background_result
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[ToolDefinition, str | None, str | None]] = {}
        self._warnings: list[str] = []
        self._completed: dict[str, ToolResult] = {}
        self._inflight: dict[str, asyncio.Future[ToolResult]] = {}
        self._background: asyncio.Queue[ToolCall] = asyncio.Queue()
        self._background_task: asyncio.Task[None] | None = None

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(item[0] for item in self._tools.values())

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    async def start(self) -> None:
        await self._text_files.start()
        self._install_builtin_tools()
        self._stack = AsyncExitStack()
        for endpoint in self._endpoints:
            try:
                await self._connect(endpoint)
            except Exception as error:
                self._warnings.append(
                    f"MCP endpoint '{endpoint.id}' is unavailable: {error}"
                )
        self._background_task = asyncio.create_task(
            self._background_loop(), name="helomi-mcp-background"
        )

    async def stop(self) -> None:
        if self._background_task is not None:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        self._drain_background()
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._sessions.clear()
        await self._text_files.stop()

    def definition(self, name: str) -> ToolDefinition | None:
        item = self._tools.get(name)
        return item[0] if item else None

    async def execute(self, call: ToolCall) -> ToolResult:
        if completed := self._completed.get(call.id):
            return completed
        if inflight := self._inflight.get(call.id):
            return await asyncio.shield(inflight)
        task = asyncio.create_task(self._execute_once(call))
        self._inflight[call.id] = task
        try:
            result = await task
            self._completed[call.id] = result
            return result
        finally:
            self._inflight.pop(call.id, None)

    async def enqueue(self, call: ToolCall) -> None:
        definition = self.definition(call.name)
        if definition is None:
            raise ValueError(f"Tool does not exist: {call.name}")
        if definition.mode != "background":
            raise ValueError(f"Tool is not a background tool: {call.name}")
        await self._background.put(call)

    async def _connect(self, endpoint: McpEndpoint) -> None:
        if self._stack is None:
            raise RuntimeError("Tool service is not started")
        if isinstance(endpoint, StdioMcpEndpoint):
            transport = await self._stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=endpoint.command,
                        args=list(endpoint.args),
                        env=self._stdio_environment(endpoint),
                        cwd=str(self._text_files.root.parent),
                    )
                )
            )
            read, write = transport
        else:
            headers = self._environment_mapping(endpoint.headers_from_env)
            client = await self._stack.enter_async_context(
                httpx.AsyncClient(headers=headers)
            )
            read, write, _ = await self._stack.enter_async_context(
                streamable_http_client(str(endpoint.url), http_client=client)
            )
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions[endpoint.id] = session
        listed = await session.list_tools()
        for tool in listed.tools:
            name = f"mcp__{endpoint.id}__{tool.name}"
            self._tools[name] = (
                ToolDefinition(
                    name=name,
                    description=tool.description or tool.name,
                    input_schema=dict(tool.inputSchema),
                    mode=endpoint.mode,
                    require_confirmation=endpoint.require_confirmation,
                ),
                endpoint.id,
                tool.name,
            )

    def _install_builtin_tools(self) -> None:
        self._tools = {
            "files_list": (
                ToolDefinition(
                    "files_list", "List available text files.", {"type": "object"}
                ),
                None,
                None,
            ),
            "file_read": (
                ToolDefinition(
                    "file_read",
                    "Read a UTF-8 text file. The .txt extension may be omitted.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": (
                                    "Relative text-file path, with optional .txt "
                                    "extension."
                                ),
                            }
                        },
                        "required": ["path"],
                    },
                ),
                None,
                None,
            ),
            "file_write": (
                ToolDefinition(
                    "file_write",
                    "Create or replace a UTF-8 text file. The .txt extension may "
                    "be omitted.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": (
                                    "Relative text-file path, with optional .txt "
                                    "extension."
                                ),
                            },
                            "content": {"type": "string"},
                            "mode": {
                                "type": "string",
                                "enum": ["create", "replace"],
                            },
                        },
                        "required": ["path", "content", "mode"],
                    },
                ),
                None,
                None,
            ),
            "app_quit": (
                ToolDefinition(
                    "app_quit",
                    "Immediately quit Helomi when the user explicitly asks to close, "
                    "quit, exit, or shut down Helomi or the app.",
                    {"type": "object"},
                ),
                None,
                None,
            ),
        }

    async def _execute_once(self, call: ToolCall) -> ToolResult:
        item = self._tools.get(call.name)
        if item is None:
            return ToolResult(call.id, f"Tool does not exist: {call.name}", True)
        _, endpoint_id, remote_name = item
        try:
            if endpoint_id is None:
                return self._execute_builtin(call)
            session = self._sessions[endpoint_id]
            timeout = (
                self._BACKGROUND_TIMEOUT
                if item[0].mode == "background"
                else self._IMMEDIATE_TIMEOUT
            )
            response = await asyncio.wait_for(
                session.call_tool(
                    remote_name or call.name,
                    arguments=call.arguments,
                ),
                timeout,
            )
            return ToolResult(
                call.id,
                self._format_mcp_result(response),
                response.isError,
            )
        except Exception as error:
            return ToolResult(call.id, f"Tool failed: {error}", True)

    def _execute_builtin(self, call: ToolCall) -> ToolResult:
        if call.name == "files_list":
            return ToolResult(call.id, json.dumps(self._text_files.list()))
        if call.name == "file_read":
            return ToolResult(
                call.id,
                self._text_files.read(str(call.arguments["path"])),
            )
        if call.name == "file_write":
            self._text_files.write(
                str(call.arguments["path"]),
                str(call.arguments["content"]),
                mode=str(call.arguments["mode"]),
            )
            return ToolResult(call.id, "Text file saved.")
        if call.name == "app_quit":
            return ToolResult(call.id, "Quit requested.", quit_requested=True)
        return ToolResult(call.id, f"Tool does not exist: {call.name}", True)

    async def _background_loop(self) -> None:
        while True:
            call = await self._background.get()
            try:
                result = await self.execute(call)
                if self._on_background_result is not None:
                    await self._on_background_result(call, result)
            finally:
                self._background.task_done()

    @staticmethod
    def _format_mcp_result(response: Any) -> str:
        text = [item.text for item in response.content if hasattr(item, "text")]
        if response.structuredContent is not None:
            text.append(json.dumps(response.structuredContent, ensure_ascii=False))
        return "\n".join(text) or "Tool returned no supported text content."

    @staticmethod
    def _environment_mapping(mapping: dict[str, str]) -> dict[str, str]:
        return {header: os.environ[name] for header, name in mapping.items()}

    @staticmethod
    def _stdio_environment(endpoint: StdioMcpEndpoint) -> dict[str, str]:
        inherited = {
            name: value
            for name in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
            if (value := os.environ.get(name)) is not None
        }
        inherited.update(
            {child: os.environ[host] for child, host in endpoint.env_from_env.items()}
        )
        return inherited

    def _drain_background(self) -> None:
        while True:
            try:
                self._background.get_nowait()
            except asyncio.QueueEmpty:
                return
            else:
                self._background.task_done()
