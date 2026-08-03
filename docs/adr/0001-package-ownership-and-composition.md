# ADR-0001: Package ownership and composition

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: Existing implementation; retrospective record.

## Context

Helomi combines real-time speech, graph-based conversation, local resources,
terminal UI, and a macOS-specific shell. Shared ownership would make lifecycle
and policy changes difficult to reason about.

## Decision or proposal

Keep `speech`, `conversation`, `resources`, `common`, `cli`, and `desktop` as
separate ownership boundaries. `cli` is the runtime composition root; `desktop`
remains a thin shell. `common` contains reusable primitives only.

## Consequences

Cross-package coordination uses explicit contracts and events. Domain policy
stays with its owner, avoiding a second runtime in tools or the desktop shell.

## Alternatives considered

- A single application package: rejected because it obscures audio and graph
  lifecycle ownership.
- UI-led composition: rejected because terminal UI state must derive from domain
  events rather than redefine domain policy.

## References

- [Architecture overview](../architecture/overview.md)
- [Root instructions](../../AGENTS.md)
