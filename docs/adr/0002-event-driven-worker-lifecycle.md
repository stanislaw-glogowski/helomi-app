# ADR-0002: Event-driven worker lifecycle

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: Existing implementation; retrospective record.

## Context

Speech and conversation run concurrently, exchange work in both directions, and
must start and stop without losing events or leaking tasks.

## Decision or proposal

Use a typed EventBus for cross-package events, package-owned queues for internal
work, explicit readiness subscriptions before publication, and a shared
`ShutdownEvent` for coordinated teardown.

## Consequences

The CLI waits for both workers before releasing the start gate. Every received
queue item must be acknowledged exactly once, and cancellation behavior remains
visible in the owning worker.

## Alternatives considered

- Direct worker references: rejected because they couple package lifecycles.
- Unstructured background tasks: rejected because startup failure and shutdown
  would be difficult to observe and await.

## References

- [Lifecycle and concurrency](../architecture/lifecycle-and-concurrency.md)
