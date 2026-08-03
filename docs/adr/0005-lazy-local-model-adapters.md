# ADR-0005: Lazy local model adapters

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: Existing implementation; retrospective record.

## Context

Speech and language-model resources are heavy, device-bound, and can fail due
to missing assets or insufficient memory. Importing or loading them globally
makes startup, testing, and shutdown less predictable.

## Decision or proposal

Select adapter-specific settings through discriminated configuration and acquire
heavy local models at owned service lifecycle boundaries. Profiles contain only
fields validated by the configured adapter.

## Consequences

Tests can exercise contracts without hardware or model downloads, while startup
reports model problems at the correct boundary. Real model/Metal validation
remains a separate operational check.

## Alternatives considered

- Eager module-level loading: rejected because it makes imports expensive and
  couples tests to local machine state.
- One untyped universal profile schema: rejected because unsupported provider
  fields would survive until runtime.

## References

- [Configuration](../configuration.md)
- [Testing](../development/testing.md)
