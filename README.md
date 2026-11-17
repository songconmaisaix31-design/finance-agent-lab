<div align="center">

# finance-agent-lab

Six cities, one finance pipeline: city differences live in configuration, city data lives in isolated namespaces, and five of the six cities stay blocked until their rules are approved.

六个城市、一条财务流水线：城市差异写在配置里，城市数据放在隔离命名空间里，六城中有五个在规则获批前一直保持阻塞。

[![Cities](https://img.shields.io/badge/cities-6%20registered%20%C2%B7%201%20enabled-blue.svg)](config/city_profiles)
[![Stages](https://img.shields.io/badge/pipeline%20stages-5-yellowgreen.svg)](orchestration/pipeline.yaml)
[![Tests](https://img.shields.io/badge/test%20methods-83-brightgreen.svg)](tests)
[![Dependencies](https://img.shields.io/badge/pinned%20dependencies-5-informational.svg)](requirements.txt)
[![License](https://img.shields.io/badge/license-none%20in%20repo-lightgrey.svg)](README.md)
![CI](https://img.shields.io/badge/CI-not%20configured-lightgrey.svg)

</div>

> **How to read this page / 怎么读这页**
> English first, then the same content in Chinese — not a summary, not a separate half. Tables keep both languages in one cell.
> 每段英文在前、同一内容的中文紧跟在后；不是摘要，也没有单独的"中文版"。表格把两种语言放进同一格。

## At a glance · 一眼看懂

| | |
|---|---|
| **Problem<br/>问题** | Six cities' finance workbooks are similar enough to share logic and different enough to fork it. The usual outcome is six copies of one script, each with its own fee rates and its own bugs.<br/>六个城市的财务表足够相似、该共用逻辑，又足够不同、容易被复制成六份。常见结果是同一个脚本被抄六遍，每份有自己的费率、自己的 bug。 |
| **Fix<br/>做法** | One standard pipeline profile, one profile file per city, per-city rule sets and approval packs, and per-city storage namespaces outside the repo. Unknown income, delivery, or crowd-cost types fail closed.<br/>一条标准流水线配置、每个城市一个 profile、按城市的规则集与审批包、以及仓库之外按城市隔离的数据目录。未知的收入、配送或人次成本类型一律闭合失败。 |
| **Cost<br/>代价** | Python 3.11+, five pinned packages, no database. City data lives outside Git under a root you pass in with `--root`.<br/>需要 Python 3.11+、5 个固定版本依赖、不要数据库。城市数据放在 Git 之外，根目录由 `--root` 传入。 |
| **Not<br/>不是** | Not a production accounting system, not a web UI, not an approved business rule set. `guan` / 固安 is a synthetic-smoke reference city and is explicitly not production ready.<br/>不是生产财务系统、不是网页界面、也不是已批准的商业规则集。`guan` / 固安 只是合成数据冒烟参考城市，明确未达到生产可用。 |

## The problem · 问题在哪

Every city wants "the same report, just with our numbers". The polite version of that request produces copied configuration: the fee rate from one city survives in another, and nobody can tell which number is authoritative.

每个城市都想要"同一份报表，只是换成我们的数字"。这个请求的客气版本产出的是复制来的配置：A 城的费率活到了 B 城，最后没人说得清哪个数字算数。

The current state is visible in the rule directories — one real rule set, five placeholders:

现状直接写在规则目录里——一份真规则集，五份占位：

```text
config/rules/
├── guan/rule-set.yaml          # rule_set_id: guan-rules · status: unverified
├── biyang/README.md            # placeholder only · 仅占位
├── queshan/README.md           # placeholder only · 仅占位
├── xianghe/README.md           # placeholder only · 仅占位
├── yicheng/README.md           # placeholder only · 仅占位
├── yongcheng/README.md         # placeholder only · 仅占位
└── shared/README.md            # shared, not yet approved · 共享但未批准
```

The five non-`guan` cities are registered but blocked for formal runs precisely because those rule sets are not approved. That is a deliberate state, not a missing feature.

另外五个非 `guan` 城市已注册、但正式运行被阻塞，原因正是这些规则集未获批。这是刻意的状态，不是待补的功能。

## The idea · 思路

Configuration is split by who owns it: the pipeline shape is shared, the city identity is per city, and the business numbers are per city and explicitly unapproved until a human says otherwise.

配置按"谁拥有它"来拆：流水线形状是共享的，城市身份是一城一份，业务数字一城一份，且在人工批准之前明确是未批准状态。

| Noun · 名词 | Where · 位置 | Rule · 规则 |
|---|---|---|
| **City profile**<br/>城市档案 | `config/city_profiles/<id>.yaml` | Declares display name, currency, storage namespace, rule set id, and which capabilities are enabled.<br/>声明显示名、币种、存储命名空间、规则集 id，以及启用哪些能力。 |
| **Pipeline profile**<br/>流水线档案 | `config/pipeline_profiles/standard-finance-pipeline.yaml` | One profile for all six cities. A city that needs a different shape changes the profile, not the code.<br/>六个城市共用一份。需要不同形状的城市改档案，不改代码。 |
| **Stage**<br/>阶段 | `orchestration/pipeline.yaml` | Five stages: `intake` → `normalize` → `calculate` → `reconcile` → `report`. Each stage has an input and output schema.<br/>五个阶段：`intake` → `normalize` → `calculate` → `reconcile` → `report`，每段都有输入与输出 schema。 |
| **Contract**<br/>契约 | `schemas/*.json` | Six JSON schemas. n8n may only pass run metadata and paths — never billing or normalized rows.<br/>六份 JSON schema。n8n 只能传运行元数据与路径，绝不传账单行或归一化行。 |
| **Exactness**<br/>精确性 | `src/reconcile*.py`, `reconciliation_contract.py` | Decimal comparison, zero tolerance on technical invariants. Business cross-table rules report `not_implemented` instead of guessing.<br/>用 Decimal 比较，技术不变量零容忍；跨表业务规则报 `not_implemented`，不猜。 |

The test of whether the idea holds: `python -m src.cli cities validate` either passes against the profiles or names the profile that is wrong. It does not silently pick a default city.

检验这套思路是否成立：`python -m src.cli cities validate` 要么对着档案通过，要么指出哪份档案有问题；它不会悄悄选一个默认城市。

## Capabilities · 能力清单

CLI surface, from `src/cli.py`:

命令行接口，来自 `src/cli.py`：

| Command · 命令 | What it does · 做什么 |
|---|---|
| `plan --city <id> --input <dir> --output <dir>` | Validates a run request and plans stages without executing accounting.<br/>校验运行请求、规划阶段，不执行核算。 |
| `run --city <id> --input <dir> --output <dir> --execute` | Actual accounting, only with the explicit `--execute` flag.<br/>真正核算，必须显式带 `--execute`。 |
| `stage <name> --city --input --output` | Executes one stage contract in isolation.<br/>单独执行某一个阶段的契约。 |
| `cities list` / `cities show --city <id>` / `cities validate` | Inspects and validates city and pipeline profiles.<br/>查看并校验城市档案与流水线档案。 |
| `storage init --root <dir>` / `storage validate --root <dir>` | Creates or validates per-city data directories and the catalog outside the repo.<br/>在仓库之外创建或校验按城市隔离的数据目录与目录清单。 |
| `rebuild-run-index` | Rebuilds the API run lookup index from run-directory truth files.<br/>从运行目录里的真值文件重建 API 运行索引。 |

HTTP surface, from `src/api.py` (`src.api:app`), canonical paths under `/api/v1` with deprecated unprefixed aliases:

HTTP 接口，来自 `src/api.py`（`src.api:app`），规范路径在 `/api/v1` 下，另有已弃用的无前缀别名：

| Endpoint · 端点 | What it does · 做什么 |
|---|---|
| `GET /api/v1/health` | Liveness plus the service version.<br/>存活检查与服务版本。 |
| `POST /api/v1/runs` | Creates a run from `run_id`, city, input path, output root.<br/>用 `run_id`、城市、输入路径、输出根创建一次运行。 |
| `GET /api/v1/runs/{run_id}` | Reads stage statuses and metrics for one run.<br/>读取一次运行的各阶段状态与指标。 |
| `POST /api/v1/runs/{run_id}/stages/{stage}` | Executes one of the five stages; unknown stage returns `404 UNKNOWN_STAGE`.<br/>执行五个阶段之一；未知阶段返回 `404 UNKNOWN_STAGE`。 |
| `GET /api/v1/runs/{run_id}/artifacts` | Lists artifacts produced by the run.<br/>列出该次运行产出的文件。 |

Orchestration quality gates live in `quality-gates.yaml`: intake, calculation and reconciliation must not fail, reconciliation must report zero errors, and the report stage must produce at least one artifact — otherwise the run is `rejected` or `failed`.

编排质量门在 `quality-gates.yaml`：intake、calculation、reconciliation 不得失败，reconciliation 错误数必须为 0，report 阶段至少产出一个文件——否则整轮标为 `rejected` 或 `failed`。

## Quickstart · 快速开始

### Requirements · 环境要求

Python 3.11+; the five pins in `requirements.txt` (`fastapi`, `uvicorn`, `openpyxl`, `jsonschema`, `PyYAML`). No database, no service to start for CLI runs. `scripts/check.ps1` and the n8n compose file assume Windows PowerShell for the local workflow.

需要 Python 3.11+ 和 `requirements.txt` 里 5 个固定版本依赖。CLI 运行不需要数据库、不需要起服务。`scripts/check.ps1` 与 n8n compose 的本地流程按 Windows PowerShell 写的。

### 1. Install · 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Plan before you run · 先规划再运行

```powershell
python -m src.cli cities list
python -m src.cli cities validate
python -m src.cli plan --city guan --input <input-directory> --output <output-directory>
```

`plan` validates the request and writes nothing that spends effort on accounting. Outputs land under `<output-directory>\runs\<run-id>\`.

`plan` 只校验请求，不进入核算。产物落在 `<output-directory>\runs\<run-id>\`。

### 3. Execute one run · 执行一次运行

```powershell
python -m src.cli run --city guan --input <input-directory> --output <output-directory> --execute
python -m src.cli storage validate --root <finance-data-root>
```

Reconciliation results are in `runs\<run-id>\result-summary.json` under `reconciliation` and in `runs\<run-id>\reconciliation-report.json`.

对账结果在 `runs\<run-id>\result-summary.json` 的 `reconciliation` 段和 `runs\<run-id>\reconciliation-report.json`。

### 4. Run the tests · 跑测试

```powershell
.\scripts\check.ps1
# equivalent · 等价于
python -m unittest discover -s tests -p "*test*.py"
```

83 test methods across 10 files. **Not executed for this README revision** — no dependencies were installed here, so treat the pass count as unverified.

10 个文件里 83 个测试方法。**本次 README 改造没有执行**——这里没有装依赖，所以通过数请当作未验证。

## Documentation · 文档

| Doc · 文档 | Read it when · 什么场景读它 |
|---|---|
| `docs/BASELINE.md` | Establishing what the platform does today before changing anything.<br/>动手改之前先确认平台今天到底做什么。 |
| `docs/LESSONS.md` | Reading the failures that shaped the stage contracts.<br/>读塑造了阶段契约的那些失败。 |
| `docs/plans/phase-2f-six-city-governance.md` | Understanding the six-city governance decisions.<br/>理解六城治理的决策。 |
| `docs/plans/phase-2c-safe-entrypoint.md` | Why execution needs an explicit entry point.<br/>为什么执行必须走显式入口。 |
| `docs/plans/phase-2d-crowd-cost-contract.md` | The crowd-cost contract and its unverified bucket rules.<br/>人次成本契约与未验证的分桶规则。 |
| `docs/plans/phase-2e-reconciliation-contract.md` | Which reconciliation checks exist and which are deliberately absent.<br/>哪些对账检查存在、哪些是刻意没有的。 |
| `docs/n8n-migration/STAGE_CONTRACTS.md` | Implementing or debugging one stage's input/output contract.<br/>实现或调试某个阶段的输入输出契约。 |
| `docs/n8n-migration/STAGE_DEPENDENCY_MAP.md` | Working out what must run before what.<br/>理清谁必须在谁之前跑。 |
| `docs/n8n-migration/MODULE_MAP.md` | Finding which module owns a behaviour.<br/>找某个行为归哪个模块。 |
| `docs/n8n-migration/DATA_FLOW.md` | Following a workbook through all five stages.<br/>跟一份表穿过五个阶段。 |
| `docs/n8n-migration/RECOVERY_MODEL.md` | Recovering a run after a partial failure.<br/>部分失败后如何恢复一次运行。 |
| `docs/n8n-migration/OPENAPI_GOVERNANCE.md` | Changing the HTTP contract without breaking n8n.<br/>改 HTTP 契约而不打坏 n8n。 |
| `docs/n8n-migration/AUDIT.md` | Auditing the migration's scope and exclusions.<br/>审计迁移的范围与排除项。 |
| `docs/n8n-migration/FINAL_ACCEPTANCE_REPORT.md` | Checking what was accepted, and by whom.<br/>核对验收了什么、由谁验收。 |
| `docs/n8n-migration/MANUAL_UI_ACCEPTANCE.md` | The manual UI acceptance steps that were never automated.<br/>从未自动化的手工界面验收步骤。 |
| `docs/n8n-migration/PHASE3_ACCEPTANCE_REPORT.md`, `PHASE3_AUDIT.md`, `REVIEW_FINDINGS.md` | Reviewing the phase 3 claims against the findings.<br/>把第三阶段的说法和评审发现对起来看。 |
| `docs/n8n-migration/CURRENT_PIPELINE.mmd`, `TARGET_PIPELINE.mmd` | Seeing current versus target pipeline as diagrams.<br/>用图看当前与目标流水线。 |
| `TASK.md` | The current task, its acceptance criteria, and its known blockers.<br/>当前任务、验收标准与已知阻塞。 |
| `AGENTS.md` | Editing rules and the safety invariants for contributors.<br/>贡献者的编辑规则与安全不变量。 |

## Repository layout · 仓库结构

```text
finance-agent-lab/
├── src/                       # 31 Python modules: CLI, API, pipeline, reconcile · 31 个模块
│   ├── cli.py                 # plan / run / stage / cities / storage · 命令行入口
│   ├── api.py                 # FastAPI app: 5 endpoints + deprecated aliases · 5 个端点
│   ├── pipeline_service.py    # stage orchestration · 阶段编排
│   └── reconciliation*.py     # exact Decimal invariants · Decimal 精确不变量
├── config/
│   ├── city_profiles/         # 6 city profiles · 6 份城市档案
│   ├── pipeline_profiles/     # 1 standard pipeline · 1 份标准流水线
│   └── rules/                 # 1 rule set + 6 placeholders · 1 份规则集 + 6 处占位
├── approval-pack/             # per-city approval drafts and shared pipeline rules · 审批草案
├── orchestration/pipeline.yaml# stages, statuses, payload scope · 阶段、状态、载荷范围
├── quality-gates.yaml         # 5 gates that can reject a run · 5 道可否决运行的门
├── schemas/                   # 6 JSON schemas · 6 份 JSON schema
├── workflows/                 # 7 n8n workflow exports: FIN-00…FIN-90 · 7 个 n8n 流程导出
├── infra/n8n/                  # compose, up/down, sanitize export · 编排与导出清洗
├── docs/                      # 21 docs, including the n8n migration trail · 21 份文档
└── tests/                     # 10 files, 83 test methods · 10 个文件、83 个测试方法
```

## Status · 状态

Single-commit snapshot of a sanitized working tree (`git rev-list --count HEAD` returns 1), not the full history. Static counts here — 31 modules, 6 cities, 5 stages, 6 schemas, 5 gates, 7 n8n workflows, 21 docs, 10 test files, 83 test methods — are file and `git ls-files` counts at this commit.

这是一份脱敏工作树的单提交快照（`git rev-list --count HEAD` 返回 1），不是完整历史。这里的静态数字——31 个模块、6 个城市、5 个阶段、6 份 schema、5 道门、7 个 n8n 流程、21 份文档、10 个测试文件、83 个测试方法——都是本提交下的文件与 `git ls-files` 计数。

Known limits, stated rather than hidden:

- Five of six cities (`xianghe`, `yicheng`, `yongcheng`, `queshan`, `biyang`) are registered but blocked for formal runs until their rule sets are approved; only `guan` can run today, and only with synthetic data.
- `guan` itself is `status: unverified`; its fee rates, whitelists, field aliases, crowd-cost buckets, and tolerances await business approval. Nothing here is production ready.
- Cross-table business relationships in reconciliation are reported as `not_implemented` with `approval_status: unverified`, not evaluated.
- No CI: there is no `.github/` directory, so no badge here claims a build. `scripts/check.ps1` runs the tests locally.
- No license file exists in this snapshot, so the repository grants no reuse right by itself.
- The n8n path was accepted partly by manual UI steps (`docs/n8n-migration/MANUAL_UI_ACCEPTANCE.md`); that part is not covered by the automated tests.
- Real finance workbooks were never used in tests by policy. All test data is synthetic, so real-world input shapes remain unverified.
- Tests were not executed for this README revision; the 83 count is a static count, not a pass count.

边界写出来而不是藏起来：

- 六个城市中有五个（`xianghe`、`yicheng`、`yongcheng`、`queshan`、`biyang`）已注册但在规则集获批前禁止正式运行；今天只有 `guan` 能跑，且只用合成数据。
- `guan` 自身是 `status: unverified`：费率、白名单、字段别名、人次成本分桶与容差都还等业务批准。这里没有哪部分是生产可用。
- 对账里的跨表业务关系报为 `not_implemented`、`approval_status: unverified`，不做计算。
- 没有 CI：不存在 `.github/` 目录，所以本页没有徽章声称构建通过；测试由 `scripts/check.ps1` 在本地跑。
- 本快照没有许可文件，因此仓库本身不授予复用权利。
- n8n 那条路径有一部分是靠手工界面步骤验收的（`docs/n8n-migration/MANUAL_UI_ACCEPTANCE.md`），这部分不在自动测试覆盖内。
- 按策略，测试从不使用真实财务表。所有测试数据都是合成的，真实输入形状仍未验证。
- 本次 README 改造没有执行测试；83 是静态计数，不是通过数。

## License · 许可

No license file is present in this snapshot. All rights reserved by default; do not redistribute or reuse without the owner's permission. City rule sets and approval packs are internal business documents, not open specifications.

本快照没有许可文件，默认保留所有权利；未获所有者许可请勿再分发或复用。城市规则集与审批包是内部业务文档，不是公开规范。
