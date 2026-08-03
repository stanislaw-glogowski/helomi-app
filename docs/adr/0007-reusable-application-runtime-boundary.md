# ADR-0007: Reusable application runtime boundary

- Status: Accepted
- Date: 2026-08-03
- Supersedes: ADR-0001
- Superseded by: None
- Implementation: Planned extraction into `src/helomi/app`.

## Context

ADR-0001 established package ownership but also made `helomi.cli` the runtime
composition root. That couples reusable application startup and shutdown to the
Textual frontend and would require another frontend to duplicate profile
validation, worker coordination, readiness, cancellation, and teardown.

The ownership boundaries from ADR-0001 remain valid: speech owns voice behavior,
conversation owns graph execution, resources owns local resource discovery,
common owns shared primitives, and frontends own their presentation and user
interaction. The composition-root decision needs a narrower replacement that
preserves those boundaries.

## Decision or proposal

Introduce `helomi.app` as the reusable application composition and lifecycle
boundary. It owns local application composition, profile validation before
startup, speech and conversation worker startup, readiness coordination,
cancellation, and ordered shutdown.

Keep `helomi.cli` as a terminal presentation frontend. It owns the Textual
application shell, screens, widgets, navigation, keyboard handling, terminal
logs and telemetry presentation, and CLI-specific signal binding. Its state is
a projection of application and domain events rather than a second source of
speech, conversation, model, or audio-device state.

Domain policy and concrete adapters remain in `helomi.speech`,
`helomi.conversation`, and `helomi.resources`. The application API exposes
explicit lifecycle and event contracts, not concrete adapters. This decision
does not introduce a dependency-injection framework, service locator, or desktop
implementation.

Preserve the established runtime behavior: adapters and models load lazily at
their owning lifecycle boundaries; readiness subscriptions exist before workers
publish; both workers pass the readiness gate before processing; event and queue
acknowledgement semantics remain unchanged; startup can be retried after a
failure; cancellation propagates; and shutdown signals, awaits, closes, and
joins owned work in order.

## Consequences

Terminal behavior and the CLI entrypoint remain compatible while application
composition becomes reusable by a future frontend. Startup failures and runtime
events cross one explicit boundary, so frontends can present them without
owning worker lifecycle or domain state.

The extraction adds an application package and focused lifecycle tests. The CLI
retains frontend-specific orchestration around profile choice, retry choice, and
presentation tasks, but delegates reusable runtime operations to `helomi.app`.
Real audio devices, Apple Voice Processing, Metal execution, and model behavior
still require separate manual validation.

ADR-0002 remains authoritative for event-driven worker lifecycle and queue
semantics. ADR-0005 remains authoritative for lazy adapter and model loading.

## Alternatives considered

- Keep `helomi.cli` as the composition root: rejected because non-terminal
  frontends would have to depend on Textual code or duplicate lifecycle logic.
- Give every frontend its own runtime composition: rejected because startup,
  retry, cancellation, and shutdown behavior would drift between frontends.
- Add a dependency-injection framework or service locator: rejected because the
  runtime has a small explicit dependency graph and does not need implicit
  lookup or framework-owned lifecycles.
- Move domain policy or concrete adapters into `helomi.app`: rejected because it
  would weaken the established speech, conversation, and resource ownership
  boundaries.

## References

- [ADR-0001: Package ownership and composition](0001-package-ownership-and-composition.md)
- [ADR-0002: Event-driven worker lifecycle](0002-event-driven-worker-lifecycle.md)
- [ADR-0005: Lazy local model adapters](0005-lazy-local-model-adapters.md)
- [Architecture overview](../architecture/overview.md)
- [Lifecycle and concurrency](../architecture/lifecycle-and-concurrency.md)
