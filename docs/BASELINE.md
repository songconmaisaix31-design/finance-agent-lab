# Project Baseline

## Purpose

`finance-agent-lab` is now positioned as a multi-city finance calculation platform. The public entrypoint is `python -m src.cli`; `guan` / 固安 is the first reference city and is loaded through explicit city configuration.

This baseline records the current engineering boundary. No business rule values were changed, no real finance file content was read, and local ignored data was inspected only by filesystem metadata.

## Current Architecture

| Area | Status | Evidence |
| --- | --- | --- |
| Public CLI entrypoint | implemented | `src/cli.py`; README usage documents `python -m src.cli plan/run` |
| Request validation and path safety | implemented | `src/pipeline_service.py` validates explicit city/input/output and refuses unsafe nesting |
| City registry/profile | implemented for `guan` | `src/city_registry.py`; `config/cities/guan.yaml` includes metadata and `rule_approval_status: unverified` |
| Versioned frontend result contract | implemented | `schemas/run-result.schema.json`; `schemas/run-manifest.schema.json`; `src/result_contract.py` |
| Legacy README entrypoint | deprecated and safe by default | `src/pipeline.py` prints deprecation guidance and does not run accounting by default |
| Current richer city reference | implemented as internal reference | `src/pipeline_guan.py:53-372` remains the most complete historical 固安-style orchestration, but is not the public API |
| Configuration loading | implemented | `src/config.py:11-23`; `config/cities/guan.yaml` |
| Manifest and file fingerprints | implemented | `src/manifest.py:8-25`, `src/manifest.py:28-66`; used by `src/pipeline_guan.py:70-84`, `src/pipeline_guan.py:350-363` |
| Field mapping | implemented, lightly tested indirectly | `src/field_mapper.py:36-99`; no direct unit tests in `tests/minimal_tests.py` |
| Data normalization | implemented | `src/normalizer.py:47-58`, `src/normalizer.py:61-146` |
| Income calculation | implemented | `src/income_calc.py:8-101`; tested by `tests/minimal_tests.py:103-119` |
| Fee calculation | implemented | `src/fee_calc.py:7-56`; tested by `tests/minimal_tests.py:124-178` |
| Crowd cost extraction | implemented and synthetic-tested | `src/crowd_cost.py:12-74`; `src/crowd_cost_contract.py`; `tests/test_crowd_cost_contract.py` |
| Cross-table reconciliation | partial | `src/reconcile.py:5-65`, `src/reconcile.py:90-120`; `src/reconcile.py:68-87` contains a placeholder body |
| Report generation | implemented and smoke-tested | `src/report.py:61-96`, `src/report.py:402-469`; public smoke tests assert report artifact generation |
| Legacy modules | partial / risky | `src/loader.py`, `src/models.py`, `src/income.py`, `src/hq_fee.py`, `src/reporter.py` use float-oriented structures or older pipeline paths |

## Data Flow

| Stage | Status | Evidence |
| --- | --- | --- |
| Input | implemented for safe public smoke boundary | `src.cli` requires explicit `--city`, `--input`, and `--output`; `src.pipeline_service` refuses unsafe path relationships |
| Read and validate | implemented for synthetic `guan` smoke | `src.field_mapper.py:80-90` fails on missing bill headers; Phase 2C tests generate synthetic workbooks |
| Standardize | implemented | `src/normalizer.py:61-146` maps rows into `NormalizedBillingRow`; invalid amounts are retained with errors |
| Business calculation | implemented / partial | Income, team fees, and crowd-cost extraction are synthetic-tested; reconciliation strategy remains partial |
| Reconcile | partial | Income and team checks exist in `src/reconcile.py:5-65`; a bill-vs-cost helper is still a placeholder at `src/reconcile.py:68-87` |
| Output | implemented | Phase 2C writes `run-manifest.json`, `result-summary.json`, `unknown-types.json`, `events.jsonl`, and report artifacts under `<output>/runs/<run-id>` |

## Module Status

| Responsibility | Status | Evidence |
| --- | --- | --- |
| Manifest / file fingerprint | implemented | `src/manifest.py:8-66`; `tests/minimal_tests.py:181-190` checks SHA-256 shape |
| Field mapping | implemented | `src/field_mapper.py:5-18`, `src/field_mapper.py:36-99`; missing required fields raise `ValueError` |
| Data standardization | implemented | `src/normalizer.py:47-58`, `src/normalizer.py:61-146`; `tests/minimal_tests.py:36-58` covers decimal parsing |
| Income calculation | implemented | `src/income_calc.py:8-101`; whitelist and unknown types tested |
| Fee calculation | implemented | `src/fee_calc.py:7-56`; HQ fee and team cost tested |
| Crowd cost extraction | implemented and synthetic-tested | Four existing buckets are covered with fully synthetic workbooks |
| Cross-table reconciliation | partial | `src/reconcile.py:68-87` is placeholder; `compare_bill_crowd_counts` exists at `src/reconcile.py:90-120` |
| Report generation | implemented and smoke-tested | `src/report.py:61-96`; `tests/test_phase2c_safe_entrypoint.py` verifies report artifact generation |
| Public pipeline orchestration | implemented for safe smoke | `src/pipeline_service.py` wraps real field mapping, normalization, income, fee, report, manifest, and contract boundaries |
| Configurable business rules | partial | City config covers many rules; legacy `src/pipeline.py` uses older config files and hard-coded run counts at `src/pipeline.py:118-122` |
| Unknown type reporting | implemented fail-closed | `src/income_calc.py:27-101`; `src/crowd_cost_contract.py`; `src/pipeline_service.py`; Phase 2C/2D tests verify blocked status |

## Business Rule Sources

| Rule / Behavior | Source | Classification | Evidence |
| --- | --- | --- | --- |
| City, agent, billing date | city config | implemented, partly tested | `config/cities/guan.yaml`; `tests/minimal_tests.py:20-29` |
| HQ fee rate | city config | implemented and tested | `src/config.py:18`; `tests/minimal_tests.py:31-33`, `tests/minimal_tests.py:124-129` |
| Team delivery unit cost | city config | implemented and tested | `src/config.py:19-20`; `tests/minimal_tests.py:31-33`, `tests/minimal_tests.py:171-178` |
| Income whitelist | city config | implemented and tested | `config/cities/guan.yaml`; `src/income_calc.py:12-43`; `tests/minimal_tests.py:103-119` |
| Unknown income type handling | code + report output | implemented and tested at function level | `src/income_calc.py:43-101`; `tests/minimal_tests.py:116-119` |
| Decimal money handling | newer modules use Decimal | implemented and tested in core path | `src/normalizer.py:47-58`; `src/income_calc.py:1-101`; `src/fee_calc.py:1-56` |
| Float money handling | legacy modules | implemented but risky / source unclear | `src/loader.py:19-28`; `src/models.py:10-24`; `src/hq_fee.py:4-12` |
| Field aliases and required headers | code constants | implemented but not config-driven | `src/field_mapper.py:5-18`; `src/field_mapper.py:30-70` |
| Header position | detection in first 10 rows | implemented, untested | `src/field_mapper.py:36-50` |
| Empty / invalid amount | code behavior | implemented and tested only for parser | `src/normalizer.py:47-58`, `src/normalizer.py:93-111`; parser tests at `tests/minimal_tests.py:36-58` |
| Crowd cost filters and category mapping | city config + existing code | implemented and synthetic-tested; approval unverified | `src/crowd_cost.py:12-74`; `config/cities/guan.yaml`; `tests/test_crowd_cost_contract.py` |
| Cross-table differences | code + config tolerance | partial | `src/reconcile.py:90-120`; `src/pipeline_guan.py:298-317` |
| Real data-derived assumptions | unknown | needs confirmation | Hard-coded file names, city/date, and fixed run names exist; business source not recorded in docs |

## Test Coverage

| Test area | Tested module | Normal path | Error path | Boundary |
| --- | --- | --- | --- | --- |
| City config | `src.config` | config loads | missing config not tested | counts of whitelist entries tested |
| Decimal parsing | `src.normalizer` | normal and negative numeric strings | empty, `None`, invalid string | comma/percent/extreme amounts not tested |
| Income calculation | `src.income_calc` | whitelist totals, refund preservation, distinct order count | unknown income type reported | duplicate order ID tested |
| HQ fee | `src.fee_calc` | 1% fee on gross total | not tested | precision beyond 2 decimals not tested |
| Team delivery cost | `src.fee_calc` | group and normal counts | unknown delivery/service not tested | duplicate orders not tested |
| Manifest hash | `src.manifest` | SHA-256 format | missing file / changed file not tested | large file not tested |

Highest-value missing tests:

| Gap | Why it matters | Evidence |
| --- | --- | --- |
| Field mapping fixture tests | Real bills can change header row or column order | `src/field_mapper.py:36-99` |
| Reconciliation tests | A helper is placeholder and count mismatch policy is business-sensitive | `src/reconcile.py:68-87`; `config/cities/guan.yaml` |
| Report content checks | Phase 2C proves report artifact generation, but not workbook business content | `src/report.py:61-96`, `src/report.py:402-469` |
| Real-input immutability | Synthetic inputs are tested; real inputs remain out of scope until business-approved dry runs | `tests/test_phase2c_safe_entrypoint.py` |

## Local Data Boundary

| Metric | Result |
| --- | ---: |
| Ignored local data/output files under `runs` | 219 |
| Ignored cache files | 7 |
| Total ignored files currently present | 226 |
| Total ignored size | 108,463,970 bytes |
| Largest ignored file | 4,414,715 bytes, `.xlsx`, under `runs` |

| Top-level location | Files | Bytes | Classification |
| --- | ---: | ---: | --- |
| `runs` | 219 | 108,418,896 | suspected run outputs and extracted/generated intermediate files |
| `src` | 6 | 31,279 | Python cache |
| `tests` | 1 | 13,795 | Python cache |

| Extension | Files | Bytes |
| --- | ---: | ---: |
| `.json` | 104 | 154,361 |
| `.csv` | 64 | 46,346,532 |
| `.xlsx` | 32 | 59,558,407 |
| `.yaml` | 12 | 34,094 |
| `.pyc` | 7 | 45,074 |
| `.png` | 4 | 2,243,941 |
| `.html` | 3 | 81,561 |

| Category | Count | Notes |
| --- | ---: | --- |
| Suspected input data | 96 | Excel/CSV/ZIP-like files, mostly generated/extracted under `runs` |
| Suspected run output | 219 | All local data/output files are under `runs` |
| Suspected logs | 0 | No `.log`, `.out`, or `.err` files found |
| Suspected temporary/cache | 7 | Python bytecode caches only |
| Suspected sensitive config | 0 | No ignored env/credential/token/key files found by metadata pattern |

All ignored local data observed in this audit is grouped under `runs`; no root-level business file was detected by metadata pattern. Current code can still write new run directories and extracted files under `runs`, and `src/pipeline_guan.py:94-109` extracts ZIP content into a run-local temp directory.

## Confirmed Risks

| Risk | Severity | Evidence |
| --- | --- | --- |
| Two pipeline generations coexist | high | `src.pipeline` is deprecated; `src.pipeline_guan.py` remains a city reference; legacy float-oriented modules remain tracked |
| Crowd-cost business meaning is unapproved | high | Bucket behavior is tested as existing behavior, with `approval_status: unverified` |
| Field mapping is code-defined, not config-driven | medium | `src/field_mapper.py:5-18` |
| Placeholder reconciliation helper remains tracked | medium | `src/reconcile.py:68-87` |
| Business source for fixed city/date/rates/file names is not recorded | medium | `config/cities/guan.yaml`; `src/pipeline_guan.py:71-75` |
| Legacy float models remain in repo | medium | `src/models.py:10-24`; `src/loader.py:19-28` |

## Unknowns Requiring Human Input

| Question | Why needed |
| --- | --- |
| Should Phase 2E harden cross-table reconciliation warnings vs failures? | Cross-table reconciliation is the next correctness gap |
| Which future city/date input contract should follow `guan`? | Phase 2C only validates `guan` |
| Are fixed rate values and whitelist entries approved business rules? | They currently come from config, but the approving source is not recorded |
| Are crowd-cost bucket mappings approved business rules? | Phase 2D verifies behavior but does not approve business meaning |
| Should unknown income or delivery types always fail formal production runs? | Phase 2C defaults to fail-closed; final business policy still needs owner approval |
| How should negative, zero, duplicated, and reversal crowd-cost rows be treated? | Phase 2D characterizes current behavior as additive/unverified |
| Should extracted files and normalized CSVs be retained in every run or optionally cleaned? | Affects local data growth and auditability |

## Candidate Next Tasks

| Candidate | Problem | Value | Scope | Main files | Acceptance criteria | Test strategy | Risk | Complexity | Business confirmation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Reconciliation policy hardening | Placeholder helper and warning/fail policies are unclear | Makes mismatch behavior explicit before real runs | Specify and test mismatch statuses/tolerance behavior | `src/reconcile.py`, `config/cities/guan.yaml`, `tests/` | Count and amount mismatch outcomes are deterministic; policies are documented/tested | Pure unit tests with Decimal dictionaries | Requires policy decisions before implementation | S-M | Confirm whether mismatches should warn or fail |

## Recommended Next Task

**Cross-table reconciliation policy hardening**

Why: the public pipeline now has safe entry and synthetic crowd-cost coverage, so the next correctness risk is ambiguous reconciliation behavior.

Recommended Phase 2E acceptance criteria:

- Reconciliation policies are explicit for mismatch warning vs failure.
- Placeholder behavior is either implemented or formally blocked with stable status.
- Synthetic tests cover matching, mismatch, tolerance, and blocked cases.
- Result contracts expose reconciliation status without implying unverified success.

Out of scope for the recommended task:

- Changing income, fee, or crowd-cost formulas.
- Reading or running real finance files.
- Adding frontend, database, external APIs, notifications, remotes, or UI.

## Phase 2E Reconciliation Contract Baseline

Phase 2E introduces a single public reconciliation contract entry:

`src.reconciliation_contract.build_reconciliation_contract`

The old `src.reconcile` helpers remain available for report compatibility, but they are not the authoritative public reconciliation boundary. The placeholder `reconcile_bill_vs_cost_table` is not promoted to authority and cross-table business reconciliation remains unimplemented until approved rule sources exist.

Implemented technical checks:

| Check id | Category | Rule source | Approval status | Status |
| --- | --- | --- | --- | --- |
| `crowd.upstream_status` | structural | technical_invariant | technical | implemented |
| `crowd.bucket_total` | arithmetic | technical_invariant | technical | implemented |
| `crowd.row_accounting` | arithmetic | technical_invariant | technical | implemented |
| `artifact.summary_manifest_consistency` | structural | technical_invariant | technical | implemented |
| `artifact.manifest_actual_consistency` | structural | technical_invariant | technical | implemented |
| `contract.run_id` | contract | technical_invariant | technical | implemented |
| `contract.city_id` | contract | technical_invariant | technical | implemented |
| `contract.status` | contract | technical_invariant | technical | implemented |
| `contract.config_hash` | contract | technical_invariant | technical | implemented |
| `contract.schema_version` | contract | technical_invariant | technical | implemented |
| `input.manifest_unchanged` | contract | technical_invariant | technical | implemented |
| `cross_table.business_rules` | cross_table | unknown | unverified | not_implemented |

Current result boundary:

- `result-summary.json` includes a `reconciliation` object under schema version `1.0`.
- `reconciliation-report.json` is a safe machine-readable copy containing run id, status, summary, checks, warnings, errors, timestamp, and engine version.
- All amount values in reconciliation checks are string-serialized Decimal values.
- Failed or blocked reconciliation prevents a `success` run status.
- Cross-table business relations do not become approved in Phase 2E.

Unimplemented business checks:

- Authoritative relationships between real business tables.
- Any approved non-zero amount tolerance.
- Negative amount, reversal, zero amount, and duplicate-row business policy beyond current characterization.
- Final business approval of fee rates, whitelists, and crowd-cost bucket rules.
