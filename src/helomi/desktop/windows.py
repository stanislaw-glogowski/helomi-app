from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from helomi.app import ProgressStatus

from .state import AssistantMessage, DesktopSnapshot, PhraseState, UserMessage


@dataclass(slots=True)
class _WindowContent:
    window: Any
    title: Any
    subtitle: Any
    text: Any
    centered: bool = False


class DesktopWindows:
    """Native utility windows, constructed only when a user opens one."""

    _HEADER_HEIGHT = 92
    _PADDING = 18

    def __init__(self) -> None:
        self._appkit: Any | None = None
        self._snapshot: DesktopSnapshot | None = None
        self._conversation: _WindowContent | None = None
        self._system: _WindowContent | None = None
        self._conversation_rendered: DesktopSnapshot | None = None
        self._system_rendered: DesktopSnapshot | None = None

    def update(self, snapshot: DesktopSnapshot) -> None:
        self._snapshot = snapshot
        if self._conversation is not None and snapshot != self._conversation_rendered:
            self._render_conversation(snapshot)
        if self._system is not None and snapshot != self._system_rendered:
            self._render_system(snapshot)

    def show_conversation(self) -> None:  # pragma: no cover - requires AppKit
        if self._conversation is None:
            self._conversation = self._make_window("Conversation", 700, 600)
            self._render_conversation(self._current_snapshot())
        self._show(self._conversation)

    def show_system_info(self) -> None:  # pragma: no cover - requires AppKit
        if self._system is None:
            self._system = self._make_window("System Info", 660, 650)
            self._render_system(self._current_snapshot())
        self._show(self._system)

    def _current_snapshot(self) -> DesktopSnapshot:
        if self._snapshot is None:
            raise RuntimeError("Desktop windows require an initial snapshot")
        return self._snapshot

    @property
    def _kit(self) -> Any:  # pragma: no cover - requires AppKit
        if self._appkit is None:
            self._appkit = cast(Any, import_module("AppKit"))
        return self._appkit

    def _make_window(  # pragma: no cover - requires AppKit
        self, title: str, width: float, height: float
    ) -> _WindowContent:
        appkit = self._kit
        frame = appkit.NSMakeRect(0, 0, width, height)
        style = (
            appkit.NSWindowStyleMaskTitled
            | appkit.NSWindowStyleMaskClosable
            | appkit.NSWindowStyleMaskMiniaturizable
            | appkit.NSWindowStyleMaskResizable
            | appkit.NSWindowStyleMaskFullSizeContentView
        )
        window = appkit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, appkit.NSBackingStoreBuffered, False
        )
        window.setTitle_(title)
        window.setReleasedWhenClosed_(False)
        window.setTitleVisibility_(appkit.NSWindowTitleHidden)
        window.setTitlebarAppearsTransparent_(True)
        window.setMovableByWindowBackground_(True)

        effect = appkit.NSVisualEffectView.alloc().initWithFrame_(frame)
        effect.setMaterial_(appkit.NSVisualEffectMaterialUnderWindowBackground)
        effect.setBlendingMode_(appkit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(appkit.NSVisualEffectStateActive)
        effect.setAutoresizingMask_(
            appkit.NSViewWidthSizable | appkit.NSViewHeightSizable
        )
        window.setContentView_(effect)

        header = appkit.NSVisualEffectView.alloc().initWithFrame_(
            appkit.NSMakeRect(
                self._PADDING,
                height - self._HEADER_HEIGHT - 12,
                width - 36,
                self._HEADER_HEIGHT,
            )
        )
        header.setMaterial_(appkit.NSVisualEffectMaterialHeaderView)
        header.setState_(appkit.NSVisualEffectStateActive)
        header.setWantsLayer_(True)
        header.layer().setCornerRadius_(14)
        header.setAutoresizingMask_(appkit.NSViewWidthSizable | appkit.NSViewMinYMargin)
        effect.addSubview_(header)

        heading = appkit.NSTextField.labelWithString_("")
        heading.setFrame_(appkit.NSMakeRect(18, 43, width - 72, 30))
        heading.setFont_(
            appkit.NSFont.systemFontOfSize_weight_(22, appkit.NSFontWeightSemibold)
        )
        heading.setAutoresizingMask_(appkit.NSViewWidthSizable)
        header.addSubview_(heading)
        subtitle = appkit.NSTextField.labelWithString_("")
        subtitle.setFrame_(appkit.NSMakeRect(20, 18, width - 76, 20))
        subtitle.setFont_(appkit.NSFont.systemFontOfSize_(13))
        subtitle.setTextColor_(appkit.NSColor.secondaryLabelColor())
        subtitle.setLineBreakMode_(appkit.NSLineBreakByTruncatingTail)
        subtitle.setAutoresizingMask_(appkit.NSViewWidthSizable)
        header.addSubview_(subtitle)

        scroll = appkit.NSScrollView.alloc().initWithFrame_(
            appkit.NSMakeRect(
                self._PADDING,
                self._PADDING,
                width - 36,
                height - self._HEADER_HEIGHT - 48,
            )
        )
        scroll.setAutoresizingMask_(
            appkit.NSViewWidthSizable | appkit.NSViewHeightSizable
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setDrawsBackground_(False)
        text = appkit.NSTextView.alloc().initWithFrame_(scroll.bounds())
        text.setEditable_(False)
        text.setSelectable_(True)
        text.setRichText_(False)
        text.setDrawsBackground_(False)
        text.setFont_(appkit.NSFont.systemFontOfSize_(14))
        text.setTextColor_(appkit.NSColor.labelColor())
        text.setTextContainerInset_(appkit.NSMakeSize(16, 16))
        text.setAutoresizingMask_(appkit.NSViewWidthSizable)
        scroll.setDocumentView_(text)
        effect.addSubview_(scroll)
        return _WindowContent(window, heading, subtitle, text)

    def _show(self, content: _WindowContent) -> None:
        if not content.centered:
            content.window.center()
            content.centered = True
        content.window.makeKeyAndOrderFront_(None)
        self._kit.NSApp.activateIgnoringOtherApps_(True)

    def _render_conversation(  # pragma: no cover - requires AppKit
        self, snapshot: DesktopSnapshot
    ) -> None:
        assert self._conversation is not None
        self._set_header(self._conversation, snapshot)
        text = self._conversation.text
        scroll = text.enclosingScrollView()
        visible = scroll.contentView().documentVisibleRect()
        document = text.bounds()
        follows_latest = (
            visible.origin.y + visible.size.height >= document.size.height - 2
        )
        text.setString_(self._conversation_text_value(snapshot))
        self._style_sections(
            text,
            (snapshot.profile_name, "You", "🎙️ Listening"),
        )
        if follows_latest:
            text.scrollRangeToVisible_(self._kit.NSMakeRange(len(text.string()), 0))
        self._conversation_rendered = snapshot

    def _render_system(self, snapshot: DesktopSnapshot) -> None:
        assert self._system is not None
        self._set_header(self._system, snapshot)
        self._system.text.setString_(self._system_text_value(snapshot))
        self._style_sections(
            self._system.text,
            ("Signals", "Runtime Pipeline", "Latency", "Startup Progress"),
        )
        self._system_rendered = snapshot

    def _style_sections(  # pragma: no cover - requires AppKit text storage
        self, text: Any, headings: tuple[str, ...]
    ) -> None:
        """Apply lightweight card-like hierarchy without custom drawing code."""
        storage = text.textStorage()
        value = str(text.string())
        for heading in headings:
            start = 0
            while (index := value.find(heading, start)) >= 0:
                storage.addAttribute_value_range_(
                    self._kit.NSFontAttributeName,
                    self._kit.NSFont.systemFontOfSize_weight_(
                        15, self._kit.NSFontWeightSemibold
                    ),
                    self._kit.NSMakeRange(index, len(heading)),
                )
                storage.addAttribute_value_range_(
                    self._kit.NSForegroundColorAttributeName,
                    self._kit.NSColor.controlAccentColor(),
                    self._kit.NSMakeRange(index, len(heading)),
                )
                start = index + len(heading)

    @staticmethod
    def _set_header(content: _WindowContent, snapshot: DesktopSnapshot) -> None:
        content.title.setString_(
            f"{snapshot.agent_activity.emoji} {snapshot.profile_name}"
        )
        detail = snapshot.detail or snapshot.agent_activity.presentation
        content.subtitle.setString_(f"{snapshot.mode.presentation}  ·  {detail}")

    @staticmethod
    def _conversation_text_value(snapshot: DesktopSnapshot) -> str:
        if not snapshot.conversation.messages:
            if snapshot.waiting_for_wakeword:
                return f"👂 Waiting for “{snapshot.system_info.wakeword_label}”…"
            return "🎙️ Listening…"
        sections: list[str] = []
        for message in snapshot.conversation.messages:
            if isinstance(message, UserMessage):
                state = "🎙️ Listening" if not message.committed else "You"
                sections.append(f"{state}\n{message.text or 'Listening…'}")
                continue
            assert isinstance(message, AssistantMessage)
            phrases = "\n".join(
                f"{DesktopWindows._phrase_indicator(phrase.state)} {phrase.text}"
                for phrase in message.phrases
            )
            draft = f"🤔 Drafting · {message.draft}" if message.draft else ""
            interrupted = "🛑 Reply interrupted" if message.interrupted else ""
            body = "\n".join(item for item in (phrases, draft, interrupted) if item)
            sections.append(f"{snapshot.profile_name}\n{body or '🤔 Thinking…'}")
        return "\n\n".join(sections)

    @staticmethod
    def _phrase_indicator(state: PhraseState) -> str:
        return {
            PhraseState.QUEUED: "💬 Queued ·",
            PhraseState.SPEAKING: "🔊 Speaking ·",
            PhraseState.DELIVERED: "✅ Delivered ·",
        }[state]

    @staticmethod
    def _system_text_value(snapshot: DesktopSnapshot) -> str:
        info = snapshot.system_info
        vad_status = "detected" if info.vad_detected else "idle"
        wakeword_status = "detected" if info.wakeword_detected else "idle"
        progress = DesktopWindows._progress_text(snapshot)
        timings = (
            "\n".join(
                f"{stage.replace('_', ' ').title()}: {elapsed:,.0f} ms"
                for stage, elapsed in info.timings
            )
            or "No interaction yet"
        )
        return "\n\n".join(
            (
                "Signals\n"
                f"VAD  {info.vad_score:.0%} · {vad_status}\n"
                f"Wake word  {info.wakeword_score:.0%} · {wakeword_status}\n"
                f"Captured  {info.captured_sample_count:,} samples",
                "Runtime Pipeline\n"
                f"Audio  {info.audio_driver}\n"
                f"Input  {info.input_device}\n"
                f"Output  {info.output_device}\n"
                f"VAD  {info.vad_adapter} · threshold {info.vad_threshold:.2f}\n"
                "Wake word  "
                f"{info.wakeword_model} · threshold {info.wakeword_threshold:.2f}\n"
                f"STT  {info.stt_adapter} · {info.stt_model}\n"
                f"LLM  {info.llm_adapter} · {info.llm_model}\n"
                f"TTS  {info.tts_adapter} · {info.tts_model}",
                f"Latency\n{timings}",
                progress,
            )
        )

    @staticmethod
    def _progress_text(snapshot: DesktopSnapshot) -> str:
        active = [
            item
            for item in snapshot.progress.items
            if item.status is ProgressStatus.ACTIVE
        ]
        if not active:
            return "Startup Progress\nReady"
        lines = []
        for item in active:
            percentage = (
                f" · {item.percentage:.0f}%" if item.percentage is not None else ""
            )
            lines.append(
                f"{item.description} · {item.completed:g} {item.unit}{percentage}"
            )
        return "Startup Progress\n" + "\n".join(lines)
