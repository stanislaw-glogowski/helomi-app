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

Store shared technical settings in root `settings.yml`, then deep-merge optional
root overrides and locale-specific settings under `locales/<language>`. Store
persona content in fixed-layout locale profile directories, with an optional
deep-merged `profile.override.yml` per profile.

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
