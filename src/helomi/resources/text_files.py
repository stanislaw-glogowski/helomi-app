from __future__ import annotations

import asyncio
from pathlib import Path

from watchfiles import awatch


class TextFileCatalog:
    """A watched, containment-safe catalog for Helomi user text files."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._files: tuple[str, ...] = ()
        self._watch_task: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()

    @property
    def root(self) -> Path:
        return self._root

    async def start(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._refresh()
        self._watch_task = asyncio.create_task(self._watch(), name="helomi-text-files")

    async def stop(self) -> None:
        if self._watch_task is None:
            return
        self._watch_task.cancel()
        try:
            await self._watch_task
        except asyncio.CancelledError:
            pass
        self._watch_task = None

    def list(self) -> tuple[str, ...]:
        self._refresh()
        return self._files

    def read(self, path: str) -> str:
        resolved = self._resolve(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"Text file does not exist: {path}")
        return resolved.read_text(encoding="utf-8")

    def write(self, path: str, content: str, *, mode: str) -> None:
        if mode not in {"create", "replace"}:
            raise ValueError("Text file mode must be 'create' or 'replace'")
        resolved = self._resolve(path)
        exists = resolved.exists()
        if mode == "create" and exists:
            raise FileExistsError(f"Text file already exists: {path}")
        if mode == "replace" and not exists:
            raise FileNotFoundError(f"Text file does not exist: {path}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        self._refresh()
        self._changed.set()

    async def wait_for_change(self) -> None:
        await self._changed.wait()
        self._changed.clear()

    async def _watch(self) -> None:
        async for _ in awatch(self._root):
            self._refresh()
            self._changed.set()

    def _refresh(self) -> None:
        if not self._root.is_dir():
            self._files = ()
            return
        self._files = tuple(
            sorted(
                path.relative_to(self._root).as_posix()
                for path in self._root.rglob("*.txt")
                if path.is_file() and self._contained(path)
            )
        )

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            raise ValueError("Text file path must be relative")
        if not path.suffix:
            path = path.with_suffix(".txt")
        elif path.suffix != ".txt":
            raise ValueError("Text file path must use the .txt extension")
        resolved = (self._root / path).resolve()
        if not self._contained(resolved):
            raise ValueError("Text file path must stay inside the data directory")
        return resolved

    def _contained(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._root)
        except ValueError:
            return False
        return True
