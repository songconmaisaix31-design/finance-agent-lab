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
| Crowd cost extraction | partial | `src/crowd_cost.py:12-74`; not covered by current tests |
| Cross-table reconciliation | partial | `src/reconcile.py:5-65`, `src/reconcile.py:90-120`; `src/reconcile.py:68-87` contains a placeholder body |
| Report generation | implemented, untested | `src/report.py:61-96`, `src/report.py:402-469`; no report tests |
| Legacy modules | partial / risky | `src/loader.py`, `src/models.py`, `src/income.py`, `src/hq_fee.py`, `src/reporter.py` use float-oriented structures or older pipeline paths |

## Data Flow

| Stage | Status | Evidence |
| --- | --- | --- |
| Input | implemented for safe public smoke boundary | `src.cli` requires explicit `--city`, `--input`, and `--output`; `src.pipeline_service` refuses unsafe path relationships |
| Read and validate | implemented for synthetic `guan` smoke | `src.field_mapper.py:80-90` fails on missing bill headers; Phase 2C tests generate synthetic workbooks |
| Standardize | implemented | `src/normalizer.py:61-146` maps rows into `NormalizedBillingRow`; invalid amounts are retained with errors |
| Business calculation | implemented / partial | Income and team fees are implemented; crowd cost and reconciliation paths exist but are not unit-tested |
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
| Crowd cost extraction | partial | `src/crowd_cost.py:12-74`; no fixture test covers filter/category behavior |
| Cross-table reconciliation | partial | `src/reconcile.py:68-87` is placeholder; `compare_bill_crowd_counts` exists at `src/reconcile.py:90-120` |
| Report generation | implemented and smoke-tested | `src/report.py:61-96`; `tests/test_phase2c_safe_entrypoint.py` verifies report artifact generation |
| Public pipeline orchestration | implemented for safe smoke | `src/pipeline_service.py` wraps real field mapping, normalization, income, fee, report, manifest, and contract boundaries |
| Configurable business rules | partial | City config covers many rules; legacy `src/pipeline.py` uses older config files and hard-coded run counts at `src/pipeline.py:118-122` |
| Unknown type reporting | implemented fail-closed | `src/income_calc.py:27-101`; `src/pipeline_service.py`; Phase 2C tests verify blocked status |

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
| Crowd cost filters and category mapping | city config | implemented but lacks tests | `src/crowd_cost.py:12-74`; `config/cities/guan.yaml` |
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
| Crowd cost extraction fixture tests | Crowd cost is a core expense path beyond the Phase 2C smoke boundary | `src/crowd_cost.py:12-74` |
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
| Core crowd-cost path lacks fixture tests | high | no tests import `src.crowd_cost` for bucket behavior |
| Field mapping is code-defined, not config-driven | medium | `src/field_mapper.py:5-18` |
| Placeholder reconciliation helper remains tracked | medium | `src/reconcile.py:68-87` |
| Business source for fixed city/date/rates/file names is not recorded | medium | `config/cities/guan.yaml`; `src/pipeline_guan.py:71-75` |
| Legacy float models remain in repo | medium | `src/models.py:10-24`; `src/loader.py:19-28` |

## Unknowns Requiring Human Input

| Question | Why needed |
| --- | --- |
| Should Phase 2D prioritize crowd-cost fixture coverage or reconciliation policy hardening? | Both are still business-critical gaps after safe entrypoint work |
| Which future city/date input contract should follow `guan`? | Phase 2C only validates `guan` |
| Are fixed rate values and whitelist entries approved business rules? | They currently come from config, but the approving source is not recorded |
| Should unknown income or delivery types always fail formal production runs? | Phase 2C defaults to fail-closed; final business policy still needs owner approval |
| Should extracted files and normalized CSVs be retained in every run or optionally cleaned? | Affects local data growth and auditability |

## Candidate Next Tasks

| Candidate | Problem | Value | Scope | Main files | Acceptance criteria | Test strategy | Risk | Complexity | Business confirmation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Safe public entrypoint and fixture smoke test | README command points to legacy absolute-path pipeline | Prevents accidental use of old local inputs and establishes a testable workflow | Align entrypoint to the authoritative pipeline, fail fast without inputs, add tiny synthetic fixtures | `README.md`, `src/pipeline.py`, `src/pipeline_guan.py`, `tests/` | No absolute local paths in default command; missing inputs fail clearly; fixture run proves outputs land under temp/run dir; existing 15 tests still pass | Generate minimal in-test workbooks/ZIPs; assert no fixture input hash changes | Could expose hidden assumptions in report/crowd-cost path | M | Confirm authoritative pipeline and default city/date |
| Crowd cost extraction fixture coverage | Expense path is core and untested | Raises confidence in cost buckets before business changes | Add fixture tests around crowd cost field detection, filtering, and category mapping | `src/crowd_cost.py`, `src/crowd_cost_fast.py`, `tests/` | Four buckets computed from synthetic workbook; missing fields fail clearly; Decimal totals preserved | Create in-memory/temp `.xlsx` fixtures only | May reveal current implementation defects; fixes should be scoped | M | Confirm expected cost-table category semantics |
| Reconciliation policy hardening | Placeholder helper and warning/fail policies are unclear | Makes mismatch behavior explicit before real runs | Specify and test mismatch statuses/tolerance behavior | `src/reconcile.py`, `config/cities/guan.yaml`, `tests/` | Count and amount mismatch outcomes are deterministic; policies are documented/tested | Pure unit tests with Decimal dictionaries | Requires policy decisions before implementation | S-M | Confirm whether mismatches should warn or fail |

## Recommended Next Task

**Safe public entrypoint and fixture smoke test**

Why: correctness and data safety come first. Before changing business calculations, the project should stop advertising a command that can run a legacy, absolute-path pipeline and should prove the intended pipeline can run against synthetic data without reading or mutating real files.

Recommended Phase 2C acceptance criteria:

- The default documented command no longer depends on local absolute finance file paths.
- The authoritative pipeline entrypoint is explicit and fails clearly when required inputs are absent.
- A fixture-based smoke test creates only synthetic inputs in a temporary directory.
- The smoke test verifies generated outputs are confined to a temp/run directory.
- The smoke test verifies input fixture hashes are unchanged after the run.
- Existing 15 baseline tests continue to pass.

Out of scope for the recommended task:

- Changing income, fee, crowd-cost, or reconciliation formulas.
- Reading or running real finance files.
- Cleaning existing `runs` outputs.
- Adding external APIs, notifications, remotes, or UI.
