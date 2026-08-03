# ADR-0003: Local settings and profile contract

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: Existing implementation; retrospective record.

## Context

Assistant identity and machine/runtime selection change at different rates.
Mixing them exposes unused provider fields and makes local customization unsafe.

## Decision or proposal

Store technical adapter settings in `settings.yml` with an optional deep-merged
`settings.override.yml`. Store persona content and adapter-compatible model
overrides in fixed-layout profile directories below the local data root.

## Consequences

Configuration validation happens at the resource boundary and incompatible
profiles can be shown with actionable errors. Profile prompt and reaction paths
are stable, but fields must match the selected adapter.

## Alternatives considered

- One monolithic configuration file: rejected because local profile identity and
  runtime infrastructure would be coupled.
- Free-form prompt/resource locations: rejected because validation and profile
  discovery would be less reliable.

## References

- [Configuration](../configuration.md)
- [Profiles](../profiles.md)
