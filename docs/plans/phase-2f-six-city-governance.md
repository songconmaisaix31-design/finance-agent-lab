# Phase 2F Six-City Governance Plan

## Objective

Establish six independent city profiles, one shared standard pipeline profile, isolated city storage namespaces, and a business-rule governance boundary without copying `guan` business parameters to other cities.

## Scope

- Cities: `guan`, `xianghe`, `yicheng`, `yongcheng`, `queshan`, `biyang`.
- Shared pipeline profile: `standard-finance-pipeline` version `1`.
- Data root: external to Git, resolved through `FINANCE_DATA_ROOT` or explicit CLI `--root`.
- Storage namespaces: `incoming`, `staging`, `runs`, `exports`, `quarantine`, `archive` per city.

## Architecture Boundary

```text
Standard Pipeline Profile
  -> City Profile
  -> Business Rule Set
  -> City Data Namespace
```

The standard pipeline profile declares stages only. It does not contain city names, city paths, fee rates, whitelists, field aliases, or business data.

## Rule Governance

- `guan` keeps using `config/cities/guan.yaml` as the current calculation source.
- `config/rules/guan/rule-set.yaml` records that source and approval status.
- The other five cities have `rules.status: missing`; formal runs are blocked until rules are approved.
- Future shared business parameters must be represented as an approved shared rule set, not copied city YAML.

## Storage Governance

`StorageResolver` must resolve only:

```text
<finance-data-root>/<city-id>/<namespace>
```

It rejects path traversal, absolute namespace injection, symlink/reparse point escape, city/namespace mismatch, and cross-city input/output use.

## Out of Scope

- Real finance file reads.
- Real data copying, movement, cleanup, archive, or migration.
- Frontend, API, database, production run, or second-city calculation.
- Business rule approval.
