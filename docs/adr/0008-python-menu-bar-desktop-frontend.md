# ADR-0008: Python menu-bar desktop frontend

- Status: Draft
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: None

## Context

ADR-0007 introduces `helomi.app` as the reusable application lifecycle boundary,
allowing a desktop frontend to reuse startup and shutdown without depending on
Textual or duplicating worker composition.

The first desktop workflow needs a real macOS menu-bar application that displays
profiles, starts a selected profile, reports startup progress and failure,
supports retry, and shuts down cleanly. It does not need a conversation view,
telemetry panels, a persistent main window, or a separate Swift application.

`rumps` offers a small Python API over AppKit status items, but its latest
published release is old. Its compatibility with the project's Python version
and asyncio lifecycle must therefore be demonstrated before this proposal is
accepted.

## Decision or proposal

Use `rumps` for the first `helomi.desktop` menu-bar frontend, subject to the
acceptance gate below. The menu-bar status item is the application shell; there
is no persistent main window. Closing the application means selecting an
explicit **Quit Helomi** action, which requests application shutdown and awaits
completion before terminating the AppKit loop.

The first workflow will:

- display every profile supplied by `helomi.app`, with invalid profiles disabled;
- start models and devices only after the user selects a valid profile;
- present starting, running, failed, retrying, and shutting-down states;
- retry the selected profile through the same retryable application instance;
- provide clean shutdown without conversation, log, or telemetry views.

`helomi.desktop` owns the status item, menus, presentation state, native user
interaction, and translation of user actions into application commands.
`helomi.app` remains the source of profiles, lifecycle operations, events, and
shutdown completion. Desktop code does not construct resource stores, workers,
models, adapters, or audio drivers, and it does not maintain independent speech,
conversation, model, or audio-device state.

Run `rumps` and AppKit on the macOS main thread. Run the asyncio application
runtime on one desktop-owned background thread. Submit application commands
through thread-safe event-loop handoff and return their completion through
futures. Consume application and domain events on the runtime loop, translate
them into desktop presentation updates, and place those updates on a bounded
thread-safe queue drained by the main thread.

Keep this bridge concrete and desktop-owned. Do not add a generic UI framework,
dependency-injection framework, service locator, or unused port hierarchy.
Importing `helomi.desktop` or its entrypoint must not construct `rumps.App`, an
application runtime, models, Metal resources, profile stores, or audio devices.
Continue to package the initial frontend in the Python wheel and launch it
through the existing `helomi-desktop` console entrypoint rather than building a
separate macOS application bundle.

## Acceptance gate

Before changing this ADR to Accepted, verify with the project's Python 3.14
environment that:

- `rumps` and its Cocoa dependencies resolve through `uv`;
- package and entrypoint imports remain side-effect-free;
- a minimal status item starts and terminates on the AppKit main thread;
- runtime-loop command handoff, startup retry, and shutdown are deterministic;
- importing the frontend initializes no model, Metal, profile, or audio resource.

If the gate fails, keep this ADR in Draft and revise the proposal to use PyObjC
and AppKit directly. Do not silently replace `rumps` with Swift, Toga, or another
desktop framework.

## Consequences

The desktop workflow can remain small and Python-native while presenting a real
macOS menu-bar experience. It reuses the application lifecycle and keeps domain
and resource ownership unchanged. The explicit thread boundary also keeps
AppKit on its required main thread and asyncio work on one owned event loop.

The project accepts maintenance risk from an older convenience wrapper and must
test it against Python 3.14 before adoption. The first release is intentionally
less feature-rich than the CLI and is not yet distributed as a standalone
double-clickable `.app` bundle.

## Alternatives considered

- Direct PyObjC and AppKit: retained as the fallback because PyObjC supports
  Python 3.14, but not preferred initially because it requires more platform UI
  code for the same small workflow.
- A separate Swift application: rejected because it introduces a second native
  application target and a process boundary before the workflow requires one.
- Toga or another cross-platform toolkit: rejected because Helomi is currently
  macOS-specific and the first workflow only needs a menu-bar status item.
- Reuse Textual in a desktop shell: rejected because it would preserve the CLI
  as a presentation dependency rather than exercise the `helomi.app` boundary.

## References

- [ADR-0007: Reusable application runtime boundary](0007-reusable-application-runtime-boundary.md)
- [rumps on PyPI](https://pypi.org/project/rumps/)
- [PyObjC supported platforms](https://pyobjc.readthedocs.io/en/latest/supported-platforms.html)
