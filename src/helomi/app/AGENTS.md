# Application runtime instructions

`helomi.app` is the reusable application composition boundary. It owns local
resource discovery, profile compatibility validation, worker readiness,
startup progress, retryable runtime lifecycle, and ordered shutdown. It does
not own terminal or desktop presentation.

Keep the public surface explicit: profiles, settings, progress, lifecycle
operations, and typed event subscriptions. Do not add dependency injection or
service-location frameworks. Start event subscriptions before workers can
publish, and preserve one `task_done()` for every successful event receive.

Use fakes for workers and local stores in tests. Tests must not initialize
audio devices, models, Metal, or network downloads.
