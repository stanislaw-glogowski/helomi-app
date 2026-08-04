# ADR-0009: Profile-scoped SQLite memory

- Status: Accepted
- Date: 2026-08-04
- Supersedes: None
- Superseded by: None

## Context

Conversation history and summaries previously used an in-memory LangGraph
checkpointer, so they disappeared at process exit. Local tool files were shared
under one data-root directory, preventing profiles from owning separate user data.

## Decision or proposal

Each locale profile owns `data/` and `db/memory.db` under its fixed profile directory.
SQLite persists the profile's single LangGraph thread and a separate keyed-fact
table. Facts are changed only by explicit local tools and recalled through FTS5
search of the current user turn. Summarisation retains the configured recent
messages and compacts obsolete checkpoints after successful maintenance.

## Consequences

Profiles resume independently after restart without a network service or an
embedding model. Their local data and database files remain ignored by default.
SQLite corruption or unavailable storage fails startup rather than discarding a
user's memory. Checkpoint time-travel beyond the latest compacted state is not
available.

## Alternatives considered

- A global data and memory store: rejected because profile switching could leak
  user context and files between assistants.
- Automatic fact extraction: rejected because durable writes should be explicit.
- Embedding-based recall: deferred because FTS5 is local, deterministic, and adds
  no model dependency.
