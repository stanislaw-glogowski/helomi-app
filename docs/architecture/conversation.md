# Conversation

The conversation worker owns finite graph execution, history, profile
preparation, local language-model loading, and safe phrase segmentation. It does
not own microphone capture, playback, or voice-session policy.

```mermaid
flowchart LR
  Input["ConversationActivated or UserTurn"] --> Queue["Graph queue"]
  Queue --> Graph["LangGraph run"]
  Graph --> Chunk["ReplyChunk"]
  Chunk --> Segmenter["ReplySegmenter"]
  Segmenter --> Phrase["ReplyPhrase"]
  Phrase --> Speech["Speech worker"]
  Graph --> History["Conversation state/checkpoint"]
```

One visible graph run is active at a time. The worker assigns reply identifiers,
publishes generation lifecycle events, and streams non-empty model chunks. The
segmenter emits speakable phrases while retaining an incomplete draft for the
terminal UI. After a completed user reply, summarization is a separate idle
maintenance run. A new activation, user turn, interruption, or shutdown cancels
maintenance before starting further model work.

`TurnPlanner` first handles empty input, exact cancellation phrases, explicit
response requests, explicit detailed requests, and standalone questions locally,
including common punctuation-free Polish forms produced by transcription. It sends
only ambiguous acknowledgements, corrections, follow-ups, and underspecified turns
to the local classifier. The classifier may choose no response, one clarification
question, or brief, standard, or detailed response depth; invalid output falls back
to a standard response and cannot cancel a turn.

MLX caches the stable profile system-prompt prefix. Per-turn summary, delivery
context, and response-depth instructions remain outside that cache, so changing
conversation state does not discard the expensive persona prefix. A bounded cache
falls back to full prompt generation for chat templates that cannot represent a
safe prefix.

For explicit standard and detailed requests, the graph waits up to the configured
acknowledgement delay for its first model chunk, then emits one prepared
acknowledgement when needed. Other standard and detailed turns use the longer
wait-reaction delay and its neutral wait pool. Brief responses, silence, and
cancellation remain silent; a turn emits at most one prepared reaction. Reactions
are not persisted in conversation history, and speech playback adds the configured
pause before the answer continues.

When a model selects a tool, the conversation graph routes the request through
the tool service. Immediate results return to the model in the same finite run.
Background tools enqueue one in-memory job, emit a prepared background
reaction, and later re-enter the graph as a result input. MCP sessions,
subprocesses, filesystem watching, and job execution remain outside graph state;
only the conversational result is checkpointed.
Completed background summaries use protected delivery: Helomi waits for the
current reply to finish and does not let barge-in interrupt the summary.

When speech detects barge-in, `CancelReply` cancels the active task, drains
queued inputs, and records the actually delivered prefix as context for the next
run. The reply ID prevents a stale cancellation from affecting newer generation.
This prevents the assistant from assuming that unplayed text was heard.

Language-model runtimes are acquired lazily during profile preparation. MLX is
the supplied local adapter; LangChain is an alternative for an
Ollama-compatible endpoint. Configuration and profile-role rules are documented
in [Configuration](../configuration.md).
