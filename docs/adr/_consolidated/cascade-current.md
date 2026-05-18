# ADR-042 Cascade — Consolidated View

> **Auto-generated** by `scripts/audit/consolidate_cascade.py` per ADR-042 §27.5. Do NOT hand-edit — `consolidate_cascade.py --verify` rejects drift. Regenerate via `python -m scripts.audit.consolidate_cascade`.

## Base ADR-042 — Quality Assurance Infrastructure Overhaul

_Status: Accepted_

<!--
TRANSITIONAL NOTE: This ADR is the bootstrap document for the QA infrastructure
it defines. Until Phase 1 (§26) delivers the Fact Substitution Registry (§10),
this document uses hardcoded values where {{ facts.X }} substitutions will live
later. Each such site carries a TODO marker linking to a tracking issue. After
Phase 4 revalidation (§28.3), this document MUST be re-rendered through the
fact registry and re-validated. The transitional exemption window is explicit
and finite; it expires when Phase 4 closes.
-->

# ADR-042: Quality Assurance Infrastructure Overhaul

## 1. Purpose & Scope

### 1.1 Purpose

Define a single, agent-equal, machine-enforceable Quality Assurance regime
covering documentation, code, configuration, and process artifacts for the
SciEasy repository. The regime exists because prompt-level constraints on AI
agents have demonstrably failed to prevent four distinct classes of
documentation / implementation drift (§2), and the project has grown past the
point where individual reviewer vigilance can serve as a substitute for tooling.

This ADR also serves as the canonical template for all subsequent ADRs (§28.4):
its frontmatter schema, prose conventions, and metadata structure are the
template that all later ADRs MUST follow.

### 1.2 In-scope artifacts

This ADR governs QA enforcement over the following artifact classes:

| Artifact class | Scope detail |
|---|---|
| Python source | `src/scieasy/` and `packages/scieasy-blocks-*/` |
| Frontend source | `frontend/` (TypeScript toolchain, same rigor — see §21) |
| Tests | `tests/` (docstring coverage exempt, all other rules apply) |
| Documentation | `docs/` (ADRs, specs, architecture, planning, audit) |
| Configuration | `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/`, `.workflow/schema-v2.yaml` |
| Agent-facing files | `AGENTS.md`, `CLAUDE.md`, `CURSOR.md`, `GEMINI.md`, all symlinks |
| Skills | `.claude/skills/`, `~/.claude/skills/`, equivalent paths in other runtimes |
| Identity/ownership | `MAINTAINERS`, `docs/identity/humans.yml` |

### 1.3 Out-of-scope

The following are explicitly out of scope for ADR-042:

| Out-of-scope | Where it belongs instead |
|---|---|
| Runtime architecture decisions | Their own ADRs (ADR-017+) |
| Plugin model design | ADR-027 + ADR-028 |
| AI-feature design (AIBlock, prompt composition, etc.) | ADR-035, ADR-040 |
| Storage backend design | ADR-022, ADR-026 |
| One-off scripts in `scripts/` (excluding `scripts/audit/` and `scripts/committer.py`, `scripts/translate_docs.py` which ADR-042 explicitly governs) | Free, unregulated |
| Data assets under `_skills/`, `agent_provisioning/templates/` | Free (data, not code) |
| Historical commit hygiene before Phase 3 start | No retroactive enforcement of trailers/frontmatter on existing history |

### 1.4 ADR-042 as the canonical template

ADR-042 is the first ADR written under the rules ADR-042 itself defines. After
Phase 4 (§26.5) closes, `docs/adr/_template/ADR-template.md` is frozen as a
verbatim derivative of this ADR's structure (with field values stripped). All
subsequent ADRs MUST be authored by copying that template; ad-hoc structure is
prohibited.

---

## 2. Context — The Four-Class Drift Problem

### 2.1 Empirical observation

The SciEasy repository is largely AI-agent-developed. As the codebase grew past
~30 KLOC Python plus ~41 ADRs and ~8 specs, drift between intent (docs/ADRs)
and reality (code/config) became systemic. Four distinct classes are observed:

| Class | Pattern | Example (cited in §2.2) |
|---|---|---|
| **a** | Documentation and implementation agree | (the goal state) |
| **b** | Both exist but disagree (signature, schema, behavior) | `_data` backdoor surviving ADR-031 |
| **c** | Documentation cites a symbol/file/path; reality does not contain it (phantom reference) | ADR-040 hypothetical example: `compose_system_prompt(project_dir)` claims |
| **d** | Public code symbol exists with no governing ADR or docstring (orphan) | ~680 public symbols today, no machine validation |

Classes (b), (c), and (d) collectively represent silent technical debt that AI
agents (and human contributors) cannot detect by reading either the docs or the
code alone — and that prompt instructions to "check the docs" have failed to
prevent.

### 2.2 Concrete evidence (sampled 2026-05-17 audit)

- ADR-031 declares the `ViewProxy` class eliminated and `_data` backdoor
  removed. The class is indeed gone, but `_data` attribute access remains live
  in `src/scieasy/blocks/io/loaders/load_data.py:197-201`. Class (b).
- ADR-007 is superseded by ADR-031 per ADR-031's own frontmatter, but `ADR.md`
  still labels ADR-007 `Status: accepted` with no supersession marker. Class (b).
- The drift smoke audit (2026-05-17) found roughly 1-in-5 fine-grained ADR
  claims drift from current code state in spot-checked subsystems; orphan
  public-symbol count is conservatively estimated above 400 (out of ~680).

### 2.3 Why prompt-level constraints failed

The project's CLAUDE.md has carried explicit anti-drift rules since at least
Phase 2 (out-of-scope TODO rule, ADR alignment requirements, etc.). These have
not held because:

1. **Agents do not re-read** the full instruction set between turns; the longer
   the conversation, the higher the recency bias.
2. **Multi-agent dispatch** breaks the "one agent reads everything" assumption.
   A skeleton agent and an implementation agent split the work; rules read by
   one do not transfer to the other.
3. **Prose rules are not machine-verifiable**. A rule like "every ADR must
   match its referenced code" cannot be checked at PR time without tooling
   that parses ADRs into structured form, resolves their references against a
   symbol table, and reports mismatches.
4. **Reviewer fatigue.** As PR volume grew (driven by agent productivity),
   human reviewers stopped reading 100% of every diff. Code review became
   sampling.

### 2.4 The required shift

The fix is not "stronger prompts." It is **machine-enforced consistency at
the gate**, with prose rules backed by code-level validators and CI checks
that block merge. The remainder of this ADR specifies that machinery.

---

## 3. Decision Summary

### 3.0 Transitional prologue (bootstrap exemption window)

> ADR-042 is the bootstrap document for the QA infrastructure it defines.
> Until Phase 1 (§26.2) delivers the Fact Substitution Registry (§10) and
> the full schema/audit toolchain (§5–§11, §17, §20), this document,
> ADR-043, and ADR-044 use hardcoded values where `{{ facts.X }}`
> substitutions will eventually live. Each such site carries a TODO marker
> linking to the umbrella tracking issue. After Phase 4 revalidation
> (§28.3), all three documents MUST be re-rendered through the fact
> registry and re-validated. The transitional exemption window is
> explicit and finite; it expires when Phase 4 closes.
>
> The transitional exemption covers:
> 1. Hardcoded numeric/list values in prose that would otherwise be
>    machine-rendered substitutions.
> 2. Governed-contract dotted paths that will not be importable until
>    Phase 1 lands their pydantic implementations.
> 3. Pytest-examples execution of fenced python blocks that import from
>    `scieasy.qa.schemas.*` or other Phase-1-deliverable modules. After
>    Phase 1 lands the imports, pytest-examples becomes a hard gate.
>
> The exemption does NOT cover any other rule, gate, or check defined in
> this ADR. It explicitly extends to the first PR of any addendum
> (ADR-043, ADR-044, future B/C/...) for the duration of that single PR;
> see §27.4.

This ADR adopts, as a single coherent regime:

1. **Pydantic v2 schemas** as the single source of truth for all
   structured contracts (frontmatter, MAINTAINERS, audit reports, facts
   registry, identity registry). Co-located in `src/scieasy/qa/schemas/`.

2. **Mandatory YAML frontmatter** on every ADR and spec (§5), defining
   `governs` (modules / contracts / files), `is_code_implementation`,
   `agent_editable`, `assisted_by`, translations, and lifecycle dates.

3. **Bidirectional ownership closure** between ADR `governs` and the new
   `MAINTAINERS` file (§11); CI rejects PRs where the symmetric difference is
   non-empty.

4. **Fact Substitution Registry** (§10): structured facts (gate count,
   tool list, thresholds, etc.) live in a single generated YAML file extracted
   from canonical sources; prose references them via `{{ facts.X }}`
   substitutions. Hardcoded prose mentions of registered fact values become
   CI errors.

5. **a/b/c1/c2/c3/d drift classifier** (§9) running on every PR, with
   c-class never assuming which side is wrong.

6. **Workflow v2** (§19): seven gates replacing the prior six-gate workflow,
   each with machine-checkable definition-of-done and per-stage guidance to
   walk agents to one-pass quality.

7. **Sphinx + autoapi + nitpicky + sphinx-needs + pytest-examples** as the
   docs engine (§23); broken `:py:class:` references and unexecutable code
   blocks fail the build.

8. **Linux-kernel-style git trailers** (§13): `Assisted-by:`, `Fixes:`,
   `ADR:`, validated by commit-msg hook.

9. **libCST codemod discipline** (§20): any ADR that changes a contract
   ships a paired codemod under `tools/codemods/adr-NNN-*.py`; CI verifies
   the codemod-when-applied yields zero diff.

10. **OpenClaw-pattern AGENTS.md hierarchy** (§12) with per-subtree
    nesting, `$persona` routing tokens, and a `docs-agent` CI workflow with
    hard path allowlist (§15).

11. **Real-Behavior-Proof gate** (§14): AI-generated tests, lint, CI
    output are supplemental only; a human must attach screenshot, screen
    recording, or real-execution log for any UI/runtime change.

12. **Agent-equality principle** (§4.1): every rule applies identically to
    all supported AI agent runtimes (Claude Code, Codex, Cursor, Aider,
    Gemini). No preferential implementation; provisioning extends to all
    runtimes synchronously.

13. **Human Developer Exemption Principle** (§25): process burdens
    (trailers, gates, wrappers) relax for verified human contributors;
    quality baseline (tests, lint, types, ADRs, schemas, closure, fact
    substitution) does not.

14. **Documentation language policy** (§22): all source documents in
    English; an external-API-driven translator script auto-generates Chinese
    mirrors under `docs/zh-CN/`. No agent translation.

15. **Self-iteration mechanism** (§28): a dedicated audit agent scans this
    ADR for internal contradictions during the planning phase; post-Phase-4,
    this ADR must be revalidated against the final tooling and pass all rules
    it defines.

### 3.1 Execution sequencing

The regime is delivered as a seven-step phased rollout (§26): Phase 0,
Phase 1, Phase 1.5 (checkpoint), Phase 2, Phase 3, Phase 4, Phase 5.
Phase 0 establishes feature
freeze and the umbrella issue. Phase 1 builds tools in report-only mode.
Phase 1.5 is a baseline-data review gate. Phase 2 flips CI to fail-on-error.
Phase 3 is dedicated technical-debt cleanup (no feature work). Phase 4
delivers the "tool-generated specs become source of truth" PR. Phase 5 is
permanent enforcement and weekly audit cron.

### 3.2 Zero-tolerance posture

Unlike typical mid-size projects that adopt strict tooling with a baseline
of tolerated existing violations ("baseline + ratchet"), ADR-042 explicitly
rejects baseline tolerance. CI is red from Phase 2 until the dedicated
Phase 3 cleanup completes. This is justified in §4.3.

---

## 4. Core Principles

The four principles below are non-negotiable. Every other section in this
ADR derives from them.

### 4.1 Agent-Equality (identical merge-time enforcement)

> All AI agent runtimes (Claude Code, Codex, Cursor, Aider, Gemini, and any
> future runtime the project supports) receive **identical merge-time
> enforcement**. No rule, gate, or governance check may apply to one runtime
> and not others at the CI / git / branch-protection layer.

**Scope clarification (audit P0.1 fix)**: agent-equality applies to the
**hard guarantee layer** (CI, git hooks, branch protection, workflow-gate
validators, server-side validation), which is genuinely cross-runtime by
construction (all PRs hit the same CI regardless of who authored). It does
NOT mandate identical per-runtime lifecycle hooks: Claude Code's
`PreToolUse` / `InstructionsLoaded` / `Stop` / etc. are Claude-specific
events; Codex / Cursor / Aider / Gemini define their own (or none). Per-
runtime hooks are best-effort local guardrails — they should be configured
for each runtime where the runtime supports an analogous lifecycle, but
cannot be a hard guarantee since lifecycle support varies.

**Implications:**

- `AGENTS.md` is the canonical root document. `CLAUDE.md`, `CURSOR.md`,
  `GEMINI.md` are symlinks or auto-derived files containing only a pointer
  back to `AGENTS.md`. (§12)
- Skills installation extends to all runtimes via the `agent_provisioning`
  system (ADR-040 §3.5-3.8). Adding a skill = updating the required-skill
  manifest (§17) plus running cross-runtime provisioning. (§17)
- Hooks are implemented in three layers, in order of guarantee strength:
  (1) **Git hooks + CI + branch protection** — true cross-runtime hard
  guarantee; (2) **per-runtime agent hooks** — Claude harness
  (`scripts/hooks/*.sh` PreToolUse + InstructionsLoaded + Stop), Codex
  (`codex_config.toml` hook section), etc.; best-effort, not deterministic
  across runtimes; (3) **skill-embedded best-practices** — advisory only.
  Cross-runtime parity at layer (1) is mandatory; layers (2) and (3) are
  best-effort per-runtime. (§16)
- The `Assisted-by:` git trailer (§13) uses an agent-agnostic format
  `<Runtime>:<ModelID>` and CI validates only format compliance, never
  preferring any runtime.
- Verification of any new agent-collaboration mechanism requires Real-Behavior-
  Proof on all supported runtimes (§14), not only on one.

**Failure mode this prevents:** "Worked in Claude Code but Codex never picked
up the rule" — a class of silent disparity that would compound over time as
agent runtimes diverge.

### 4.2 Code-as-Truth (Transitional) → Status-Based Arbitration (Permanent)

> Until Phase 4 closes, code is the ground truth and documentation must be
> revised to match. After Phase 4, conflict arbitration becomes status-based:
> an Accepted ADR is the ground truth; a Draft or Proposed ADR yields to
> current code.

The transitional rule exists because the Phase 3 debt-cleanup sprint needs a
deterministic tiebreaker for thousands of (b)-class drift items. Re-litigating
each "did the code drift from intent, or did intent drift from code?" is
infeasible; we adopt "code wins, fix the docs" as the universal rule.

The permanent rule restores ADR authority once docs are validated. See §8 for
the full conflict-arbitration table by status.

### 4.3 Zero-Tolerance

> No existing violation is grandfathered. CI is red from Phase 2 until Phase 3
> cleanup completes. There is no `baseline.json` of tolerated violations.

This is the most aggressive choice in this ADR and is justified by:

1. **Agents will learn baselines as compliance ceilings.** If the tool says
   "5,237 violations is OK," the agent's mental model becomes "5,237 is the
   target," and new contributions will drift toward that ceiling.
2. **The cleanup is bounded.** The debt is finite (~680 symbols, ~50 docs).
   With agent-parallel cleanup (§26.5), the sprint is estimable in weeks, not
   indefinite.
3. **Feature freeze (§26.1) is in effect.** No new debt is accumulating during
   cleanup. The window is closed.
4. **The cost of permissive baselines compounds.** Every release shipped with
   tolerated debt locks that debt into the API contract or documented behavior,
   making removal an ABI-break later.

**Implementability** (verified 2026-05-17 against primary tool docs +
GitHub API docs): zero-tolerance with all-red CI is **implementable** via
a **ratchet wrapper** that exploits GitHub's `conclusion=neutral` semantic
for required checks.

GitHub branch-protection docs state: *"Required status checks must have a
`successful`, `skipped`, or `neutral` status before collaborators can make
changes to a protected branch."* The Checks API allows a workflow to
report `conclusion=neutral`. Therefore cleanup PRs can merge while CI
visibly shows "5,237 → 5,236 → 5,235 …" if the wrapper reports `neutral`
on monotonic decrease.

**Three Phase-1 deliverables make this work** (without them, the design
self-contradicts):

1. **`.workflow/ci/ratchet.py`** — per-tool wrapper: reads previous
   finding count from `docs/audit/baselines/<tool>.json`, compares to
   current run. Reports Checks API `conclusion=neutral` when current ≤
   previous AND no new file regressions; `conclusion=failure` when count
   increases OR a previously-clean file regresses.
2. **SARIF unification** — convert ruff/mypy/bandit/pyright JSON →
   SARIF (community converters exist; zizmor emits SARIF natively).
   Upload to GitHub Code Scanning. `partialFingerprints` gives free
   per-finding stable IDs + auto-close on PR diff. This is the standard
   GitHub-native mechanism for "PR closes findings X, Y, Z, N remain."
3. **Explicit tool-flag pinning** in CI invocations:
   - `mypy --soft-error-limit=-1` (default is -1 but MUST be explicit;
     any positive integer silently truncates errors past the limit and
     defeats per-finding tracking).
   - `zizmor --format=sarif` (defeats GitHub Annotations 10-cap UI render
     limit; full findings reach code-scanning).
   - `ruff --output-format=json-lines --statistics`.
   - `pydoclint --baseline` (native baseline supported).

**Tools verified to satisfy run-to-completion + per-finding output**: ruff,
mypy (with above flag), pyright, interrogate, pydoclint, griffe, vulture,
xenon, bandit/ruff-S, pip-audit, mutmut, pytest-examples, markdownlint-cli2,
sphinx-lint, sphinx-build --nitpicky, actionlint, zizmor (with above flag),
codespell, yamllint, import-linter — all 20 tools in the §21.1 stack.

**Phase-1 verification artifact**: `docs/audit/reports/<phase-1-end-sha>/ci-implementability.json`
must contain empirical (not asserted) per-tool dry-run results before
Phase 2 flip is authorized. Schema documented in
`docs/contributing/reference/ci-implementability.md` (Phase 1 deliverable).

**Industry precedent**: FastAPI + mypy use the same ratchet pattern; GitHub
Code Scanning's `partialFingerprints` was designed for this workflow.

### 4.4 Meta-Recursion

> Every rule defined in this ADR applies to this ADR. Every rule applies to
> the tooling that enforces this ADR. Every rule applies to itself.

**Concrete manifestations:**

- ADR-042 has the same frontmatter every other ADR has (§5).
- ADR-042's commit carries `Assisted-by:` trailer like every other commit (§13).
- ADR-042's `governs.contracts` list must resolve to real symbols (§9 forward
  pass) — meaning every pydantic class in §5–7.5 must be created in Phase 1.
- ADR-042's prose must use `{{ facts.X }}` substitutions wherever it cites
  values registered in the facts registry (§10) — once the registry is
  operational. (The transitional exemption is in §3.0 prologue.)
- If gate.py changes from 6 to 7 stages, ADR-042's prose mention of "7 stages"
  must update too (or substitute via `{{ facts.workflow.stage_count }}`).
- The QA tools that enforce ADR-042 must themselves pass ADR-042's tests, lint,
  type-checks, docstring coverage, ADR coverage, and bidirectional closure.

This recursion is not philosophical. It is the operational defense against
"the tool that enforces consistency is itself inconsistent."

---

## 5. Frontmatter Schema

### 5.1 Design rationale

Every ADR and spec carries machine-parseable YAML frontmatter that:

1. Identifies the document (id, title, date, status).
2. Tracks lifecycle (supersedes, superseded_by, related, closes).
3. Declares governance scope (`governs.modules`, `governs.contracts`,
   `governs.files`).
4. Declares validation (`tests`).
5. Declares AI provenance (`agent_editable`, `assisted_by`).
6. Declares translation linkage (`translations`).
7. Declares ownership (`owner`, `co_authors`).

The schema is enforced by pydantic v2 with `extra="forbid"` (unknown fields
are errors, not silently dropped). Cross-field rules (e.g., `is_code_implementation=true`
requires non-empty `governs` and `tests`) are validators.

### 5.2 Pydantic models

The full models live at `src/scieasy/qa/schemas/frontmatter.py`. Reproduced
below for reference:

```python
# src/scieasy/qa/schemas/frontmatter.py
from __future__ import annotations
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(StrEnum):
    DRAFT = "Draft"
    PROPOSED = "Proposed"
    ACCEPTED = "Accepted"
    SUPERSEDED = "Superseded"
    WITHDRAWN = "Withdrawn"
    DEPRECATED = "Deprecated"


class AgentEditable(StrEnum):
    TRUE = "true"
    FALSE = "false"
    ALLOWLIST = "allowlist"


class Phase(StrEnum):
    """Phase enum. Values are the canonical machine form; §26 prose uses
    'Phase 0', 'Phase 1.5', etc. for readability. ADR-043 phase_gate CLI
    uses enum-form (e.g., `--check phase-1->phase-1-5`)."""
    PLANNING = "planning"
    PHASE_0 = "phase-0"
    PHASE_1 = "phase-1"
    PHASE_1_5 = "phase-1-5"     # §26.3 Baseline review gate
    PHASE_2 = "phase-2"
    PHASE_3 = "phase-3"
    PHASE_4 = "phase-4"
    PHASE_5 = "phase-5"
    COMPLETE = "complete"


# --- Shared primitive types (audit fix C1: extracted from frontmatter.py and
# maintainers.py into a common module to break the circular import) ---
# These live in `src/scieasy/qa/schemas/_common.py`; both frontmatter.py and
# maintainers.py import them from there.

# Pattern fix I2: allow 1-char paths (regex was previously 2+ char-required).
RepoRelativePath = Annotated[str, Field(min_length=1, pattern=r"^[^/](?:.*[^/])?$")]
PathGlob = Annotated[str, Field(min_length=1)]  # broader; allows ** wildcards anywhere

DottedModulePath = Annotated[
    str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")
]
FunctionOrClassPath = Annotated[
    str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
]
GitHandle = Annotated[str, Field(pattern=r"^@[A-Za-z0-9][A-Za-z0-9_-]*$")]
AssistedByLine = Annotated[
    str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9._-]+(?: \[.+\])?$")
]
LocaleCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]
ADRRef = Annotated[int, Field(ge=1, le=9999)]
IssueRef = Annotated[int, Field(ge=1)]

# --- frontmatter.py imports from ._common ---


class Governs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modules: list[DottedModulePath] = Field(default_factory=list)
    contracts: list[FunctionOrClassPath] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    files: list[RepoRelativePath] = Field(default_factory=list)
    # excludes: list[PathGlob] — both primitives imported from
    # `scieasy.qa.schemas._common` (audit fix C1: no circular import).
    excludes: list[PathGlob] = Field(default_factory=list)


class Translation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: LocaleCode
    path: RepoRelativePath
    auto_generated: bool = True
    source_sha: str | None = None


class AmendmentKind(StrEnum):
    """How an addendum amendment relates to its target section (§27.5)."""
    EXTEND = "extend"          # adds to the target (target prose still applies)
    REPLACE = "replace"        # supersedes target prose entirely
    CONSTRAIN = "constrain"    # tightens target (target still applies + restriction)
    CLARIFY = "clarify"        # editorial; no semantic change


class Amendment(BaseModel):
    """Single addendum amendment record. Used in ADRFrontmatter.amends."""
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=4)  # e.g. "ADR-042 §17 Required Skills"
    kind: AmendmentKind
    summary: str = Field(min_length=4, max_length=240)


class ADRFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Identity
    adr: ADRRef
    title: str = Field(min_length=4, max_length=120)
    status: Status
    date_created: date
    date_accepted: date | None = None
    date_superseded: date | None = None

    # Lifecycle
    supersedes: list[ADRRef] = Field(default_factory=list)
    superseded_by: ADRRef | None = None
    related: list[ADRRef] = Field(default_factory=list)
    closes_issues: list[IssueRef] = Field(default_factory=list)
    tracking_issue: IssueRef | None = None

    # Addendum amendment records (§27.5; required for any ADR that amends another)
    amends: list[Amendment] = Field(default_factory=list)

    # Governance
    is_code_implementation: bool
    governs: Governs

    # Validation
    tests: list[RepoRelativePath] = Field(default_factory=list)

    # AI governance
    agent_editable: AgentEditable = AgentEditable.FALSE
    # AgentRuntime imported from `scieasy.qa.schemas.maintainers` (defined
    # in §6.2). Forward-import handled by `from __future__ import annotations`
    # at module top — pydantic resolves at validation time, not import time.
    # (iter-7 ITER-FRESH-012: import dependency made explicit.)
    agent_editable_allowlist: list[AgentRuntime] = Field(default_factory=list)  # required non-empty iff agent_editable == ALLOWLIST (audit fix F4)
    assisted_by: list[AssistedByLine] = Field(default_factory=list)

    # Meta
    phase: Phase = Phase.PLANNING
    tags: list[str] = Field(default_factory=list)
    owner: GitHandle
    co_authors: list[GitHandle] = Field(default_factory=list)
    language_source: Literal["en"] = "en"
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _agent_editable_allowlist_paired(self) -> "ADRFrontmatter":
        if self.agent_editable == AgentEditable.ALLOWLIST and not self.agent_editable_allowlist:
            raise ValueError(
                "agent_editable=allowlist requires non-empty agent_editable_allowlist"
            )
        if self.agent_editable != AgentEditable.ALLOWLIST and self.agent_editable_allowlist:
            raise ValueError(
                "agent_editable_allowlist is only valid when agent_editable=allowlist"
            )
        return self

    @model_validator(mode="after")
    def _status_dates_consistent(self) -> "ADRFrontmatter":
        if self.status == Status.ACCEPTED and self.date_accepted is None:
            raise ValueError("status=Accepted requires date_accepted")
        if self.status == Status.SUPERSEDED:
            if self.date_superseded is None:
                raise ValueError("status=Superseded requires date_superseded")
            if self.superseded_by is None:
                raise ValueError("status=Superseded requires superseded_by")
        return self

    @model_validator(mode="after")
    def _code_impl_requires_governs_and_tests(self) -> "ADRFrontmatter":
        if self.is_code_implementation:
            if not (self.governs.modules or self.governs.contracts):
                raise ValueError(
                    "is_code_implementation=true requires non-empty "
                    "governs.modules or governs.contracts"
                )
            if not self.tests:
                raise ValueError("is_code_implementation=true requires non-empty tests")
        return self

    @model_validator(mode="after")
    def _no_self_supersede(self) -> "ADRFrontmatter":
        if self.adr in self.supersedes:
            raise ValueError("ADR cannot supersede itself")
        if self.superseded_by == self.adr:
            raise ValueError("ADR cannot be superseded by itself")
        return self
```

### 5.3 Field reference (selected)

| Field | Type | Required | Rule |
|---|---|---|---|
| `adr` | int | yes | 1–9999, globally unique across all ADRs |
| `title` | str | yes | 4–120 chars |
| `status` | enum | yes | One of Draft/Proposed/Accepted/Superseded/Withdrawn/Deprecated |
| `date_created` | ISO date | yes | YYYY-MM-DD |
| `date_accepted` | ISO date | conditional | Required iff `status == Accepted` |
| `date_superseded` | ISO date | conditional | Required iff `status == Superseded` |
| `is_code_implementation` | bool | yes | If true, forces non-empty governs + tests |
| `governs.modules` | list[dotted path] | conditional | At least one (or contracts) required if is_code_implementation |
| `governs.contracts` | list[dotted path] | conditional | Function/class level granularity (§5.4) |
| `governs.files` | list[repo path] | optional | Non-Python files (workflows, configs, schemas) |
| `agent_editable` | enum | yes (default false) | true/false/allowlist (§5.4.1 details; allowlist requires paired `agent_editable_allowlist` list of runtimes) |
| `assisted_by` | list[str] | yes (may be empty) | Format `<Runtime>:<ModelID> [tools]` |
| `owner` | GitHandle | yes | At least one human owner |
| `co_authors` | list[GitHandle] | optional | Includes `@claude`, `@codex`, etc. when AI co-authored |
| `language_source` | Literal["en"] | yes | All source docs in English (§22.1) |
| `translations` | list[Translation] | optional | Auto-populated by translator |

### 5.4 Governance granularity

`governs.contracts` carries function/class-level dotted paths. Method-level
granularity (`Class.method`) is supported but not required for the class
itself to be governed. The general rule:

- Listing `scieasy.qa.schemas.frontmatter.ADRFrontmatter` covers the class and
  all its methods/attributes.
- Listing `scieasy.qa.schemas.frontmatter.ADRFrontmatter._status_dates_consistent`
  explicitly governs a specific validator (useful when an ADR specifically
  introduces or modifies that validator).
- `governs.modules` is coarser; listing `scieasy.qa.schemas` covers everything
  in that module.

The reverse-pass classifier (§9 step 5) checks: every public **class** must
appear in some ADR's `governs.contracts` or be a member of a module in some
ADR's `governs.modules`. Public functions/methods need only docstrings.

### 5.4.1 `agent_editable` enum semantics (audit fix I1 + I11)

The `agent_editable: AgentEditable` field has three values; their semantics:

| Value | Effect | When to use |
|---|---|---|
| `false` | No AI agent may modify the document body. Only verified humans (per ADR-042 §25 identity registry) may edit. | Default. Stable ADRs / specs / governance docs whose body is the authoritative reference. |
| `true` | Any AI agent may modify the document body, subject to all other rules (trailer, RBP if applicable, doc_drift, etc.). | Working notes, planning docs, debugging logs. Rare for core docs. |
| `allowlist` | AI agents from the runtimes named in a sibling `agent_editable_allowlist: list[AgentRuntime]` field may modify; others may not. | Production-environment artifacts where only specific runtimes have legitimate edit reasons (e.g., a doc that only `docs-agent` should refresh; allowlist would be `[Claude]` if docs-agent uses Claude only). |

**Temporal scope (audit fix I11)**: `agent_editable` applies AFTER the
document reaches `status: Accepted`. During `Draft` and `Proposed`, the
flag is **informational**: agents may edit Draft/Proposed bodies subject
to the standard `assisted_by`/trailer requirements (the bootstrap
exemption per §3.0 covers the pre-acceptance edit window). This is why
ADR-042, ADR-043, ADR-044 themselves carry `agent_editable: false` while
being authored by `@claude` during their Draft state — there is no
contradiction; the flag's enforcement begins at Acceptance.

The `allowlist` mode requires a paired `agent_editable_allowlist: list[AgentRuntime]`
field declared on `ADRFrontmatter` (see §5.2 — the field is declared and
enforced by the `_agent_editable_allowlist_paired` model_validator: it
MUST be non-empty when `agent_editable=allowlist`, and MUST be empty
otherwise). `AgentRuntime` is imported from `scieasy.qa.schemas.maintainers`
(defined in §6.2). Implementation of the cross-runtime install plumbing
that consumes this allowlist is tracked under §26.2 sub-phase 1H.

### 5.5 Lifecycle and status transitions

```
                Draft ────────────► Proposed ────────────► Accepted
                  │                     │                     │
                  ▼                     ▼                     ▼
              Withdrawn            Withdrawn             Superseded
                                                              │
                                                              ▼
                                                         Deprecated
```

Transitions:

- `Draft → Proposed`: author opens an issue and posts a change-plan comment.
- `Proposed → Accepted`: project owner approves; `date_accepted` is set.
- `Accepted → Superseded`: a new ADR's `supersedes` list contains this ADR's
  number. The supersession-automation hook (§5.6) mutates this ADR's status
  and writes `superseded_by` and `date_superseded`.
- `Accepted → Deprecated`: the project decides to deprecate without an
  immediate replacement. Used sparingly.
- `Draft/Proposed → Withdrawn`: author abandons the proposal.

`Withdrawn` and `Deprecated` ADRs remain in the repository for archaeology;
they are not deleted. Their `governs` is treated as inert by the bidirectional
closure check (§11).

### 5.6 Supersession automation

When a new ADR's `supersedes` field lists an ADR number `N`, the
`adr-supersession-bot` CI workflow:

1. Validates that ADR-N exists and is currently `Accepted`.
2. Mutates ADR-N's frontmatter: sets `status: Superseded`, `superseded_by: <new>`,
   `date_superseded: <today>`.
3. Commits the change as a separate bot commit with trailer
   `Assisted-by: ADR-Supersession-Bot:v1`.
4. The supersession commit is restricted to ADR-N's frontmatter — no body
   edits, no other files (analogous to docs-agent path allowlist, §15).

This eliminates the historical pattern where ADR-007 stayed marked `accepted`
despite being superseded by ADR-031 (§2.2 example).

### 5.7 Spec frontmatter

Specs use a subset of the ADR schema (`SpecFrontmatter`):

- No supersession lifecycle. Specs are `Draft | Active | Deprecated` only.
- Specs identify by `spec_id: <kebab-case-slug>` rather than integer.
- Specs include `related_adrs: list[ADRRef]` to link back to governing ADRs.
- All other fields (governs, tests, agent_editable, assisted_by, owner,
  translations) are identical to ADRs.

```python
# src/scieasy/qa/schemas/frontmatter.py (continued)
class SpecFrontmatter(BaseModel):
    """Subset of ADRFrontmatter for specs (no supersession lifecycle)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    spec_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    status: Literal["Draft", "Active", "Deprecated"]
    date_created: date

    related_adrs: list[ADRRef] = Field(default_factory=list)
    closes_issues: list[IssueRef] = Field(default_factory=list)

    is_code_implementation: bool
    governs: Governs                                  # already-implemented (subject to closure)
    planned_governs: Governs = Field(default_factory=Governs)  # to-be-created in named phases
    tests: list[RepoRelativePath] = Field(default_factory=list)

    agent_editable: AgentEditable = AgentEditable.FALSE
    assisted_by: list[AssistedByLine] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)
    owner: GitHandle
    co_authors: list[GitHandle] = Field(default_factory=list)
    language_source: Literal["en"] = "en"
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _code_impl_requires_governs_and_tests(self) -> "SpecFrontmatter":
        if self.is_code_implementation:
            if not (self.governs.modules or self.governs.contracts
                    or self.planned_governs.modules or self.planned_governs.contracts):
                raise ValueError(
                    "is_code_implementation=true requires non-empty governs OR planned_governs"
                )
            if not self.tests:
                raise ValueError(
                    "is_code_implementation=true requires non-empty tests"
                )
        return self
```

---

## 6. MAINTAINERS Schema

### 6.1 Purpose

The `MAINTAINERS` file is the reverse direction of ADR `governs`: a mapping
from file globs to the ADRs and humans that own them. It serves three roles:

1. **Reverse-ownership lookup**: given a file, find which ADRs govern it and
   which humans approve changes.
2. **Bidirectional closure validation** (§11): the union of paths covered by
   any `MAINTAINERS` entry must equal the union of paths covered by any
   Accepted ADR's `governs.modules + governs.files`.
3. **Agent authorization**: each entry lists which AI runtimes are permitted
   to edit files under its glob (`agents_allowed`). Empty list = humans only.

### 6.2 Schema

```python
# src/scieasy/qa/schemas/maintainers.py
from __future__ import annotations
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
# Audit fix C1: shared primitives moved to ._common to break the circular
# import that previously existed between frontmatter.py and maintainers.py.
from ._common import ADRRef, GitHandle, PathGlob


class AgentRuntime(StrEnum):
    CLAUDE = "Claude"
    CODEX = "Codex"
    CURSOR = "Cursor"
    AIDER = "Aider"
    GEMINI = "Gemini"


class MaintainersEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_glob: PathGlob
    adrs: list[ADRRef] = Field(default_factory=list)
    humans: list[GitHandle] = Field(default_factory=list)
    agents_allowed: list[AgentRuntime] = Field(default_factory=list)
    excludes: list[PathGlob] = Field(default_factory=list)
    notes: str | None = None


class Maintainers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    entries: list[MaintainersEntry] = Field(min_length=1)  # audit fix I1: explicit non-empty
```

### 6.3 File format

`MAINTAINERS` is a YAML file at repo root. Example excerpt:

```yaml
version: 1
entries:
  - path_glob: "src/scieasy/qa/**"
    adrs: [42]
    humans: ["@jiazhenz026"]
    agents_allowed: [Claude, Codex, Cursor, Aider, Gemini]
    notes: "QA infrastructure subsystem. ADR-042."

  - path_glob: "src/scieasy/core/**"
    excludes: ["src/scieasy/core/lineage/**"]
    adrs: [1, 17, 22, 27, 28, 31]
    humans: ["@jiazhenz026"]
    agents_allowed: [Claude, Codex, Cursor, Aider, Gemini]

  - path_glob: "src/scieasy/core/lineage/**"
    adrs: [38]
    humans: ["@jiazhenz026"]
    agents_allowed: [Claude, Codex, Cursor, Aider, Gemini]
```

### 6.4 Glob semantics

- `**` matches any number of path components (including zero).
- `*` matches any non-slash characters within a single component.
- Negation is handled by `excludes`, not by `!` prefix syntax (clearer to parse).
- Globs are matched relative to repo root.
- An entry's effective coverage is `glob_match(path_glob) − Σ glob_match(excludes)`.

### 6.5 Resolution

Given a file path:

1. Find all entries whose `(path_glob, excludes)` cover the path.
2. If zero entries match → CI error: "file is not covered by any MAINTAINERS entry."
3. If one entry matches → use it.
4. If multiple entries match → use the most-specific (longest non-wildcard prefix).
   Ties are resolved by entry order in the YAML file.

---

## 7. Audit Report Schema

### 7.1 Purpose

Every audit tool (doc_drift, frontmatter_lint, fact_drift, closure, full_audit)
emits its results in a shared `AuditReport` envelope. This provides:

- A single schema for downstream consumers (CI annotations, the `doc-drift-guard`
  skill, human-readable HTML render).
- Versioned schema (`schema_version: 1`) for forward compatibility.
- Cross-tool aggregation (one envelope can contain multiple `ToolRun` blocks).

### 7.2 Models

```python
# src/scieasy/qa/schemas/report.py
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DriftClass(StrEnum):
    A = "a"     # agree
    B = "b"     # disagree (signature/schema mismatch)
    C1 = "c1"   # doc cites symbol; code missing — symbol existed historically
    C2 = "c2"   # doc cites symbol; code missing — symbol never existed
    C3 = "c3"   # doc/code mismatch; cannot determine wrong side
    D = "d"     # public code symbol with no ADR coverage


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    severity: Severity
    drift_class: DriftClass | None = None
    file: str
    line: int | None = None
    symbol: str | None = None
    message: str
    suggested_fix: str | None = None
    git_evidence: str | None = None
    related_findings: list[str] = Field(default_factory=list)


class ToolRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    version: str
    config_hash: str
    started_at: datetime
    completed_at: datetime
    exit_status: Literal["ok", "warnings", "errors", "crash"]
    findings: list[Finding] = Field(default_factory=list)


class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    run_id: str
    repo_sha: str
    repo_branch: str
    pr_number: int | None = None
    generated_at: datetime
    runs: list[ToolRun]

    total_findings: int
    by_severity: dict[Severity, int]
    by_drift_class: dict[DriftClass, int]

    bidirectional_closure_ok: bool
    translation_ok: bool
```

### 7.3 Storage

Reports are stored under `docs/audit/reports/YYYY-MM-DD/<run-id>.json`,
immutable once written. A symlink `docs/audit/latest/` points to the most
recent report directory. Reports older than 90 days are archived to
`docs/audit/archive/YYYY/MM/` (still committed to repo for historical
queryability).

### 7.4 Consumers

| Consumer | Reads |
|---|---|
| CI annotation | `latest/full.json` to post per-line PR comments |
| `doc-drift-guard` skill | `latest/full.json` to brief agents on current debt |
| Weekly audit report | `reports/YYYY-MM-DD/full.json` to generate HTML diff vs previous week |
| Phase 4 revalidation gate | The ADR-042-self-check report (§28.3) |

---

## 7.5 Facts Registry Schema

### 7.5.1 Purpose

Structured "facts" that prose documents would otherwise hardcode (gate count,
stage names, tool list, coverage thresholds, ADR counts, etc.) live in a
single generated registry. Prose references them via `{{ facts.X }}`
substitutions, rendered at docs-build time. The registry is the only source
of truth; hardcoded prose references to known fact values become CI errors
(§10).

### 7.5.2 Models

```python
# src/scieasy/qa/schemas/facts.py
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class WorkflowFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_count: int = Field(ge=1)
    stages: list[str]
    blocking_validations: dict[str, list[str]]


class ToolFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    python_version: str
    min_coverage_percent: int = Field(ge=0, le=100)
    lint_rules: list[str]
    type_checkers: list[str]
    docs_engine: str


class ADRFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_count: int
    by_status: dict[str, int]
    latest_adr_number: int


class MaintainersFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_count: int
    human_count: int
    paths_covered_count: int


class SkillFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_skills: list[str]
    installed_per_runtime: dict[str, list[str]]


class FactsRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    generated_at: datetime
    source_shas: dict[str, str]
    workflow: WorkflowFacts
    tool: ToolFacts
    adr: ADRFacts
    maintainers: MaintainersFacts
    skill: SkillFacts
```

### 7.5.3 Generation

`docs/facts/generated.yaml` is produced by `scripts/audit/generate_facts.py`,
which orchestrates the per-namespace extractors:

| Namespace | Extractor | Reads |
|---|---|---|
| `workflow` | `extract_workflow_facts.py` | `.workflow/schema-v2.yaml`, `gate.py --self-describe` |
| `tool` | `extract_tool_facts.py` | `pyproject.toml`, `.pre-commit-config.yaml` |
| `adr` | `extract_adr_facts.py` | `docs/adr/*.md` frontmatter |
| `maintainers` | `extract_maintainers_facts.py` | `MAINTAINERS` |
| `skill` | `extract_skill_facts.py` | `scieasy.qa.identity` registry + cross-runtime probe |

Generation is invoked by:

- Pre-commit hook (regenerates on relevant source change).
- CI on every PR (regenerates and diffs against committed copy; mismatch = error).
- Manual: `python -m scieasy.qa.audit.generate_facts`.

### 7.5.4 Schema versioning

`schema_version` is bumped only when the field structure changes. Field-value
changes do not bump the version. Bumping requires an addendum ADR.

---

## 8. Truth Model & Conflict Arbitration

### 8.1 Phase-dependent rules

| Phase | Arbitration rule when ADR claim conflicts with code |
|---|---|
| Phase 0 – Phase 4 (transitional) | **Code wins.** ADR is revised to match. |
| Phase 5 (permanent) | **Status-driven.** See table below. |

### 8.2 Status-driven arbitration (Phase 5 onwards)

| ADR status | Conflict resolution |
|---|---|
| `Accepted` | ADR wins. Code must be revised, or a new ADR supersedes this one. |
| `Proposed` | Code wins. ADR is updated to match observed code, then re-proposed. |
| `Draft` | Code wins. Draft is iterated until aligned. |
| `Superseded`/`Withdrawn`/`Deprecated` | Inert. No conflict possible (claims are historical). |

### 8.3 Conflict-detection workflow

A b-class drift detected by §9 produces a `Finding` with `drift_class=b`.
The fix path:

1. Audit script reports the conflict.
2. Agent (or human) reads the conflict and the status of the cited ADR.
3. Applies the rule from §8.2.
4. Commits the resolution: either updates the ADR (with `Fixes:` trailer
   referencing the audit finding) or updates the code (with `ADR: N` trailer
   referencing the governing ADR).

### 8.4 Multi-ADR conflicts

If two Accepted ADRs both `govern` the same symbol with contradicting claims,
this is itself a Finding (`rule_id="closure.multi-adr-conflict"`) and blocks
merge. Resolution requires supersession of one ADR.

---

## 9. a/b/c1/c2/c3/d Drift Classification

### 9.1 Definitions (precise)

| Class | Forward / Reverse | Definition |
|---|---|---|
| **a** | Either | Doc citation resolves; if signature claim present, claim matches code |
| **b** | Forward | Doc citation resolves but signature/schema/field disagrees with code |
| **c1** | Forward | Doc citation does not resolve in current code; git history shows the symbol was present and later deleted |
| **c2** | Forward | Doc citation does not resolve and never appeared in git history (likely doc hallucination) |
| **c3** | Forward | Mixed git evidence (e.g., the dotted path matched a different kind of symbol historically); manual review required |
| **d** | Reverse | Public class is not cited by any Accepted ADR's `governs.contracts` (no docstring requirement on classes; classes need ADR coverage) OR public function/method lacks a docstring |

Critical invariant: **c-class never assumes which side is wrong.** The
classifier reports the discrepancy plus evidence; the resolution requires
human or agent judgment guided by §8.

### 9.2 Algorithm (Python pseudocode)

```python
# src/scieasy/qa/audit/doc_drift.py — algorithm overview
# Full implementation in Phase 1. The body of this function is held in a
# separate file (docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md) per §28.0
# to satisfy the pytest-examples constraint on ADR-042 itself.

def classify_repo(repo_root: Path) -> AuditReport:
    """Top-level drift classification entry point.

    Steps:
      1. Build code symbol table via griffe (static, no import side effects).
      2. Parse all ADR/spec frontmatter via pydantic.
      3. Build doc-cited symbols index from frontmatter + Sphinx refs.
      4. Forward pass: doc citations must resolve; signatures must match.
      5. Reverse pass: public classes must be ADR-governed; public functions
         must have docstrings.
      6. Bidirectional MAINTAINERS <-> governs closure check.
      7. Translation freshness check.
      8. Aggregate into AuditReport.
    """
    raise NotImplementedError("see docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md")
```

The complete pseudocode lives in
`docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` (companion file,
`agent_editable: false`) and is exempt from `pytest-examples` via an explicit
allowlist entry.

### 9.3 c-class disambiguation heuristics

For symbol `S` cited by doc but not in code:

```python
evidence = git_history_for_symbol(S, repo_root)

if evidence.was_present_then_deleted:
    drift = C1
    fix = (f"Symbol deleted in {evidence.deleting_commit_sha} by "
           f"{evidence.deleting_commit_author}. "
           f"Per §8: if ADR is Accepted, restore the symbol or supersede the ADR. "
           f"If ADR is Draft/Proposed, update the ADR to match current code.")

elif evidence.never_existed:
    near = nearest_existing_symbol(S, public_symbols)
    drift = C2
    fix = (f"Symbol never existed in git history (likely doc hallucination). "
           + (f"Did you mean: {near}?" if near else "No close match found."))

else:
    drift = C3
    fix = "Mixed git evidence; manual review required to determine wrong side."
```

The "nearest existing symbol" check uses Levenshtein distance on dotted-path
segments, suggesting a close match if edit distance ≤ 3.

### 9.4 d-class scope (relaxed for methods/functions)

The reverse pass enforces:

- Every public **class** must appear in some ADR's `governs.contracts` OR be a
  member of a module in some ADR's `governs.modules`. Failure → d-class
  `Finding` with `rule_id="doc-drift.orphan-class"`.
- Every public **function/method** must have a docstring (Google-style). No
  ADR-coverage requirement at this granularity. Failure → d-class with
  `rule_id="doc-drift.missing-docstring"`.

Rationale: requiring ADR coverage at function-method granularity would
explode the ADR count to unmaintainable scale. Class-level coverage is the
right tradeoff: it documents the contract surface where it matters.

"Public" is defined as **listed in `__all__`** if `__all__` is present, else
**not starting with underscore**. The first audit pass during Phase 1 will
flag many modules lacking `__all__`; remediation is to add `__all__`
explicitly during Phase 3 cleanup.

### 9.5 b-class signature matching (strict)

Signature matching compares four attributes of the function/method:

1. **Parameter names** (positional + keyword, in order)
2. **Parameter type annotations** (using `inspect.get_type_hints` evaluated
   types)
3. **Return type annotation**
4. **Raised exceptions** (extracted from `Raises:` docstring section)

All four must match. A b-class `Finding` notes which attribute disagrees.

### 9.6 Audit module entry-point signatures

The following module-level entry points are governed by ADR-042 and listed
in frontmatter `governs.contracts`. Their full implementations live in
Phase 1; the stubs below establish the signatures and return types:

```python
# src/scieasy/qa/audit/frontmatter_lint.py
from pathlib import Path
from scieasy.qa.schemas.report import Finding


def lint_file(path: Path) -> list[Finding]:
    """Validate a single ADR/spec file's YAML frontmatter against the schema.

    Parses YAML frontmatter from ``path``, attempts construction via
    ``ADRFrontmatter`` (or ``SpecFrontmatter`` for specs), and returns a list
    of :py:class:`scieasy.qa.schemas.report.Finding` objects describing any
    pydantic ValidationError, missing required field, regex mismatch, or
    cross-field validator failure.

    Returns an empty list when the file is fully valid.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/full_audit.py
from pathlib import Path
from scieasy.qa.schemas.report import AuditReport


def run(repo_root: Path | None = None, *,
        targets: list[Path] | None = None,
        pre_push: bool = False,
        self_check: bool = False) -> AuditReport:
    """Orchestrate the full audit pipeline.

    Runs every audit tool (doc_drift, frontmatter_lint, fact_drift,
    closure, trailer_lint, committer_enforce, weakened_ci_check) and
    aggregates their results into a single :py:class:`scieasy.qa.schemas.report.AuditReport`
    envelope. ``targets`` narrows the audit to specific files; ``pre_push``
    enables the stricter pre-push subset; ``self_check`` targets ADR-042
    itself for the §28.2 continuous self-validation gate.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/trailer_lint.py
from pathlib import Path
from scieasy.qa.schemas.report import Finding


def run(repo_root: Path | None = None, *,
        commit_range: str = "HEAD~1..HEAD") -> list[Finding]:
    """Validate git trailers on the specified commit range.

    For each commit in ``commit_range``: extract trailers, validate
    ``Assisted-by:`` format (§13.2) when the commit author is an agent,
    validate ``Fixes:`` SHA references, validate ``ADR:`` references
    resolve to a real ADR, and (per §13.3 layer 3) cross-check approval
    trailers against actual GitHub review APIs.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/committer_enforce.py
from pathlib import Path
from scieasy.qa.schemas.report import Finding


def check(repo_root: Path | None = None) -> list[Finding]:
    """Verify recent agent commits were made via scripts/committer.py.

    Reads ``docs/audit/commit-log.jsonl`` and compares against git log; any
    agent-authored commit not appearing in the log is a violation. Used
    as a pre-commit hook (per ADR-042 §16.1, §21.3) and as a CI gate.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/contradiction_audit.py   (audit fix C3)
# Invoked via `python -m scieasy.qa.audit.contradiction_audit --targets <files>`
# from ADR-043 §3.5 governance-modification workflow.
from pathlib import Path
from scieasy.qa.schemas.report import AuditReport


def run(repo_root: Path | None = None, *,
        targets: list[Path] | None = None) -> AuditReport:
    """Scan target ADR/spec docs for internal contradictions (§28.1).

    Implemented by the $scieasy-adr-auditor persona (§17). For machine
    invocation, runs against the persona's checklist: supersedes cycles,
    agent_editable contradictions, governs vs excludes conflicts,
    schema vs validator mismatches, workflow stage cycles, undefined
    section references, tool-list internal contradictions.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/complete_artifacts.py   (audit fix C3)
# Invoked via `python -m scieasy.qa.audit.complete_artifacts --check` from
# Workflow v2 stage 6 (§19.2).
from pathlib import Path
from scieasy.qa.schemas.report import Finding


def check(repo_root: Path | None = None, *,
          pr_number: int | None = None) -> list[Finding]:
    """Verify Workflow v2 stage-6 'complete_artifacts' requirements:

    Docstrings + ADR governs + MAINTAINERS + translation enqueued + CHANGELOG
    entry + codemod committed (if contract change) + RBP attached + skills
    installed cross-runtime. Composed from existing checks; returns the
    union of their Findings filtered to the PR's diff scope.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

```python
# src/scieasy/qa/audit/codemod_lint.py   (audit fix C3)
# Referenced in §20.3 ("metadata is parsed by scieasy.qa.audit.codemod_lint").
from pathlib import Path
from typing import Any


def parse(codemod_path: Path) -> dict[str, Any]:
    """Parse a tools/codemods/adr-NNN-*.py file's metadata docstring header.

    Returns the pydantic-validated CodemodMeta dict (see §20.3): adr ref,
    description, affects list, tests list. Raises ValueError on missing
    or malformed metadata.
    """
    raise NotImplementedError("Phase 1 deliverable")
```

These stubs satisfy frontmatter `governs.contracts` symbol-existence checks
during Sphinx nitpicky validation (§23.4). The bodies are filled in during
Phase 1; each fill-in PR includes the corresponding test from `tests/qa/`
(per frontmatter `tests` list).

---

## 10. Fact Substitution Registry + Rule-of-Rules Consistency

### 10.1 Problem

Prose documents that hardcode structured facts (gate count, stage names, tool
list, thresholds) drift silently when the underlying facts change. Concrete
example: if `gate.py` changes from 6 to 7 stages but CLAUDE.md still says "6
stages," neither human review nor existing tooling catches the inconsistency.

This generalizes class (b) drift from "code symbols" to "structured facts
mentioned in prose." The fix follows the same principle: prose cannot
duplicate canonical data.

### 10.2 Mechanism

```
Canonical sources (code/config)
        │
        ▼
generate_facts.py (auto-extracts)
        │
        ▼
docs/facts/generated.yaml  ◄── pydantic-validated, version-controlled
        │
        ▼
Jinja2 substitution in prose: {{ facts.workflow.stage_count }}
        │
        ▼
Sphinx build (rendered output) + fact_drift.py audit (raw input)
```

### 10.3 Prose authoring rules

When prose needs to mention any registered fact:

- **Wrong**: `"The workflow has 7 stages."`
- **Right**: `"The workflow has {{ facts.workflow.stage_count }} stages."`

The Sphinx build (via `sphinx-substitution-extensions` or equivalent)
renders the substitution at build time.

### 10.4 Audit: `fact_drift.py`

A new audit tool scans prose for hardcoded fact values:

```python
# src/scieasy/qa/audit/fact_drift.py — algorithm overview

def check_substitutions(repo_root: Path) -> list[Finding]:
    """Detect hardcoded facts in prose that should use {{ facts.X }} substitution.

    Steps:
      1. Load FactsRegistry from docs/facts/generated.yaml.
      2. Collect all registered fact values (numbers, list elements, strings).
      3. For each prose file (.md, .rst under docs/, README.md, AGENTS.md):
         a. Strip code blocks (``` ... ``` and indented).
         b. Strip existing {{ facts.X }} substitutions.
         c. For each remaining line, search for literal occurrences of any
            registered fact value.
         d. If found, emit Finding(severity=error, rule="fact-drift.hardcoded",
            suggested_fix=f"replace '{value}' with {{ facts.{path} }}").
      4. Return findings.
    """
```

False-positive minimization: numeric values < 3 or single-character matches
are excluded by default (they are rarely "facts" in the registry sense). The
exclusion list is in `pyproject.toml` `[tool.fact_drift]` for tuning.

### 10.5 The "gate.py changed from 6 to 7 stages" scenario

1. Developer modifies `.workflow/schema-v2.yaml` from 6 to 7 stages.
2. Pre-commit hook runs `extract_workflow_facts.py`, updating
   `docs/facts/generated.yaml` (`workflow.stage_count: 6 → 7`).
3. Pre-commit then runs `fact_drift.py` on all prose.
4. CLAUDE.md (or any other doc) that still contains the literal string `"6
   stages"` triggers: `Finding(severity=error, file="CLAUDE.md", line=142,
   rule="fact-drift.hardcoded", message="literal '6 stages' found; use
   '{{ facts.workflow.stage_count }} stages' instead")`.
5. Commit blocked until prose is updated.
6. After fix, prose renders to "7 stages" via Sphinx substitution.

### 10.6 Transitional period

Before the Fact Substitution Registry is fully operational (Phase 1
deliverable), this ADR uses hardcoded values with TODO markers
(`# TODO(#NNN): substitute via {{ facts.X }} after Phase 1`). The Phase 4
revalidation gate (§28.3) requires every such TODO to be resolved.

---

## 11. Bidirectional Ownership Closure

### 11.1 Statement

> The union of paths covered by Accepted ADR `governs.{modules, files}`
> equals the union of paths covered by `MAINTAINERS` entries.

Symbolically: `S_adr == S_maintainers`. The symmetric difference being
non-empty is a `Finding(severity=error, rule="closure.asymmetric")` that
blocks PR merge.

### 11.2 Closure check algorithm

```python
# src/scieasy/qa/audit/closure.py — algorithm overview

def check_bidirectional(repo_root: Path) -> list[Finding]:
    """Verify MAINTAINERS <-> governs closure.

    Steps:
      1. Load all Accepted ADRs; build S_adr from governs.modules ∪ governs.files.
      2. Load MAINTAINERS; build S_maintainers from entries' path_globs minus excludes.
      3. Compute symmetric difference.
      4. For each path in S_adr \\ S_maintainers: emit "governed by ADR but no
         MAINTAINERS entry covers it."
      5. For each path in S_maintainers \\ S_adr: emit "MAINTAINERS entry covers
         path not governed by any Accepted ADR."
    """
```

### 11.3 Module-to-glob resolution

To compare a dotted module path against a file glob:

- `scieasy.qa.schemas` → expands to `src/scieasy/qa/schemas/**/*.py` plus
  `src/scieasy/qa/schemas/__init__.py`.
- A MAINTAINERS entry like `src/scieasy/qa/**` covers this module.

The resolution helper lives in `scieasy.qa.audit.closure._module_to_paths`.

### 11.3.2 governs.files cross-ADR overlap rule (audit fix iter-7 ITER-FRESH-006)

When multiple ADRs list the same path in `governs.files` (e.g.,
`docs/sphinx/conf.py` claimed by both ADR-042 §23.2 and ADR-044 §10.4),
ownership is **shared and additive**: both ADRs apply jointly. Closure
check treats the path as governed (no orphan finding) but flags any
**semantic conflict** between the joint owners (e.g., one ADR sets
`generation: auto` while another asserts hand-edit-OK) as a §8.4
`closure.multi-adr-conflict` Finding.

Shared ownership is the common case when an addendum (per §27.5 `amends`)
extends a parent ADR's coverage of a file. The non-conflict additive
default is the design intent.

### 11.3.1 Parent / child module overlap arbitration (audit fix I4)

When multiple ADRs govern overlapping module paths (e.g., ADR-042 declares
`scieasy.qa` while ADR-043 declares the child `scieasy.qa.tracker`), the
closure check resolves ownership at the **most-specific** match: the
child-module-owning ADR is the ownership-of-record for its subtree;
the parent-module-owning ADR governs only the residue (paths under
`scieasy.qa.*` NOT covered by any child claim).

This mirrors §6.5 MAINTAINERS file-glob resolution ("most-specific wins;
ties resolved by entry order"). `closure.py` (§11.2) walks claims in
specificity order before computing the symmetric difference.

### 11.4 Why bidirectional

Single-direction enforcement is insufficient:

- ADR → MAINTAINERS only: an obsolete MAINTAINERS entry covering deleted code
  goes undetected.
- MAINTAINERS → ADR only: a new module added without ADR governance goes
  undetected.

Bidirectional closure ensures every governed path has an owner and every
owned path has a governing ADR. It also catches forgotten cleanups in either
direction.

---

## 12. AGENTS.md / CLAUDE.md / Per-subtree Hierarchy

### 12.1 Canonical root

`AGENTS.md` at repo root is the canonical agent-instruction document. All
other agent-runtime entry files are symlinks or auto-derived pointers:

| File | Form | Content |
|---|---|---|
| `AGENTS.md` | Regular file | Full canonical content |
| `CLAUDE.md` | Symlink → `AGENTS.md` | (resolved by Claude Code) |
| `CURSOR.md` | Symlink → `AGENTS.md` | (resolved by Cursor) |
| `GEMINI.md` | Symlink → `AGENTS.md` | (resolved by Gemini) |
| `.aiderrc` | Pointer file: `system: AGENTS.md` | (resolved by Aider) |

On Windows, where symlink creation requires admin privileges, fallback is a
1-line file containing `@include AGENTS.md` plus a pre-commit hook that
verifies content equivalence.

### 12.2 Per-subtree hierarchy

Each governed subtree carries its own `AGENTS.md`:

```
AGENTS.md                                         # root, all-agent policy
src/scieasy/AGENTS.md                             # Python-source rules
src/scieasy/core/AGENTS.md                        # core invariants
src/scieasy/blocks/AGENTS.md                      # block-development rules
src/scieasy/qa/AGENTS.md                          # QA infra rules (this ADR)
frontend/AGENTS.md                                # TS rules
docs/AGENTS.md                                    # doc authoring rules
.github/AGENTS.md                                 # CI/workflow rules
```

Each sub-`AGENTS.md` has frontmatter declaring:

```yaml
---
scope: src/scieasy/qa/**
parent_agents_md: AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42]
---
```

Sub-`AGENTS.md` files contain only **additional** rules narrower than the
root. They do not duplicate root content.

### 12.3 Skills own workflows; root owns policy

Borrowed verbatim from the OpenClaw pattern (research, 2026-05-17):

> Skills own workflows; root owns hard policy and routing.

`AGENTS.md` files contain:

- Hard policies (what is forbidden / required).
- Persona definitions (§18) and routing rules.
- Pointers to skills for how-to.

`AGENTS.md` files **do not** contain:

- Step-by-step procedures.
- Code examples beyond a single line for illustration.
- Tool invocations.

The how-to lives in `.claude/skills/<skill>/SKILL.md` (and equivalent paths
in other runtimes — see §17).

### 12.4 Validation

A pre-commit hook (`agents-md-lint`) validates:

- Root `AGENTS.md` exists.
- All listed runtime symlinks/pointers exist and resolve correctly.
- Every governed subtree (per MAINTAINERS) has an `AGENTS.md` if it requires
  agent-specific rules (declared via `agents_required: true` flag).
- Sub-`AGENTS.md` files do not duplicate content from the root (text-diff
  check).

---

## 13. Git Trailer Conventions

### 13.1 Trailer formats

| Trailer | Format | Required for |
|---|---|---|
| `Signed-off-by:` | `Name <email>` | Always (DCO-equivalent attestation) |
| `Assisted-by:` | `<Runtime>:<ModelID> [tools]` | Every agent-authored commit (§13.2) |
| `Fixes:` | `<sha12> ("subject")` | Every bug-fix commit |
| `ADR:` | `ADR-NNN` | Every commit implementing or modifying an ADR |
| `Reviewed-by:` | `Name <email>` | When the commit has been reviewed by another human |
| `Co-authored-by:` | `Name <email>` | When multiple authors contributed |
| `Reviewed-locally:` | `<reason>` | When skipping Codex review (Tier 2 humans only, §25) |
| `Maintainer-Override:` | `<reason>` | When a Tier 2 human bypasses a check (§25) |
| `Human-Override:` | `<reason>` | When a Tier 1 human exercises a documented exemption (§25) |

### 13.2 `Assisted-by:` agent-equality format

The format `<Runtime>:<ModelID> [tools]` is agent-agnostic. Valid examples:

```
Assisted-by: Claude:claude-opus-4-7
Assisted-by: Codex:gpt-5 [coccinelle sparse]
Assisted-by: Cursor:claude-3.5-sonnet
Assisted-by: Aider:gpt-4 [aider-ed]
Assisted-by: Gemini:gemini-2.0-pro
```

CI validates only format compliance. No runtime is preferred or rejected.

### 13.3 Enforcement

Three layers:

1. **`commit-msg` git hook** (local, fast): regex-validates trailer format.
2. **Pre-push hook**: extracts all unpushed commits, validates every trailer.
3. **CI `trailer-lint` job**: re-validates every commit in the PR's diff
   against main.

Missing `Assisted-by:` on a commit made by `scripts/committer.py --agent`
mode is a hard error. Missing `Assisted-by:` on a commit by a verified
human (per `docs/identity/humans.yml`, §25) is allowed.

### 13.4 `Fixes:` graph

A small tool, `tools/git-fixes-graph.py`, builds a defect-causality graph
from `Fixes:` trailers. Used for regression archaeology: when a commit
breaks behavior X, the graph reveals which earlier commit introduced X and
which subsequent commits attempted prior fixes.

### 13.5 No backfill

Trailer requirements apply from Phase 3 start (when `scripts/committer.py`
is operational). Historical commits before Phase 3 are not retroactively
required to have trailers. The `trailer-lint` job's diff base accounts for
this cutoff.

---

## 14. Real-Behavior-Proof Gate

### 14.1 Statement

> AI-generated tests, lint output, type-check output, and CI green are
> supplemental evidence only. They do not constitute proof that a change works.
> Any change touching the UI, runtime, or user-observable behavior MUST be
> accompanied by Real-Behavior-Proof: a screenshot, screen recording, or
> real-execution log produced by a human running the actual feature in its
> actual context.

### 14.2 RBP-required change classes

| Change class | RBP required? | Form of proof |
|---|---|---|
| UI change (HTML/CSS/JS that renders) | Yes | Chrome MCP screenshot or recording |
| Runtime behavior change (engine, blocks, workflow execution) | Yes | Real workflow execution log |
| API contract change | Yes | curl/httpie request-response transcript |
| CLI command added/changed | Yes | terminal capture of real invocation |
| Documentation-only change | No | (CI tests suffice) |
| Test-only change | No | (CI tests suffice) |
| Refactor with zero behavior change | Conditional | RBP required only if reviewer is unsure |

### 14.3 PR template enforcement

The PR template adds a mandatory section:

```markdown
## Real Behavior Proof

- [ ] This change does not require RBP (documentation/test-only/refactor)
- [ ] RBP attached below:

<!-- If RBP required, attach screenshot or log here. AI-generated test output does not count. -->
```

CI applies the `needs-rbp` label automatically to any PR whose diff touches
`src/scieasy/{blocks,engine,api,workflow}/` or `frontend/src/**`. The label
blocks merge until removed by a human reviewer who has verified the RBP
artifact.

### 14.4 `mantis-proof` skill

The `mantis-proof` skill (§17) codifies the RBP procedure. It walks the
agent through:

1. Identifying the user-observable surface affected.
2. Setting up a real test environment (not mocks).
3. Capturing proof (Chrome MCP or terminal capture).
4. Attaching proof to the PR description.

The skill itself cannot satisfy the RBP gate — only a human's manual review
of the proof artifact can.

### 14.5 Why AI-generated tests don't count

Empirical observation (§2.1) and OpenClaw's published rationale: agents
write tests that pass against their model of the code, not against the
actual code. A test green from an agent that also wrote the code is a
self-consistency check, not a correctness check. The independent observer
must be a human or a test written before the code (TDD).

---

## 15. docs-agent: Active Doc Fixer with Path Allowlist

### 15.1 Purpose

In addition to **detecting** doc/code drift (§9), the regime includes an
**active fixer**: a CI workflow that runs an AI agent post-CI-green on
main, restricted to modifying only documentation paths, with a post-step
diff guard. Pattern adopted from OpenClaw's `docs-agent.yml`.

### 15.2 Workflow

`.github/workflows/docs-agent.yml`:

```yaml
name: docs-agent
on:
  workflow_run:
    workflows: [ci]
    types: [completed]
    branches: [main]
  workflow_dispatch:

permissions:
  actions: read
  contents: write

jobs:
  docs-agent:
    if: |
      github.event.workflow_run.conclusion == 'success' &&
      github.repository == 'scieasy/scieasy' &&
      github.actor != 'github-actions[bot]'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    concurrency:
      group: docs-agent-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - name: Rate-limit check
        run: scripts/audit/docs_agent_rate_limit.py --max-per-hour 1
      - uses: actions/checkout@v4
      - name: Run docs-agent
        env:
          DOCS_AGENT_PROMPT: .github/agent-prompts/docs-agent.md
        run: scripts/audit/run_docs_agent.py
      - name: Path-allowlist enforcement (post-step, three-tier check)
        # Audit P0.2 fix: covers working-tree edits, staged, AND untracked
        # files. Pure `git diff --name-only HEAD~1` only sees committed
        # history, which misses the actual post-agent modifications.
        run: |
          unstaged=$(git diff --name-only)
          staged=$(git diff --cached --name-only)
          untracked=$(git ls-files --others --exclude-standard)
          all_changed=$(printf '%s\n%s\n%s\n' "$unstaged" "$staged" "$untracked" | sort -u)
          allowed='^(docs/|README\.md$|CHANGELOG\.md$|docs/zh-CN/)'
          for f in $all_changed; do
            [ -z "$f" ] && continue
            echo "$f" | grep -E "$allowed" || {
              echo "FATAL: docs-agent modified path outside allowlist: $f"
              exit 1
            }
          done
      - name: Stage allowed paths explicitly
        # Use explicit `git add` after guard; avoids `commit -am` which would
        # miss untracked translation files.
        run: |
          git add -- docs/ README.md CHANGELOG.md 2>/dev/null || true
      - name: Create PR (audit P0.2 fix: PR-creating, not direct-push)
        # Direct-push from this workflow would (a) violate branch protection
        # if PR-required is enforced, and (b) NOT trigger downstream
        # workflow runs (GITHUB_TOKEN push behavior, audit P0.2). Instead,
        # branch off and open a PR that goes through the same required
        # checks as any other PR.
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if git diff --cached --quiet; then
            echo "No allowed changes staged; nothing to PR"; exit 0
          fi
          branch="docs-agent/refresh-$(date +%Y%m%d-%H%M)"
          git config user.name 'docs-agent[bot]'
          git config user.email 'docs-agent@scieasy.dev'
          git checkout -b "$branch"
          git commit -m 'docs: refresh documentation

Assisted-by: docs-agent:claude-opus-4-7'
          git push origin "$branch"
          gh pr create \
            --base main --head "$branch" \
            --title "docs: refresh documentation (docs-agent)" \
            --body "Auto-generated docs refresh by docs-agent. Path-allowlisted to docs/, README.md, CHANGELOG.md, docs/zh-CN/. Subject to all required CI checks like any other PR."
```

**Why PR instead of direct push** (audit P0.2):
- Branch protection requires PRs for any contributor when "Require pull
  request before merging" is set; direct-push would fail or bypass.
- `GITHUB_TOKEN`-authored pushes do NOT trigger normal workflow runs
  (documented GitHub behavior). The downstream audit cascade would silently
  skip docs-agent commits.
- A PR runs the same required checks as any other PR, preserving the
  governance posture.

### 15.3 Path allowlist

The agent may modify only:

- `docs/**`
- `README.md`
- `CHANGELOG.md`
- `docs/zh-CN/**` (translation re-generation)

It may not:

- Create new files (the allowlist is edits-only).
- Delete files.
- Rename files.
- Modify code, tests, configuration, workflows, schemas, or any path outside
  the allowlist.

The post-step diff guard enforces this independently of the agent's prompt.

### 15.4 Fail-closed posture

The agent prompt (`.github/agent-prompts/docs-agent.md`) ends with:

> When uncertain, prefer no edit with explanation. A null change is always
> safer than a wrong change.

If the agent cannot confidently fix a drift, it logs the attempted analysis
to the workflow's annotation output and exits zero (no commit).

### 15.5 Cadence

The workflow runs at most once per hour (rate-limit script). Manual
`workflow_dispatch` is permitted for testing.

---

## 16. `committer.py` Hard Tooling

### 16.1 Purpose

`scripts/committer.py` is a thin wrapper around `git add` and `git commit`
that:

1. Forbids `-A`, `-a`, and `.` arguments (explicit file list required).
2. Auto-appends `Assisted-by:` trailer based on detected agent runtime.
3. Validates pre-commit checks pass before staging.
4. Logs each commit to `docs/audit/commit-log.jsonl` with metadata.

### 16.2 Detection of agent runtime

Environment variable contract:

| Variable | Set by | Meaning |
|---|---|---|
| `SCIEASY_AGENT_RUNTIME` | Runtime startup | `Claude` / `Codex` / `Cursor` / `Aider` / `Gemini` |
| `SCIEASY_AGENT_MODEL` | Runtime startup | Model ID, e.g. `claude-opus-4-7` |
| `SCIEASY_HUMAN_OVERRIDE` | Manual export | If set, treats commit as human-authored |

Without `SCIEASY_AGENT_RUNTIME`, `committer.py` refuses to commit unless
`SCIEASY_HUMAN_OVERRIDE` is set or the git author email matches the
`docs/identity/humans.yml` registry (§25).

### 16.3 Forbidden patterns

```bash
# All of these are rejected:
python scripts/committer.py commit -A -m "..."
python scripts/committer.py commit -a -m "..."
python scripts/committer.py add .
python scripts/committer.py add -A

# Required form:
python scripts/committer.py add path/to/file1 path/to/file2
python scripts/committer.py commit -m "feat(qa): add doc-drift classifier"
```

### 16.4 Pre-commit invocation

Before staging, `committer.py` runs:

1. `pre-commit run --files <listed-files>` (fast subset relevant to changed
   files).
2. If any check fails, the commit is aborted with the failing tool's output.
3. After commit, the pre-push hook (separate) will run the full audit
   before push.

### 16.5 Commit log

Each commit is appended to `docs/audit/commit-log.jsonl`:

```json
{
  "sha": "abc123...",
  "timestamp": "2026-05-17T12:34:56Z",
  "author": "@claude",
  "runtime": "Claude",
  "model": "claude-opus-4-7",
  "files": ["docs/adr/ADR-042.md"],
  "message_first_line": "feat(adr): introduce ADR-042 QA overhaul"
}
```

The log is append-only and committed to repo as a queryable audit trail.

---

## 17. Required Skills & Cross-Runtime Installer

### 17.1 Required skill list

The following skills MUST be installed across all supported agent runtimes
before any agent commits to the repository:

| Priority | Skill | Purpose | OpenClaw analogue |
|---|---|---|---|
| P0 | `scieasy-skill-creator` | Author/validate skills (frontmatter, SKILL.md lint) | `skill-creator` |
| P0 | `doc-drift-guard` | Run §9 classifier; brief agent on current debt | (novel) |
| P0 | `provenance-tagger` | Enforce `Assisted-by:`/`Fixes:`/`ADR:` trailers via `committer.py` | implicit in `coding-agent` |
| P0 | `adr-router` | Refuse code change without an Accepted ADR reference | (novel) |
| P1 | `pr-maintainer` | Triage labels, dedup, RBP-gate enforcement | `$openclaw-pr-maintainer` |
| P1 | `mantis-proof` | RBP capture procedure | `$crabbox` + `mantis-*-proof` |
| P1 | `session-logs` | Search local agent session JSONL for drift root-cause | `session-logs` |
| P1 | `release-maintainer` | Version bump + CHANGELOG slice + tag | `$openclaw-release-maintainer` |
| P2 | `codemod-with-adr` | Run libCST codemods only when paired with ADR ref | (novel) |
| P2 | `hallucination-guard` | Verify imported symbols/URLs exist | (novel) |
| P2 | `maintainers-reverse` | Reverse-lookup MAINTAINERS for ownership before edit | (novel) |

**Note**: `docs-agent` is NOT a skill — it is a CI workflow + codex prompt
pair restricted to a path allowlist (§15). It is enumerated separately
under §17.6 below and is verified by §15.2's workflow existence check plus
the §21.4 CI aggregator, not by §17.4's skill installation check.

### 17.2 Installation paths per runtime (canonical table)

Covers BOTH **dev environment** (this repo, SciEasy contributors) AND
**prod environment** (user projects per ADR-040). Audit P2.3 fix.

| Runtime | SciEasy source tree (dev) | Project-local install (dev or prod) | User-global install | Discovery limitation | Governing |
|---|---|---|---|---|---|
| Claude Code | `_skills/scieasy/<name>/SKILL.md` | `.claude/skills/<name>/SKILL.md` (flat per ADR-040 Add.1) | `~/.claude/skills/<name>/SKILL.md` | Skill registry does not recurse; paths must be flat (one level under `skills/`) | ADR-040 §3.4 + Add.1 |
| Codex | (same `_skills/`) | `.codex/skills/<name>/SKILL.md` AND `.agents/skills/<name>/SKILL.md` (flat) | `~/.codex/skills/<name>/SKILL.md` | Same flat-only constraint | ADR-040 §3.7 + §3.9 + Add.1 |
| Cursor | (same `_skills/`) | `.cursor/rules/<name>.md` | n/a (no user-global concept) | Cursor uses single-file `.md` rules, not directories | (deferred ADR) |
| Aider | (same `_skills/`) | `.aider.skills/<name>/SKILL.md` | `~/.aider.skills/<name>/SKILL.md` | Convention; Aider has no official "skills" concept | (deferred ADR) |
| Gemini | (same `_skills/`) | `.gemini/skills/<name>/SKILL.md` | `~/.gemini/skills/<name>/SKILL.md` | Convention | (deferred ADR) |

`agent_provisioning` (§17.3) is the single source-of-truth installer that
materializes a skill from `_skills/scieasy/<name>/` into every runtime's
project-local path on `scieasy init` / `ApiRuntime.create_project`. User-
global installation is opt-in via `scieasy install --skill <name>
--scope user`.

### 17.3 Cross-runtime installer

The `agent_provisioning` system (ADR-040 §3.5-3.8) is extended to handle the
required-skill manifest. Invocation:

```bash
python -m scieasy.agent_provisioning install --skill-manifest docs/skills/required.yaml
```

Behavior:

- Reads `docs/skills/required.yaml` (the canonical required-skill list).
- For each supported runtime, installs/updates skills to the runtime-specific path.
- Verifies installation via a probe script per runtime.
- Outputs installation report to `docs/audit/skill-install-report.json`.

### 17.4 CI verification

A CI job `skill-installation-check` verifies, for every required skill:

- The skill file exists in the project-local installation path for at least
  one runtime.
- The skill's SKILL.md passes frontmatter validation.
- The skill's declared dependencies (other skills) are also present.

The job does not run actual installs in CI (that requires real runtimes); it
verifies the manifest is consistent and the skills as defined are installable.

### 17.5 Skill authoring rules

Every SciEasy skill MUST:

- Begin life via `scieasy-skill-creator` (no ad-hoc skill files).
- Include `When uncertain, prefer no edit with explanation.` in its
  guidance section.
- Declare its required runtime dependencies.
- Pass `scieasy-skill-creator validate <path>` before commit.

### 17.6 CI workflows required (not skills)

The following CI workflows are required by ADR-042 but are NOT skills (they
do not install into agent runtimes; they run inside GitHub Actions). They
appear here to be explicit about what falls outside §17.4's skill
installation check:

| Workflow file | Purpose | Trigger | Reference |
|---|---|---|---|
| `.github/workflows/audit.yml` | Aggregator + every audit tool | PR + push | §21.4 |
| `.github/workflows/docs-agent.yml` | Active doc fixer with path allowlist | `workflow_run` post-CI on main | §15 |
| `.github/workflows/translation.yml` | Auto-regenerate `docs/zh-CN/**` | Doc change push | §22.7 |
| `.github/workflows/governance-modification.yml` | Recursive self-check on governance edits | PR touching `.governance-paths.yaml` paths | ADR-043 §3.5 |
| `.github/workflows/adr-042-conformance.yml` | Weekly tracker + meta-test sweep | Weekly cron | ADR-043 §2 |

Each CI workflow's existence is verified by the §21.4 CI aggregator's
`check` job; their internal correctness is verified by `actionlint` and
`zizmor` in §21.3 pre-commit.

---

## 18. Persona Routing

### 18.1 Personas as AGENTS.md tokens (not skills)

Personas are policy-routing tokens declared in `AGENTS.md`. They are not
packaged skills. They identify a role and its constraints; the agent
fulfilling the role uses whatever skills it needs.

### 18.2 Defined personas

| Token | Role | Allowed paths | Required gates |
|---|---|---|---|
| `$scieasy-docs` | Doc author / drift fixer | `docs/**`, `README.md`, `CHANGELOG.md` | Frontmatter lint, fact-drift, translation-queue |
| `$scieasy-pr-maintainer` | PR triage and merge | (no path edits) | Label management, RBP verification, Codex reconcile |
| `$scieasy-release-maintainer` | Version bumps and tags | `pyproject.toml`, `CHANGELOG.md`, tags | Approval from `@jiazhenz026`, all CI green, audit report archived |
| `$scieasy-adr-author` | ADR drafting and revision | `docs/adr/**`, `docs/spec/**` | Frontmatter validation, supersession check, contradiction audit (§28.1) |
| `$scieasy-rbp-prover` | Real-Behavior-Proof capture | (no code edits) | Chrome MCP / terminal capture, PR comment with artifact |
| `$scieasy-adr-auditor` | Internal-contradiction audit (§28.1) | (read-only) | None (it produces findings, doesn't merge) |

### 18.3 Routing rules

When dispatched work matches a persona's scope, the dispatcher MUST invoke
the persona token, e.g.:

```
$scieasy-docs: refresh translation for docs/adr/ADR-042.md after edit
```

The persona's scope is enforced by the path allowlist in its definition.

---

## 19. Workflow v2 (7-stage)

### 19.1 Motivation

The prior 6-gate workflow (CLAUDE.md Appendix A) enforces structure but
provides minimal guidance. Empirically, agents complete the 6 gates without
producing one-pass quality work — they pass the gates but skip artifacts
(RBP, codemod, MAINTAINERS update, translation queue), requiring follow-up
PRs.

Workflow v2 redesigns around the principle:

> Gates should guide agents to one-pass quality, not merely block bad PRs.

Each stage carries:

1. A machine-checkable definition-of-done.
2. A concrete how-to command set.
3. A guidance prompt rendered on stage entry.
4. An auto-loaded context summary (relevant ADRs, MAINTAINERS, skills).

### 19.2 The seven stages

<!-- TODO(#NNN): substitute fact-registered values after Phase 1: {{ facts.workflow.stages | bullet_list }} -->

| # | Stage | Done when | How |
|---|---|---|---|
| 1 | `start_and_route` | Task started + ADRs declared + MAINTAINERS resolved + codemod plan (if contract change) + skill plan (if new skill) | `gate.py start "title"` then `gate.py advance ... start_and_route --data '{...}'` |
| 2 | `create_issue` | Issue created with strict v2 template | `gh issue create --template feature-v2.yml` |
| 3 | `change_plan` | Plan posted as issue comment; files-in-plan within declared ADR scope | `gh issue comment --body-file plan.md` |
| 4 | `branch` | Branch from latest `main`; name `<type>/issue-<N>/<adr>/<slug>` | `git fetch origin && git checkout -b ...` |
| 5 | `implement_validate` | Implementation complete; `python -m scieasy.qa.audit.full_audit --pre-push` returns 0 errors; all commits carry `Assisted-by:` if agent-authored | iterative; gate auto-advances when audit returns clean |
| 6 | `complete_artifacts` | Docstrings + ADR governs updated + MAINTAINERS updated + translation enqueued + CHANGELOG entry + codemod committed (if contract change) + RBP attached + skills installed cross-runtime | `python -m scieasy.qa.audit.complete_artifacts --check` |
| 7 | `submit_reconcile` | PR opened, CI all green, Codex review reconciled (all P0/P1 addressed) | `gh pr create` then auto-wait Codex |

### 19.3 Per-stage guidance

When an agent advances into a stage, the gate prints a guidance message:

```
=== Stage 1: start_and_route ===
You are starting task TASK_20260517_qa_overhaul.

Auto-loaded context:
  - Likely affected files (from your declared title):
      src/scieasy/qa/**
      docs/adr/ADR-042.md
  - Governing ADRs covering this scope:
      ADR-042 (Draft, you are authoring it)
  - MAINTAINERS owner: @jiazhenz026
  - Required skills present in your runtime:
      doc-drift-guard, provenance-tagger, adr-router
  - Missing skills:
      (none)

To advance, declare:
  - Which ADRs apply (`adrs: [42]`)
  - Whether this introduces a contract change (codemod required: `contract_change: true|false`)
  - Whether this introduces a new skill (cross-runtime install required: `new_skills: []`)

Run: gate.py advance TASK_20260517_qa_overhaul start_and_route \\
  --data '{"adrs": [42], "contract_change": false, "new_skills": []}'
```

### 19.4 Auto-advance mode

Each stage supports `--auto`:

```bash
gate.py advance TASK_ID stage_name --auto
```

In auto mode, the gate runs its validators directly. If all pass, the stage
advances. If any fail, the gate prints the failing check's output and stays
at the current stage. This is the recommended mode for agents.

### 19.5 Stage definitions in code

```python
# src/scieasy/qa/workflow/gate.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Literal
from pydantic import BaseModel, ConfigDict


class StageContext(BaseModel):
    """Per-stage runtime context passed to each Validator."""
    model_config = ConfigDict(extra="forbid")
    task_id: str
    stage_name: str
    repo_root: str
    pr_number: int | None
    branch: str
    declared_data: dict[str, object]


class ValidationResult(BaseModel):
    """Outcome of a single Validator invocation."""
    model_config = ConfigDict(extra="forbid")
    validator_id: str
    status: Literal["pass", "fail", "skip"]
    message: str
    blocking: bool = True


class Validator(Protocol):
    """Callable contract for stage-level check functions.

    A Validator inspects a StageContext and returns a ValidationResult.
    Used by Workflow v2 (§19) to compose stage definition-of-done from
    machine-checkable building blocks.
    """
    validator_id: str
    blocking: bool

    def __call__(self, ctx: StageContext) -> ValidationResult: ...


@dataclass
class StageDefinition:
    name: str
    requires: list[str]               # prior stages that must be complete
    validations: list[Validator]      # machine-executable check functions
    guidance_template: str            # Jinja2 template for entry prompt
    auto_advance: bool                # whether --auto can advance this stage
    sub_checklist: list[str] = field(default_factory=list)
```

The seven stages are defined in `.workflow/schema-v2.yaml`, loaded by
`gate.py` at startup. `extract_workflow_facts.py` (§7.5.3) reads this file
to produce `facts.workflow.*`. Individual validators are registered in
`src/scieasy/qa/workflow/validators/` (one module per validator), allowing
new validators to be added without modifying `gate.py`.

### 19.6 Migration from 6-gate

| Old 6-gate stage | New v2 stage(s) |
|---|---|
| `create_issue` | 1 + 2 |
| `write_change_plan` | 3 |
| `create_branch` | 4 |
| `update_docs` | 6 (expanded) |
| `update_changelog` | 6 (merged in) |
| `submit_pr` | 7 |
| (new) | 5 `implement_validate` — explicit local validation gate |

Phase 1 ships v2; Phase 2 deprecates v1 entirely.

---

## 20. libCST Codemods Discipline

### 20.1 Statement

> Any ADR whose `governs.contracts` introduces a breaking change to an
> existing contract MUST ship a paired libCST codemod under
> `tools/codemods/adr-NNN-<slug>.py`. CI verifies that applying the codemod
> to the current tree yields zero diff (meaning all call sites are already
> migrated).

### 20.2 Pattern

Borrowed from the Linux kernel Coccinelle pattern: when an API changes, the
maintainer ships a semantic patch that automatically updates every caller.
For Python, libCST is the equivalent (concrete syntax tree, preserves
formatting, supports refactoring).

### 20.3 Codemod metadata

Each codemod file begins with a pydantic-validated metadata block:

```python
# tools/codemods/adr-042-rename-foo-to-bar.py
"""
ADR: 42
Description: Rename scieasy.X.foo to scieasy.X.bar per ADR-042 §N
Affects:
  - scieasy.X.foo (renamed to scieasy.X.bar)
Tests:
  - tests/codemods/test_adr_042_rename.py
"""

import libcst as cst
from scieasy.qa.codemods.base import CodemodBase

class RenameFooToBar(CodemodBase):
    """Rename foo -> bar."""
    # ...
```

The metadata is parsed by `scieasy.qa.audit.codemod_lint`.

### 20.4 CI verification

A CI job `codemod-applied-check`:

1. For each `tools/codemods/adr-NNN-*.py`, applies the codemod to a clone
   of the current tree.
2. Compares output to original tree.
3. If diff is non-empty, the codemod has not been applied to all call sites.
   The job emits the diff and fails.

### 20.5 Codemod ships in same PR as the ADR

The expected workflow:

1. ADR introduces or changes a contract.
2. Same PR includes:
   - The ADR update.
   - The contract change (e.g., rename in code).
   - The codemod that updates all call sites.
   - Test verifying the codemod is idempotent.
3. CI runs the codemod against the full tree; expects zero diff.
4. Reviewers verify the codemod logic.

Without the codemod, the PR cannot merge. This forces the discipline:
contract changes are accompanied by the migration, not deferred.

---

## 21. Tool Stack & CI Topology

### 21.1 Final tool stack

| Category | Tool | Purpose | Config location |
|---|---|---|---|
| Lint (Python) | `ruff` (rules: E, W, F, I, N, UP, B, SIM, RUF, D, S, ANN, PTH, RET, PT, DOC) | All-in-one linter; includes pydocstyle (D) and bandit (S) subsets | `pyproject.toml [tool.ruff]` |
| Format | `ruff format` | Code formatting | `pyproject.toml` |
| Type | `mypy --strict` (without `ignore_missing_imports`) | Primary type checker | `pyproject.toml [tool.mypy]` |
| Type | `pyright` | Secondary type checker for cross-verification | `pyrightconfig.json` |
| Docstring coverage | `interrogate` | Quantify docstring presence; target 100% public | `pyproject.toml [tool.interrogate]` |
| Docstring↔signature | `pydoclint` | Verify docstring matches signature | `pyproject.toml [tool.pydoclint]` |
| API surface | `griffe` (+ `griffe-pydantic`) | Detect breaking public-API changes | `pyproject.toml [tool.griffe]` |
| Dead code | `vulture` | Find unreachable/unused code | `pyproject.toml [tool.vulture]` |
| Complexity | `xenon` | Enforce max McCabe complexity | `pyproject.toml [tool.xenon]` |
| Security | `pip-audit` | Dependency vulnerabilities | (no config; CLI) |
| Docs build | `sphinx` + `sphinx-autoapi` + `myst-parser` + `sphinx-needs` + `furo` + `sphinx-substitution-extensions` | API ref + cross-ref + theme + facts substitution | `docs/sphinx/conf.py` |
| Doc lint | `markdownlint-cli2` | Markdown style | `.markdownlint.yaml` |
| Doc lint | `sphinx-lint` | Sphinx-specific lint | (no config) |
| Link check | Sphinx `linkcheck` builder | External URL validation | `docs/sphinx/conf.py` |
| Doc examples | `pytest-examples` | Execute fenced code blocks in docs | `pyproject.toml` |
| Workflow lint | `actionlint` | GitHub Actions YAML lint | (no config) |
| Workflow security | `zizmor` | GitHub Actions security audit | (no config) |
| Spell check | `codespell` | Common typo detection | `.codespellrc` |
| YAML | `yamllint` | YAML format | `.yamllint` |
| Config format | `pyproject-fmt` | pyproject.toml format | (no config) |
| Import boundaries | `import-linter` | Layer dependency contracts | `pyproject.toml [tool.importlinter]` |
| Pre-commit | `pre-commit` | Hook framework | `.pre-commit-config.yaml` |
| Commit lint | `commitizen` | Conventional commit format | `pyproject.toml [tool.commitizen]` |
| Test | `pytest` + `-xdist` + `-timeout` + `-randomly` + `-examples` | Parallel, timeout, randomized order, doc examples | `pyproject.toml [tool.pytest.ini_options]` |
| Coverage | `pytest-cov` + `coverage` | Coverage measurement | `pyproject.toml [tool.coverage.*]` |
| Codemod | `libcst` | Concrete-syntax-tree refactoring | (no config; library) |
| Schema | `pydantic v2` + `pydantic-settings` | Schema validation + env var contracts | (library) |

### 21.2 Frontend tool stack (TypeScript)

| Category | Tool |
|---|---|
| Lint | `eslint` with strict config + `eslint-plugin-tsdoc` + `eslint-plugin-jsdoc` |
| Format | `prettier` |
| Type | `tsc --noEmit` |
| Test | `vitest` |
| Doc | `typedoc` (cross-references back to Python via custom plugin) |

The frontend stack is governed by the same rigor as Python; see §21.4 for
shared CI gates.

### 21.3 pre-commit topology (local, ≤ 5s wall time on typical edits)

```yaml
# .pre-commit-config.yaml (excerpt)
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks: [trailing-whitespace, end-of-file-fixer, check-yaml, check-json,
            check-added-large-files, check-merge-conflict, detect-private-key]
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.1
    hooks: [ruff, ruff-format]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.15.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-PyYAML, ...]
  - repo: https://github.com/codespell-project/codespell
    rev: v2.3.0
    hooks: [codespell]
  - repo: https://github.com/woodruffw/zizmor
    rev: v1.22.0
    hooks: [zizmor]
  - repo: https://github.com/rhysd/actionlint
    rev: v1.7.10
    hooks: [actionlint]
  - repo: local
    hooks:
      - id: frontmatter-lint
        name: ADR/spec frontmatter validation
        entry: python -m scieasy.qa.audit.frontmatter_lint
        language: system
        files: ^docs/(adr|spec)/.*\.md$
      - id: fact-drift
        name: Fact-substitution check
        entry: python -m scieasy.qa.audit.fact_drift
        language: system
        files: \.(md|rst)$
      - id: doc-drift
        name: Doc/code drift classification
        entry: python -m scieasy.qa.audit.doc_drift --quick
        language: system
        pass_filenames: false
      - id: trailer-lint
        name: Git trailer validation
        entry: python -m scieasy.qa.audit.trailer_lint
        language: system
        stages: [commit-msg]
      - id: committer-only
        name: Reject commits not via committer.py for agents
        entry: python -m scieasy.qa.audit.committer_enforce
        language: system
        stages: [pre-commit]
```

### 21.4 CI topology

`.github/workflows/audit.yml` (the canonical CI workflow for ADR-042):

```yaml
name: ci
on: [pull_request, push]
jobs:
  # Aggregator job; only this is required for branch protection
  check:
    needs: [lint, typecheck, docs-build, audit, test, frontend]
    runs-on: ubuntu-latest
    steps:
      - run: echo "All required checks passed"

  lint:
    # ruff, codespell, yamllint, markdownlint, actionlint, zizmor
  typecheck:
    # mypy --strict + pyright
  docs-build:
    # sphinx-build -b html -W --keep-going + sphinx linkcheck + pytest-examples
  audit:
    # python -m scieasy.qa.audit.full_audit (doc_drift + fact_drift + closure + frontmatter_lint + trailer_lint + skill-installation-check)
  test:
    # pytest -n auto --timeout=60 --cov --cov-fail-under=90
  frontend:
    # npm run lint && npm run typecheck && npm run test && npm run build && stale-dist-check
  docs-agent-allowlist:
    # workflow_run guard for docs-agent.yml
  translation:
    # workflow_run trigger for translation.yml on doc change
```

### 21.5 Branch protection

A single required check (`check`) is configured on `main`. All gates feed
into that aggregator job. This pattern (adopted from pydantic) keeps the
GitHub branch-protection UI clean and prevents required-check-list drift.

### 21.6 Coverage targets

Phase 1 retains 70% (current). Phase 3 ratchet: 80% by mid-Phase, 90% by end.
Phase 4 baseline: 90%. New code under `src/scieasy/qa/` MUST land at 95%+
from day one (it's the tooling everyone else depends on; it cannot have
untested code paths).

---

## 22. Documentation Language Policy + Translator

### 22.1 Language policy

> All source documentation MUST be written in English (prose, headings, link
> text, frontmatter human-readable fields). Non-English prose outside
> `docs/zh-CN/**` is a CI error.

**Unicode allowlist** (audit P2.2 fix): scientific and typographic Unicode
remains permitted in source docs — Greek letters, math symbols, units,
arrows, em-dashes, smart quotes, contributor names with diacritics, DOIs
with non-ASCII metadata, etc. The lint enforces "English prose" via:

1. Language detection on prose paragraphs (e.g., `langdetect` or
   `lingua-py`); non-English-detected prose = error.
2. A scientific-symbol allowlist (Unicode blocks: Greek and Coptic, Math
   Operators, Letterlike Symbols, Arrows, General Punctuation, Latin-1
   Supplement diacritics) that bypasses prose-language detection.
3. Raw-byte ASCII rejection is NOT used (it would block legitimate
   scientific notation).

Rationale: a single source language simplifies machine processing (link
resolution, fact substitution, drift detection) and onboarding for an
international contributor base, but a raw ASCII filter would block
scientific content; an English-source policy with Unicode allowlist
preserves both goals.

### 22.2 Translation requirement

For every English source document, a corresponding Chinese translation MUST
exist under `docs/zh-CN/` with mirrored path structure:

```
docs/adr/ADR-042.md            → docs/zh-CN/adr/ADR-042.md
docs/specs/foo-spec.md         → docs/zh-CN/specs/foo-spec.md
docs/architecture/ARCHITECTURE.md → docs/zh-CN/architecture/ARCHITECTURE.md
```

Translations are auto-generated by `scripts/translate_docs.py`, not by
agents. This is deliberate: agent translation hallucinates; deterministic
API translation does not (or fails loudly).

### 22.3 `scripts/translate_docs.py`

Translator script with provider-agnostic API:

```python
# scripts/translate_docs.py
import argparse
from scieasy.qa.translation import TranslatorClient, DeepLProvider, GoogleProvider, AzureProvider

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["deepl", "google", "azure"], default="deepl")
    parser.add_argument("--source", default="docs", help="Source docs root")
    parser.add_argument("--target", default="docs/zh-CN", help="Target translations root")
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--incremental", action="store_true",
                        help="Only translate files whose source SHA changed")
    args = parser.parse_args()

    client = TranslatorClient.from_provider_name(args.provider)
    for src_path, target_path in walk_pairs(args.source, args.target):
        if args.incremental and _translation_up_to_date(src_path, target_path):
            continue
        translated = client.translate_file(src_path, source_lang="en", target_lang=args.locale)
        write_translation(target_path, translated, source_sha=_sha(src_path))
```

### 22.4 Default provider: DeepL

Rationale: highest translation quality among major APIs; supports OAuth +
API key; reasonable free tier.

Pluggable providers: Google Cloud Translate (cheaper, lower quality),
Azure Translator (medium), plus a `manual` provider for development without
external calls.

### 22.5 Configuration via env vars

`pydantic-settings` for translator config:

```python
# src/scieasy/qa/translation/settings.py
class TranslationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCIEASY_TRANSLATION_")
    provider: Literal["deepl", "google", "azure", "manual"] = "deepl"
    deepl_api_key: str | None = None
    google_credentials_path: str | None = None
    azure_endpoint: str | None = None
    azure_key: str | None = None
```

Keys are injected via GitHub Secrets in CI. Local development can use the
`manual` provider (no network calls; emits a stub translation marked
"needs-manual").

### 22.6 Incremental translation

Translation cache keyed by source-file SHA:

- Each `docs/zh-CN/X.md` carries frontmatter `source_sha: <sha-of-en-source>`.
- `translate_docs.py --incremental` re-translates only files whose source
  SHA changed.
- CI check `translation_ok` (in AuditReport): all zh-CN files have
  `source_sha` matching current English source.

### 22.7 Translation workflow CI

`.github/workflows/translation.yml` triggers on changes to `docs/**`
(excluding `docs/zh-CN/**`):

```yaml
name: translation
on:
  push:
    branches: [main]
    paths: ['docs/**', '!docs/zh-CN/**']
jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/translate_docs.py --incremental
        env:
          SCIEASY_TRANSLATION_DEEPL_API_KEY: ${{ secrets.DEEPL_API_KEY }}
      - name: Path-allowlist enforcement (three-tier check)
        # Audit P0.2 fix: cover unstaged, staged, AND untracked translation
        # files; pure `git diff --name-only HEAD~1` misses new files.
        run: |
          unstaged=$(git diff --name-only)
          staged=$(git diff --cached --name-only)
          untracked=$(git ls-files --others --exclude-standard)
          all_changed=$(printf '%s\n%s\n%s\n' "$unstaged" "$staged" "$untracked" | sort -u)
          for f in $all_changed; do
            [ -z "$f" ] && continue
            echo "$f" | grep -E '^docs/zh-CN/' || {
              echo "FATAL: translation workflow modified $f outside docs/zh-CN/"; exit 1
            }
          done
      - name: Stage zh-CN paths explicitly
        run: git add -- docs/zh-CN/ 2>/dev/null || true
      - name: Create PR (audit P0.2 fix)
        # PR-creating, not direct-push (same rationale as docs-agent §15.2):
        # branch protection + GITHUB_TOKEN-push-does-not-trigger-workflows.
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if git diff --cached --quiet; then
            echo "No translation changes; nothing to PR"; exit 0
          fi
          branch="translator/zh-CN-$(date +%Y%m%d-%H%M)"
          git config user.name 'translator[bot]'
          git config user.email 'translator@scieasy.dev'
          git checkout -b "$branch"
          git commit -m 'docs(zh-CN): refresh translation

Assisted-by: translator:deepl-api-v2'
          git push origin "$branch"
          gh pr create \
            --base main --head "$branch" \
            --title "docs(zh-CN): refresh translation" \
            --body "Auto-generated zh-CN translation refresh. Path-allowlisted to docs/zh-CN/ only."
```

### 22.8 Phase 3 backfill

All existing docs in `docs/` (currently primarily English; minor Chinese
mixed in) are normalized to pure English during Phase 3. The `translate_docs.py`
runs once on the cleaned set to populate `docs/zh-CN/**` initially.

---

## 23. Docs Build & Cross-reference Enforcement

### 23.1 Engine

Sphinx with the following extensions:

- `sphinx-autoapi`: extracts API reference from `src/scieasy/` (no import,
  static analysis).
- `myst-parser`: enables Markdown alongside RST.
- `sphinx-needs`: requirement-traceability extension; links ADRs to code and
  tests.
- `furo`: theme.
- `sphinx-substitution-extensions`: enables `{{ facts.X }}` substitutions.
- `intersphinx`: cross-project references (pydantic, fastapi, zarr, etc.).

### 23.2 Build configuration

```python
# docs/sphinx/conf.py (excerpt)
nitpicky = True
nitpick_ignore_regex = [
    # Allowlist: external types we can't resolve
    (r"py:class", r"_typeshed\..*"),
]
autoapi_dirs = ["../../src/scieasy"]
autoapi_options = ["members", "undoc-members", "show-inheritance",
                   "show-module-summary", "imported-members"]
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
    "zarr": ("https://zarr.readthedocs.io/en/stable", None),
}
```

### 23.3 Build invocation

```bash
sphinx-build -b html docs/sphinx _build/html -W --keep-going
sphinx-build -b linkcheck docs/sphinx _build/linkcheck
```

`-W` turns warnings into errors; `--keep-going` collects all errors rather
than stopping at the first.

### 23.4 Cross-reference enforcement (via nitpicky)

When prose references a symbol:

```markdown
The :py:class:`scieasy.qa.schemas.frontmatter.ADRFrontmatter` model validates...
```

Sphinx attempts to resolve `scieasy.qa.schemas.frontmatter.ADRFrontmatter`
against the autoapi-extracted symbol table. If unresolvable, the build fails.

This catches phantom-symbol references in prose (c-class drift) automatically.

### 23.5 pytest-examples integration

Every fenced code block in any ADR, spec, or doc is executed as a test:

```python
# tests/qa/test_doc_examples.py
import pytest
from pytest_examples import find_examples, CodeExample, EvalExample

@pytest.mark.parametrize("example", find_examples("docs"), ids=str)
def test_doc_examples(example: CodeExample, eval_example: EvalExample):
    if "pytest-examples: skip" in example.prefix:
        pytest.skip("explicit skip")
    eval_example.run(example)
```

Code blocks that should not be executed (e.g., shell commands, pseudocode)
carry a leading comment `# pytest-examples: skip`.

**Fence-type discipline (audit P0.4 fix)**:

| Fence type | Use for | pytest-examples behavior |
|---|---|---|
| ` ```python ` | Runnable Python examples (correct imports, complete classes, executable) | Discovered + executed |
| ` ```python\n# pytest-examples: skip ` | Pseudocode, design sketches, or examples that intentionally raise `NotImplementedError` | Discovered + explicitly skipped (still parsed by syntax check) |
| ` ```text ` (or no language tag) | Free-form pseudocode without Python syntax (allows ellipses, prose mixed with code, comments-only blocks) | NOT discovered |
| ` ```bash ` / ` ```yaml ` / ` ```toml ` / ` ```jsonl ` / ` ```jinja ` etc. | Shell, config, structured-data snippets | NOT discovered |

During Phase 1 (when pytest-examples is enabled), all existing ADR fenced
blocks under `docs/{adr,specs}/` are reviewed and re-fenced per this table.
Until Phase 1 closes, the §3.0 transitional exemption covers the gap: any
`python` block that doesn't yet carry the right fence type is exempted by
§3.0 clause (3).

### 23.6 ADR-042's own algorithm pseudocode handling

The full `doc_drift.py` algorithm (§9.2) is pseudocode; it cannot be
executed. Per the meta-recursive self-compliance requirement (§28), the
pseudocode is held in a companion file
`docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` with explicit
`pytest-examples: skip` markers, and the main ADR includes only a
truncated stub plus a reference to the companion file.

---

## 24. Audit Reports

### 24.1 Generation cadence

| Trigger | Tools run | Output |
|---|---|---|
| Pre-commit | doc_drift quick, fact_drift, frontmatter_lint, trailer_lint | Reported inline; commit blocked on errors |
| Pre-push | Full audit (doc_drift, fact_drift, closure, frontmatter_lint, trailer_lint, skill-installation-check) | `docs/audit/reports/local/<sha>.json` (gitignored locally) |
| PR CI | Full audit | Posted as PR annotation; uploaded as workflow artifact |
| Weekly cron | Full audit + griffe API-surface diff vs previous week | PR to commit report to `docs/audit/reports/YYYY-MM-DD/` |
| On-demand | `python -m scieasy.qa.audit.full_audit --output PATH` | User-specified |

### 24.2 Storage and retention

- `docs/audit/reports/YYYY-MM-DD/` — committed, immutable, retained 90 days.
- `docs/audit/latest/` — symlink to most recent.
- `docs/audit/archive/YYYY/MM/` — older reports archived (still in git history).
- `docs/audit/overrides.log` — append-only log of Tier 1/2 human overrides (§25).
- `docs/audit/commit-log.jsonl` — append-only commit metadata (§16.5).

### 24.3 Consumer story

| Consumer | Reads | Purpose |
|---|---|---|
| CI annotator | `latest/full.json` | Per-line PR comments |
| `doc-drift-guard` skill | `latest/full.json` | Brief agent on current debt before they edit |
| Weekly summary | All reports in past 7 days | Trend analysis |
| Human review | HTML render of `latest/full.json` | Direct browsing |

---

## 25. Human Developer Exemption Principle

### 25.1 Statement

> The QA regime applies to AI agents in full. Human developers receive
> documented exemptions from process-overhead rules (trailers, gates,
> wrappers) but receive NO exemptions from quality-baseline rules (tests,
> lint, types, ADRs, schemas, closure, fact substitution).

### 25.2 Identification

Multi-signal identification of contributor type:

| Signal | Implies |
|---|---|
| `Assisted-by:` trailer present | Agent |
| Commit made via `scripts/committer.py --agent` | Agent |
| `SCIEASY_AGENT_RUNTIME` env var set | Agent |
| GitHub Actions bot account | Bot |
| Commit author email matches `docs/identity/humans.yml` registry | Human |
| Commit author email + GPG/SSH signature matches registered key | Human (Tier 2 eligible) |
| None of the above | **Unknown → treated as Agent (strictest)** |

### 25.3 Human identity registry

```yaml
# docs/identity/humans.yml — pydantic-validated
version: 1
humans:
  - github: "@jiazhenz026"
    email: "jiazhenz026@gmail.com"
    tier: maintainer
    signing_key: "ed25519:AAAA..."
    joined: 2026-01-01
    notes: "Project owner"
```

The pydantic schema enforcing this file:

```python
# src/scieasy/qa/schemas/identity.py
from __future__ import annotations
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from .frontmatter import GitHandle


class HumanTier(StrEnum):
    CONTRIBUTOR = "contributor"
    MAINTAINER = "maintainer"


SigningKey = Annotated[
    str, Field(pattern=r"^(ed25519|rsa|ecdsa|gpg):[A-Za-z0-9+/=._-]+$")
]


class HumanIdentity(BaseModel):
    """Single entry in docs/identity/humans.yml."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    github: GitHandle
    email: EmailStr
    tier: HumanTier
    signing_key: SigningKey | None = None
    joined: date
    notes: str | None = None

    @property
    def requires_signing_key(self) -> bool:
        """Tier 2 humans must have a signing key registered."""
        return self.tier == HumanTier.MAINTAINER


class IdentityRegistry(BaseModel):
    """Full docs/identity/humans.yml file."""
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    humans: list[HumanIdentity]

    def lookup_by_email(self, email: str) -> HumanIdentity | None:
        for h in self.humans:
            if h.email == email:
                return h
        return None

    def lookup_by_github(self, github: GitHandle) -> HumanIdentity | None:
        for h in self.humans:
            if h.github == github:
                return h
        return None
```

`HumanIdentity` and `IdentityRegistry` are governed by ADR-042 §25 and
consumed by `scripts/committer.py` (§16.2), the `governance_mod_guard` hook
(ADR-043 §3.3), and any tier-discrimination check across the QA pipeline.

### 25.4 Tier matrix

| Rule | Tier 0 (Agent) | Tier 1 (Human contributor) | Tier 2 (Maintainer) |
|---|---|---|---|
| `Assisted-by:` trailer required | Required | Not required | Not required |
| `committer.py` required | Required | Recommended | Recommended |
| `git add .` / `-A` forbidden | Forbidden | Allowed | Allowed |
| `git commit --amend` forbidden | Forbidden | Allowed | Allowed |
| Workflow v2 (7-stage) | Required | Required (with trivial fast-lane) | Required (with broader fast-lane) |
| Trivial fast-lane | Not eligible | ≤ 150 lines AND meets §25.5 four conditions | ≤ 450 lines AND meets §25.5 four conditions |
| `Human-Override:` trailer (narrow per-rule exemption) | Not available | Available (per §13.1) for documented one-off exemptions; logged in §25.6 | Available (also use `Maintainer-Override:` for broader scope) |
| RBP required | Required (when class matches §14.2) | Required for UI/runtime; docs-only exempt | Same as Tier 1 |
| Codex review reconcile required | Required | Skippable with `Reviewed-locally:` trailer | Skippable with `Maintainer-Override:` trailer |
| Self-PR merge | Forbidden | Forbidden | Allowed in hotfix mode (with trailer) |
| pre-commit full audit | Required | Critical-only fast lane | Critical-only fast lane |
| Lint / type / test / CI gates | Required | Required (no exemption) | Required (no exemption) |
| ADR for architectural decisions | Required | Required | Required |
| Frontmatter schema | Required | Required | Required |
| Bidirectional closure | Required | Required | Required |
| Fact substitution | Required | Required | Required |

### 25.5 Trivial change fast-lane

A Tier 1 or Tier 2 human may declare `--trivial "<reason>"` on a commit when:

1. The diff is ≤ 150 lines (Tier 1) or ≤ 450 lines (Tier 2).
2. The change does not touch governed paths under `src/scieasy/{core,qa}/`.
3. The change does not introduce any new public symbol.
4. The change is limited to docs, tests, comments, or typo fixes.

When all four conditions hold, the contributor may bypass gates 2–6 of
Workflow v2 (jumping directly from gate 1 to gate 7). Gate 7 (PR submit)
still runs full CI.

CI validates the `--trivial` declaration:

- Verifies diff size matches the declared tier limit.
- Verifies no governed-path touch.
- Verifies no public-symbol addition (uses griffe diff).
- On any failure, the trivial bypass is revoked and full workflow is required.

### 25.6 Override audit

Every use of `Maintainer-Override:`, `Reviewed-locally:`, `Human-Override:`,
or `--trivial` is appended to `docs/audit/overrides.log` (append-only):

```jsonl
{"sha": "abc...", "author": "@jiazhenz026", "tier": "maintainer", "kind": "Maintainer-Override", "reason": "hotfix for production outage", "timestamp": "2026-05-17T..."}
{"sha": "def...", "author": "@contributor", "tier": "contributor", "kind": "Human-Override", "reason": "narrow exemption: skip RBP for typo-only PR", "timestamp": "2026-05-17T..."}
{"sha": "ghi...", "author": "@contributor", "tier": "contributor", "kind": "--trivial", "reason": "fixing broken link in README", "timestamp": "2026-05-17T..."}
```

Monthly review summarizes override patterns; repeated overrides on the same
rule by the same author (regardless of tier) auto-open a discussion issue.

The `Human-Override:` trailer is the narrow per-rule exemption mechanism
for Tier 1 humans; the `Maintainer-Override:` trailer is the broader-scope
mechanism reserved for Tier 2 maintainers. Both require a free-text reason
and both are equally logged; the tier distinction limits scope, not
visibility.

### 25.7 Why this is not "agent vs human" discrimination

The exemptions are **process burden**, not quality. A human and an agent
must both:

- Write tests for new code.
- Pass lint, type, audit checks.
- Document architectural decisions in ADRs.
- Comply with frontmatter and schema rules.
- Maintain bidirectional closure.

The exemptions are about the **mechanics** that agents need but humans
find friction-heavy: explicit file lists in `git add`, mandatory trailers,
multi-stage gate progression for tiny changes. Humans get to use `git
commit --amend` and edit small typos quickly. Quality of the result is
identical.

---

## 26. Seven-Step Phased Rollout (Phase 0 → Phase 5)

### 26.0 Consolidated phase ownership table

Per audit P2.3, every phase has explicit accountable roles. ADR-043 and
ADR-044 phase deliverables share these owners (no separate owner table
needed in addenda).

| Phase | Responsible implementer | Required approver (declares phase complete) | Verifying tool / report | Fallback if verifier unavailable |
|---|---|---|---|---|
| 0 | @claude + @jiazhenz026 | @jiazhenz026 | `$scieasy-adr-auditor` (contradiction audit) | Manual human review of ADR cascade |
| 1 | @claude (parallel via agent-manager) + @jiazhenz026 | @jiazhenz026 | First full audit report at `docs/audit/reports/<sha>/full.json` | Reduced-scope sub-track sign-off |
| 1.5 | n/a (decision checkpoint) | Project owner or Tier-2 maintainer | Baseline audit report | None — Phase 2 flip blocks indefinitely until approver records decision in tracking issue. Phase 1.5 is a HARD checkpoint; there is no 7-day silence default. |
| 2 | @jiazhenz026 (CI flip is a config change) | @jiazhenz026 | CI dashboard (all required checks failing as expected on existing violations) | n/a (CI flip is atomic) |
| 3 | @claude (parallel agent-manager) + Tier-1/2 humans | @jiazhenz026 | Full audit returns 0 errors | n/a (block Phase 4) |
| 4 | @claude + @jiazhenz026 | Project owner (per §26.6) | Post-Phase-4 revalidation artifact (§28.3) | Stay in transitional mode (§26.6 failure path) |
| 5 | (steady-state ops) | n/a (continuous) | Weekly audit cron + override-log monthly review | n/a |

`agent-manager` skill is invoked for any Phase 1 or Phase 3 sub-track
that benefits from parallel agent dispatch. Tracking is via
`docs/planning/phase-N-checklist.md` per the ADR-035/036 precedent.

### 26.1 Phase 0 — Process gates (1–3 days)

**Goal**: Establish the framework before any tooling work.

| Deliverable | Owner | Exit condition |
|---|---|---|
| ADR-042 (this document) | @claude + @jiazhenz026 | Status = Accepted |
| Umbrella tracking issue (closes_issues + tracking_issue) | @jiazhenz026 | Issue opened, ADR-042 frontmatter populated |
| Spec via SpecKit (per-tool specs, per-skill specs) | @claude + @jiazhenz026 | All specs in `docs/specs/` with frontmatter |
| Feature freeze announcement | @jiazhenz026 | Banner appended to CLAUDE.md / AGENTS.md |
| Pre-implementation contradiction audit (§28.1) | `$scieasy-adr-auditor` | 0 critical findings |

**Phase 0 ends when**: ADR-042 is Accepted and contradiction audit passes.

**Feature freeze policy** (audit P1.4 fix): the freeze is in effect from
Phase 0 acceptance through Phase 4 close (≈ Phase 3 sprint duration).

| Activity | Allowed during freeze? |
|---|---|
| Cleanup-track PRs (Phase 3 debt resolution) | ✅ Allowed |
| Bug fixes (regression on shipped behavior) | ✅ Allowed |
| Hotfix mode (CLAUDE.md §11.5) | ✅ Allowed |
| CI / build-system unblockers | ✅ Allowed |
| Security fixes (CVE response, dependency patches) | ✅ Allowed |
| ADR / spec / doc errata under §27.4 errata-only window | ✅ Allowed |
| Dependency upgrades (non-security, minor) | ⚠️ Tier-2 approval required |
| New user-visible features | ❌ Blocked |
| New governance scope (new ADRs unrelated to cascade) | ❌ Blocked |
| Refactors not driven by Phase 3 cleanup | ❌ Blocked |
| Performance optimization without correctness motive | ❌ Blocked |

Exception path: an issue labeled `freeze-exception` with explicit Tier-2
sign-off may permit otherwise-blocked work. Logged in
`docs/audit/freeze-exceptions.log`.

### 26.2 Phase 1 — Tooling scaffold (report-only)

**Goal**: Build all tooling. Run in report-only mode (no CI gates flip yet).

**Sequencing & parallelism** (audit P0.2 phase + Q5 max-6-agent
parallelization): Phase 1 is split into 8 sub-phases organized as a
dependency DAG that allows up to 6 concurrent agents in the middle wave.
Critical path: 1A → wave-2 (1B/1C/1D/1F/1G/1H parallel) → 1E.

```
                                        Phase 1.5 baseline review
                                                 ▲
                                                 │
                                                 1E
                                                 ▲
        ┌────────────┬───────────┬───────────┬───┴───────┬───────────┐
        │            │           │           │           │           │
       1B           1C          1D          1F          1G          1H
       (audit)    (ident)     (docs)      (test-q)   (ratchet)    (skills)
        ▲            ▲           ▲           ▲           ▲           ▲
        │            │           │           │           │           │
        └────────────┴───────────┴───────────┴───────────┴───────────┘
                                │
                               1A (schemas — foundation, blocks all)
```

Estimated duration: ~4 weeks with max-6-agent parallel (1A: ~1 wk;
wave-2: ~2 wk; 1E: ~1 wk). Single-agent sequential estimate: ~6-8 wk.

| Sub-phase | Concurrency | Deliverables | Depends on | Acceptance |
|---|---|---|---|---|
| **1A — Schemas** | 1 agent (foundation) | All pydantic schemas: `src/scieasy/qa/schemas/{frontmatter,maintainers,report,facts,identity,docs}.py`; `Amendment` model (§5.2); ADR/spec frontmatter validators | — | All schemas import; existing ADR/spec frontmatter validates against schema; `model_json_schema()` exports |
| **1B — Audit tools** | 1 agent | `doc_drift`, `frontmatter_lint`, `fact_drift`, `closure`, `trailer_lint`, `committer_enforce`, `full_audit`, `amendment_lint` (ADR-042-owned); `auto_generated_lint`, `doc_length_lint` (ADR-044-owned per its §15) | 1A | First baseline audit report at `docs/audit/reports/<sha>/full.json`; tool self-test artifacts (ADR-042 §2.4) all green |
| **1C — Ownership/identity** | 1 agent | `MAINTAINERS` file (initial coverage), `docs/identity/humans.yml`, `.governance-paths.yaml`, generated `.github/CODEOWNERS` | 1A | Bidirectional closure passes (or fails with documented gaps); identity registry validates |
| **1D — Docs build + generators** | 1 agent | Sphinx config (`docs/sphinx/conf.py`), `pyproject.toml` deps for §10.1 stack, custom directives (`scieasy_block_catalog`, `scieasy_runner_catalog`, `scieasy_ai_block_catalog`), 5 generators (`llms_txt`, `entry_point_catalog`, `cli_reference`, `openapi_reference`, `schema_reference`), `consolidate_cascade.py`, doc-set directory skeletons (~40 stub files per ADR-044 §6-9), `scripts/translate_docs.py`, translation workflow | 1A | `sphinx-build -W --keep-going` passes on minimal scaffold; one block doc auto-generated end-to-end as PoC |
| **1E — Governance checks (report-only)** | 1 agent | `governance_mod_guard.py` (local), `governance_mod_pr_check.py` (CI), `monotonic_check.py`, `honeypot_check.py`, `weakened_ci_check.py`, governance-modification workflow | 1A + 1C | All run in report-only on current main; honeypot canaries seeded |
| **1F — Test-quality tooling (report-only)** | 1 agent | `test_quality` AST lint, `test_first_check`, mutmut integration (Linux-only), hypothesis integration, `test-author` skill | 1A | Weekly cron report shows current mutation score distribution |
| **1G — Ratchet wrapper + SARIF (Q1)** | 1 agent | `.workflow/ci/ratchet.py`, SARIF converters/adapters for ruff/mypy/bandit/pyright, GitHub Code Scanning upload integration, `docs/audit/baselines/<tool>.json` seed files, `ci-implementability.json` Phase-1-end artifact | 1A + 1B | Ratchet self-test passes; SARIF uploaded; ci-implementability artifact authoritatively answers Phase-2-flip readiness |
| **1H — Workflow v2 + AGENTS.md hierarchy + skills** | 1 agent | `.workflow/schema-v2.yaml`, gate.py v2 (shadow mode against v1), AGENTS.md root + per-subtree files, CLAUDE.md/CURSOR.md/etc. symlinks, all required skills (P0+P1 from §17.1) installed cross-runtime, `scripts/committer.py`, `scripts/audit/extract_*.py` fact extractors, fact registry initial generation | 1A | v2 gates run shadow against v1 events without intervention; skills installed in 5 runtimes; AGENTS.md ≤200 lines |

**Wave-2 max concurrency = 6**: 1B + 1C + 1D + 1F + 1G + 1H all
parallelizable after 1A. Dispatched via `agent-manager` skill with
tracking checklist at `docs/planning/phase-1-checklist.md` (per
ADR-035/036 precedent). 1E blocks until 1C completes.

**Report-only mode**: tools produce findings; CI logs them; no merge
blocking until Phase 2.

**Phase 1 ends when**: all 8 sub-phases verified AND
`ci-implementability.json` artifact produced (per §4.3 implementability
gate) AND first full audit report at `docs/audit/reports/<phase-1-end-sha>/full.json`
produced and reviewed by project owner.

### 26.3 Phase 1.5 — Baseline review gate (decision checkpoint)

Phase 1.5 is a governed decision point, not "halt and discuss" prose
(audit P1.3 fix).

| Element | Value |
|---|---|
| Required artifact | Baseline full-audit report at `docs/audit/reports/<phase-1-end-sha>/full.json` |
| Required approver | Project owner or Tier-2 maintainer (per §25.4 tier matrix) |
| Allowed outcomes | (a) Proceed to Phase 2 unchanged; (b) Split Phase 1 into sub-phases via addendum; (c) Adopt temporary changed-files-only enforcement (Q1 option in audit P0.3) via addendum; (d) Revisit zero-tolerance posture (§4.3) via addendum |
| Forbidden | Any change to §4.3 zero-tolerance policy WITHOUT publishing an addendum that documents the change |
| Resume condition | Approver records decision in tracking issue + writes brief decision-log entry in `docs/audit/phase-1-5-decisions.log` |
| Default if no decision | None — Phase 2 flip is blocked indefinitely until the decision is recorded. This is a hard checkpoint, not a time-bomb (audit fix I8: removes the conflicting "auto-proceed after 7 days" fallback). |
| Threshold | If baseline > 5,000 critical errors, outcome (b), (c), or (d) is strongly recommended |

### 26.4 Phase 2 — CI flip via ratchet wrapper (half a day)

Toggle every tool from report-only to enforced-via-ratchet (NOT plain
fail-on-error). CI visibly shows full-repo violation count (the "red"
signal stays); ratchet wrapper translates count behavior into Checks API
conclusion:

- `conclusion=success`: zero findings
- `conclusion=neutral`: count ≤ baseline AND no new-file regressions
  (cleanup PR; mergeable per §4.3 GitHub branch-protection contract)
- `conclusion=failure`: count > baseline OR previously-clean file regresses
  (mergeable BLOCKED; this is the actual hard gate)

Feature freeze remains active. The dedicated cleanup sprint (Phase 3)
begins immediately.

**Pre-flip gate (§4.3 implementability check)**: Phase 2 flip is permitted
ONLY when the Phase 1 CI-implementability artifact at
`docs/audit/reports/<phase-1-end-sha>/ci-implementability.json` confirms:
- All 20 §21.1 tools dry-run successfully against current repo state
- Per-finding tracking emits stable IDs (verified for ruff, mypy, pyright,
  zizmor; community SARIF adapters in place for the rest)
- `ratchet.py` wrapper passes its own self-test (it can correctly classify
  curr vs prev counts and emit the right Checks API conclusion)
- All explicit tool-flag pinning (mypy `--soft-error-limit=-1`, zizmor
  `--format=sarif`, etc.) is in CI YAML

If verification fails, §26.3 Phase 1.5 decision checkpoint records a
fallback: changed-files-only enforcement (audit P0.3 option a) is the
documented fallback path. The zero-tolerance design intent (§4.3) is
preserved either way; only the wrapper implementation effort shifts.

**Baseline storage**: `docs/audit/baselines/<tool>.json` — committed file
per tool, updated by the wrapper on every successful main-branch merge.
Each baseline file is itself a governance file: ADR-043 §3.2
`.governance-paths.yaml` lists `docs/audit/baselines/**` (added there per
ADR-043's `amends` entry targeting ADR-042 §26.4). Each baseline file is
`agent_editable: false` — only the ratchet wrapper writes to it.
(Audit fix F12: rewrote "this addendum" — ADR-042 is the base ADR, not an
addendum; the ADR-043 ownership of `.governance-paths.yaml` is made
explicit instead.)

### 26.5 Phase 3 — Debt cleanup sprint (4–8 weeks estimated, no hard deadline)

**Goal**: Resolve every existing violation. Parallelized via agent-manager
skill + checklist convention.

Sub-tracks (parallelizable):

- ADR.md monolith → per-ADR files
- Frontmatter backfill on all ADRs/specs
- b-class drift resolution (code wins per §4.2)
- c-class drift cleanup
- d-class docstring + ADR-coverage backfill
- English normalization + first translation pass
- MAINTAINERS bidirectional closure achievement
- Public-API `__all__` declarations

**Phase 3 ends when**: full audit returns 0 errors.

### 26.6 Phase 4 — Truth-shift PR (governance decision)

Phase 4 is a governance decision, not a mechanical PR (audit P1.6 fix).

| Element | Value |
|---|---|
| Required inputs | (1) Full audit returns 0 errors; (2) implementation tracker (ADR-043 §2.1) all entries `verified`; (3) accepted addenda reconciled (each Addendum's amendments fully implemented); (4) generated templates (`docs/adr/_template/ADR-template.md`, `docs/spec/_template/SPEC-template.md`) committed |
| Required approver | Project owner OR Tier-2 maintainer (per §25.4) |
| Allowed failure paths | (a) Remain in transitional mode (publish addendum extending exemption); (b) Roll back partial truth-shift (revert PR, return to transitional) |
| Output | Single PR + annotated git tag `phase-4-complete` on merge commit |

PR body:

- Removes any remaining `Code-as-truth-during-cleanup` transitional language.
- Sets §8.2 (status-driven arbitration) as the permanent rule.
- Includes the post-Phase-4 revalidation artifact (§28.3).
- Tags `phase-4-complete` (annotated git tag) on the merge commit.

**Phase 4 ends when**: PR merged AND revalidation artifact attached AND
the `phase-4-complete` git tag is created. Per §28.3, no `phase-4-complete`
tag may be created until the revalidation artifact passes; a tag created
before the artifact lands is automatically reverted by CI (`tag-policy.yml`).

### 26.7 Phase 5 — Permanent enforcement

Steady state:

- Weekly audit cron (§24.1).
- All new ADRs/specs use the frozen template (§28.4).
- Skills enforcement via `doc-drift-guard` skill in every agent runtime.
- Override patterns reviewed monthly (§25.6).

---

## 27. Exemptions & Carve-outs

### 27.1 Path exemptions

| Path | Exempt from |
|---|---|
| `*_pb2.py` (generated protobuf) | Lint, docstring coverage, ADR coverage |
| `frontend/dist/**` | All |
| `frontend/node_modules/**` | All |
| `_skills/` (data) | All |
| `agent_provisioning/templates/` | All (template files) |
| `scripts/` (excluding `scripts/audit/` and `scripts/committer.py`, `scripts/translate_docs.py`) | Docstring coverage, ADR coverage |
| `tests/**` | Docstring coverage; all else applies |

### 27.2 Inline exemptions

`# noqa: <rule-id>(#<issue>)` allowed only with:

- A specific rule ID (not a blanket `noqa`).
- A tracking issue number.

CI scans for blanket `noqa` and rejects.

### 27.3 Hotfix mode

CLAUDE.md §11.5 hotfix mode lifts the 6-gate workflow only. It does NOT
lift:

- doc_drift / fact_drift / closure checks.
- Trailer requirements.
- Frontmatter schema validation.
- RBP requirement.

After the hotfix round ends, all gates run retroactively.

### 27.4 ADR-042 self-exemption window (extends to addendums)

ADR-042's own first PR (Phase 0 deliverable) is exempt from doc_drift,
fact_drift, and closure checks for the duration of that single PR. Without
this exemption, the PR cannot land (the tooling does not yet exist).
Immediately after merge, the exemption expires and all checks apply.

The exemption explicitly extends to the first PR introducing any addendum
to ADR-042 (currently ADR-043, ADR-044, and any future Addendum C / D /
…), again for the duration of that single PR. Each addendum is treated as
a continuation of the ADR-042 bootstrap and inherits the same finite
exemption window. The exemption does NOT cover subsequent edits to those
addendums after they have been merged.

This sub-section is co-referenced by §3.0 (transitional prologue),
ADR-043 §1.4 (transitional note), and ADR-044's transitional note prose,
so all four citations agree on the scope.

**Pre-acceptance vs post-acceptance errata rules** (audit P1.7 fix):

| State | Rule that applies |
|---|---|
| ADR-042/043/044 in `Draft` or `Proposed` (pre-acceptance) | Corrections governed by current repository gates (existing 6-stage workflow, CLAUDE.md §11.5 hotfix mode, conventional commits) + human review. ADR-043 §3 governance-modification rules do NOT yet apply — they are themselves part of the Draft being corrected. |
| ADR-042/043/044 `Accepted` (post-acceptance) | ADR-043 §3 self-modification rules apply in full (CODEOWNERS + governance_mod_guard + monotonic_check + contradiction_audit + honeypot + log entry; or §3.7 errata-only fast lane for ≤ 20-line typo-only diffs). |
| Transition moment (during the Accepted-status PR itself) | §27.4 self-exemption window covers this single PR. |

This resolves the bootstrap chicken-and-egg: pre-acceptance corrections do
not invoke un-implemented governance machinery.

### 27.5 Amendment records (replaces "addendum wins")

Phase-plan audit P0.5 fix. Replaces the prior informal rule "where main
ADR and addendum collide, the addendum wins" with explicit, machine-
readable amendment declarations.

**Rule**: every addendum that modifies a parent ADR's semantics MUST list
each modification in its frontmatter `amends:` field. The `kind` enum
(see §5.2 `AmendmentKind`) determines precedence:

| `kind` | Effect on target |
|---|---|
| `extend` | Target prose still applies; addendum adds to it. No precedence conflict. |
| `replace` | Addendum prose supersedes target entirely. Reader uses addendum. |
| `constrain` | Target still applies; addendum tightens (additional restriction). Both apply (intersection). |
| `clarify` | Editorial; no semantic change. Addendum is the canonical reading. |

**Format** (frontmatter):

```yaml
amends:
  - target: "ADR-042 §17 Required Skills"
    kind: extend
    summary: "Adds 4 new required skills (test-author, codemod-with-adr, ...)"
  - target: "ADR-042 §27.4 Self-exemption window"
    kind: constrain
    summary: "Restricts exemption to single first-PR per addendum"
```

**`target` resolution algorithm** (audit fix F16 + meta-finding):

The `target` string MUST match one of these three resolution levels.
`amendment_lint.py` (below) resolves in this order:

1. **Section-heading match**: prefix `ADR-NNN §X` or `ADR-NNN §X.Y` where
   `§X[.Y]` is a real Markdown heading in ADR-NNN. Trailing text after
   the section number is descriptive only and is NOT matched.
   Example: `target: "ADR-042 §17 Required Skills"` → matches §17 of
   ADR-042; the "Required Skills" suffix is ignored by the lint.
2. **Section + sub-element match**: prefix `ADR-NNN §X[.Y]` followed by
   ` (component <X>)` where `<X>` is a specific cell, table-row, or
   bullet identifier. Use this when the amendment touches a single
   element within a section (e.g., one row of a 20-row table).
   Example: `target: "ADR-042 §21.1 (component: furo theme row)"`.
3. **Whole-ADR match**: `target: "ADR-NNN"` with no `§X` — amendment
   applies cross-section. Rare; requires `kind: extend` or `clarify`.

Sub-component matches finer than a single bullet/row are not resolvable;
the amendment must be rewritten at the bullet/row level, OR the parent
ADR must be edited to split the cell into a discrete sub-element.

**Tooling** (Phase 1 deliverable):

- `scripts/audit/amendment_lint.py` validates: each `target` resolves
  per the algorithm above; each addendum's `amends` is non-empty if the
  addendum body modifies any parent ADR section; no two amendments
  target the same section with conflicting `replace` declarations.
- `docs/adr/_consolidated/cascade-current.md` is auto-generated by
  `scripts/audit/consolidate_cascade.py`: walks `amends` field of every
  addendum, applies amendments to base ADR-042 text (per `kind` semantics),
  produces single-file consolidated view. Generation: AUTO; hand-edits
  rejected. Updated on every merge to main that touches `docs/adr/**`.

**Migration**: ADR-043 and ADR-044 retroactively gain `amends:` fields in
this revision (see their frontmatters). Future addendums (C, D, …) MUST
populate `amends` from day one. The "addendum wins" prose in ADR-043 §1.2
and ADR-044 §1.3 is replaced with reference to this §27.5 rule.

---

## 28. ADR-042 Self-Compliance + Self-Iteration

### 28.0 Algorithm pseudocode placement

Per §23.6, the full `doc_drift.py` algorithm pseudocode lives in a companion
file `docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` (with
`agent_editable: false`). The main ADR includes only a stub. This keeps
the main ADR's fenced code blocks executable under `pytest-examples`.

### 28.1 Pre-implementation contradiction audit

While ADR-042 is in `Draft` or `Proposed` status and the tooling is not yet
implemented, a dedicated audit agent (`$scieasy-adr-auditor`) scans this
ADR for internal contradictions. Scope:

| Check | Example |
|---|---|
| supersedes cycles | A supersedes B; B supersedes A |
| `agent_editable` contradictions | ADR claims `agent_editable: false` but §X permits agent edits to a sub-section |
| `governs` vs exclusions conflicts | `governs.modules: [X]` and `exclusions: [X.sub]` where X.sub is not under X |
| schema vs validator mismatches | frontmatter declares `tests` required; pydantic schema marks it default-empty |
| workflow stage cycles | stage A depends on B which depends on A |
| internally contradicting rule clauses | §13 "trailer required" vs §25 "Tier 1 exempt" — confirm Tier 1 definition is consistent |
| references to undefined sections | "per §99 …" where §99 does not exist |
| tool-list internal contradictions | §20 lists tool X; §20 elsewhere says "use Y instead of X" |

Findings are written to `docs/audit/adr-self-audit/<adr>-<sha>.json`. CI
blocks Phase 1 progress until 0 critical findings remain.

The contradiction audit is a standing policy: every ADR drafted by an
agent runs through `$scieasy-adr-auditor` before promotion to `Proposed`.

### 28.2 Continuous self-validation

Any commit modifying ADR-042 OR modifying the §21 tool stack triggers a
CI job:

```bash
python -m scieasy.qa.audit.full_audit --target docs/adr/ADR-042.md --self-check
```

Required 0 errors to merge.

### 28.3 Post-Phase-4 mandatory revalidation

The Phase 4 PR (§26.6) MUST include the artifact:

```
docs/audit/reports/<phase-4-sha>/adr-042-self-check.json
```

This artifact proves ADR-042 passes every rule it defines, against the
final implementation of the tooling. If the artifact reports any error:

- **Bug in ADR-042**: write addendum ADR-042-A.
- **Bug in tooling**: fix tooling.
- **Mutual mismatch**: revisit the design; do not merge Phase 4 until
  resolved.

No `Phase 4 complete` tag may be created until the artifact is attached
and passes.

### 28.4 Template freeze

After Phase 4 revalidation passes:

1. `docs/adr/_template/ADR-template.md` is generated from ADR-042 by
   stripping field values and leaving structure.
2. `docs/spec/_template/SPEC-template.md` is generated analogously.
3. Both templates are committed and marked `agent_editable: false`.
4. From this point, all new ADRs/specs MUST be authored by copying the
   template. CI `template-derivation-check` verifies new ADRs follow the
   template structure.

### 28.5 Meta-compliance checklist (M1–M11)

| ID | Requirement | Status |
|---|---|---|
| M1 | ADR-042 has complete frontmatter (all required fields present, all validators pass) | ✓ Met |
| M2 | ADR-042's commit carries `Assisted-by: Claude:claude-opus-4-7` trailer | To be verified at commit time |
| M3 | ADR-042 PR includes Real-Behavior-Proof of introduced tooling | To be attached at Phase 1 PR time |
| M4 | All fenced code blocks in ADR-042 main body are executable (pytest-examples) | To be verified after Phase 1 schema creation (pseudocode moved to §28.0 companion file; python blocks importing `scieasy.qa.schemas.*` covered by §3.0 transitional exemption) |
| M5 | All `:py:class:` references in ADR-042 resolve under Sphinx nitpicky | To be verified after Phase 1 schema creation |
| M6 | `docs/zh-CN/adr/ADR-042.md` exists and source_sha matches | To be generated by translator first run |
| M7 | All ADR-042 governs entries appear in MAINTAINERS | To be created in Phase 0 |
| M8 | ADR-042 serves as template for all subsequent ADRs | §28.4 implements this |
| M9 | All numeric/list facts in ADR-042 use `{{ facts.X }}` substitution (no hardcoded values) | Transitional exemption per §3.0 prologue; to be fully met after Phase 1 fact registry operational |
| M10 | Pre-implementation contradiction audit passes (§28.1) | To be run by `$scieasy-adr-auditor` |
| M11 | Post-Phase-4 revalidation passes (§28.3) | To be run at Phase 4 close |

---

## 29. Consequences

### 29.1 Positive

- **Drift is mechanically detectable.** Every PR shows its drift impact.
- **AI provenance is queryable.** `git log --grep="^Assisted-by"` enumerates AI contributions.
- **ADRs become operational, not aspirational.** `governs` makes scope concrete.
- **One source of truth per fact.** No more "the README says 6 but the code does 7."
- **Cross-runtime parity.** Agent-equality ensures the project is not Claude-only or Codex-only.
- **Active doc fixing.** docs-agent reduces manual maintenance burden.
- **Audit trail.** Override patterns surface bad incentives early.
- **Template-driven uniformity.** New ADRs cannot be ad-hoc.

### 29.2 Negative

- **Phase 3 debt-cleanup duration unknown.** Could exceed 8 weeks.
- **Tooling complexity.** ~20 tools, ~15 custom scripts, ~5 CI workflows. Substantial maintenance.
- **Friction increase.** Every PR now does more work; even small changes pass more checks.
- **Skill installation burden.** Cross-runtime install is non-trivial; provisioning system must work everywhere.
- **Translation API cost.** DeepL pro tier billable; manual provider for development required.
- **Sphinx build time.** Full docs build with autoapi + linkcheck adds minutes to CI.
- **Pydantic schema migration burden.** Schema changes ripple to every ADR/spec; addendum protocol must be smooth.

### 29.3 Alternatives considered

| Alternative | Reason rejected |
|---|---|
| Baseline + ratchet (tolerate existing violations) | §4.3: agents learn baselines as ceilings |
| MkDocs instead of Sphinx | Sphinx's nitpicky cross-ref enforcement and sphinx-needs are decisive for ADR-traceability |
| No required skill list (let agents pick) | Variance in agent capability causes inconsistent output |
| Agent translation instead of API | Hallucination risk; deterministic API is auditable |
| Single AGENTS.md (no per-subtree) | Scope creep; per-subtree allows tighter local rules |
| Forbid AI commits entirely (NetBSD model) | Discards the productivity gain; current project IS AI-driven |
| Replace pydantic with jsonschema | pydantic already a project dep; native Python integration; better validators |
| 9-stage workflow v2 | Slightly heavy per project owner feedback; trimmed to 7 |
| 6-stage workflow (keep current) | Insufficient guidance; agents miss artifacts |

### 29.4 Open questions (reserved for Appendix D)

Items the project owner has flagged for later discussion. See Appendix D.

---

## Appendix A: Migration Scripts Specification

### A.1 `ADR.md` monolith split

The existing `docs/adr/ADR.md` contains ADRs 001–030 as inline sections.
Migration:

1. `scripts/migrate/split_adr_md.py` parses the monolith.
2. Per ADR, extracts the section content into `docs/adr/ADR-NNN.md`.
3. Generates initial frontmatter from inline metadata (bold-prose fields).
4. Marks `governs.modules: []` etc. as `null` with `# TODO(#<issue>): populate
   governs` markers for human/agent fill-in.

### A.2 Frontmatter backfill

`scripts/migrate/backfill_frontmatter.py`:

1. For each ADR/spec lacking frontmatter, inserts a stub based on inline
   metadata heuristics.
2. Marks fields the heuristic cannot infer as `# TODO(#<issue>): backfill X`.
3. Runs the contradiction audit (§28.1) on the backfilled file.

### A.3 MAINTAINERS bootstrap

`scripts/migrate/bootstrap_maintainers.py`:

1. Reads all ADRs' `governs.modules + governs.files`.
2. Generates MAINTAINERS entries covering the union.
3. Sets `humans: ["@jiazhenz026"]` and `agents_allowed: [all]` by default.
4. Human reviews and refines.

---

## Appendix B: Decision Log

Numbered list of every design decision made during ADR-042 authoring,
preserved for future "why did we pick X over Y" archaeology.

| # | Decision | Date | Decided by | Rationale |
|---|---|---|---|---|
| 1 | Full-repo scope; no developing-surface carve-out | 2026-05-17 | @jiazhenz026 | Avoid two-tier standard drift |
| 2 | Zero tolerance for existing violations | 2026-05-17 | @jiazhenz026 | §4.3 |
| 3 | pydantic v2 as the schema engine | 2026-05-17 | @jiazhenz026 + @claude | Already a dep; multi-consumer JSON Schema export |
| 4 | Code-as-truth during cleanup; status-based after | 2026-05-17 | @jiazhenz026 | Deterministic tiebreaker for debt sprint |
| 5 | Force YAML frontmatter on ADRs/specs | 2026-05-17 | @jiazhenz026 | Machine parseability |
| 6 | b-class signature matching: all 4 attributes | 2026-05-17 | @jiazhenz026 | Maximum strictness |
| 7 | Public class needs ADR coverage; function needs only docstring | 2026-05-17 | @claude proposed | Tradeoff between strictness and maintainability |
| 8 | "public" defined via `__all__` (with fallback to `_` prefix) | 2026-05-17 | @jiazhenz026 | Encourages explicit export declarations |
| 9 | Agent-equality principle (no preferential implementation) | 2026-05-17 | @jiazhenz026 | Prevents runtime divergence |
| 10 | docs-agent active fixer with path allowlist | 2026-05-17 | @jiazhenz026 | OpenClaw-proven pattern |
| 11 | English source + DeepL translator + zh-CN mirror | 2026-05-17 | @jiazhenz026 | Avoids agent translation hallucination |
| 12 | Workflow v2: 7 stages (trimmed from 9) | 2026-05-17 | @jiazhenz026 | "Slightly heavy" at 9 |
| 13 | Trivial fast-lane: 150 / 450 lines | 2026-05-17 | @jiazhenz026 | Calibrated to typical small-change scope |
| 14 | Fact Substitution Registry | 2026-05-17 | @jiazhenz026 | Catches `gate.py 6→9 but CLAUDE.md says 6` |
| 15 | Self-iteration mechanism (contradiction audit + post-Phase-4 revalidation) | 2026-05-17 | @jiazhenz026 | Prevent meta-drift |
| 16 | Human Developer Exemption Principle | 2026-05-17 | @jiazhenz026 | Prevent excessive friction for humans |

---

## Appendix C: Cross-references

| Source | Inspiration |
|---|---|
| §5 frontmatter schema | OpenClaw `skill-creator` SKILL.md frontmatter convention |
| §6 MAINTAINERS schema | Linux kernel `MAINTAINERS` file format |
| §10 Fact Substitution Registry | Sphinx substitutions + mkdocs-macros + the "gate.py drift" example raised by @jiazhenz026 |
| §12 AGENTS.md hierarchy | OpenClaw root AGENTS.md + per-subtree nesting |
| §13 git trailers | Linux kernel trailer conventions (Signed-off-by, Fixes:, Co-developed-by); kernel's Assisted-by: (merged 2025) |
| §14 Real-Behavior-Proof | OpenClaw CONTRIBUTING.md; Greg KH's "patches were wrong-but-pointed-at-real-bugs" experiment |
| §15 docs-agent | OpenClaw `.github/workflows/docs-agent.yml` + `.github/codex/prompts/docs-agent.md` |
| §16 committer.py | OpenClaw `scripts/committer` wrapper |
| §17 required skills | OpenClaw `skills/` directory inventory (skill-creator, coding-agent, gh-issues, session-logs, etc.) |
| §18 persona routing | OpenClaw `$persona` tokens in AGENTS.md ("Skills own workflows; root owns hard policy and routing") |
| §19 Workflow v2 | SciEasy current 6-gate workflow (CLAUDE.md Appendix A) + per-stage guidance pattern |
| §20 libCST codemods | Linux kernel Coccinelle semantic patches |
| §21 aggregator `check` job | pydantic CI pattern |
| §21 tool stack | pydantic (ruff D + S consolidation), OpenClaw (zizmor, actionlint, codespell) |
| §23 Sphinx + autoapi + nitpicky | pydantic `mkdocs strict: true` pattern; kernel `kernel-doc` Sphinx integration |
| §23 pytest-examples | pydantic doc-examples-as-tests pattern |
| §25 Human Exemption | (novel — no direct precedent in researched projects) |
| §28 self-iteration | (novel — no direct precedent) |

---

## Appendix D: Open Discussion Items (Reserved)

> **Status**: Reserved for additional decisions the project owner wishes to
> raise. Add items as `### D.N Topic` with description. Each item, once
> decided, is promoted to a numbered section in the main body and removed
> from this appendix. **Documentation convention (not schema-enforced —
> audit fix W8)**: ADR-042 frontmatter `agent_editable: false` applies at
> whole-document level (§5.4.1); per-section editability is enforced via
> human review per ADR-043 §3.3 governance_mod_guard CODEOWNERS gate, not
> by the pydantic schema. Only the project owner adds or removes items
> here in practice.

### D.1 [Reserved]

(To be filled.)

### D.2 [Reserved]

(To be filled.)

### D.3 [Reserved]

(To be filled.)

---

<!-- End of ADR-042. -->

---

## Amending Addenda

### ADR-043 — ADR-042 Addendum A: Implementation Monitoring, Rule-Modification Hard Blocks, Test Quality, AGENTS.md Layered Design, 2026 Convention Adoptions

_Status: Accepted_

**Amendments declared in frontmatter (§27.5):**

- **target**: `ADR-042 §17 Required Skills`
  - **kind**: `extend`
  - **summary**: Adds 1 new required skill: test-author (§4.4). The other three skills mentioned in §5.3 (codemod-with-adr, hallucination-guard, maintainers-reverse) are pre-existing P2 entries in ADR-042 §17.1; ADR-043 references them without changing their priority. Skill-kinds classification (procedural / tool-wrapping / bootstrap-meta) is introduced in §5.3.
- **target**: `ADR-042 §12 AGENTS.md / CLAUDE.md / Per-subtree Hierarchy`
  - **kind**: `extend`
  - **summary**: Adds 4 mechanism types (hook / path-rule / skill / always-loaded) and migration plan (§5)
- **target**: `ADR-042 §11 Bidirectional Closure`
  - **kind**: `extend`
  - **summary**: Adds tracker.yaml as third closure consumer (§2.6)
- **target**: `ADR-042 §27 Exemptions & Carve-outs`
  - **kind**: `extend`
  - **summary**: Adds §3 governance modification hard blocks (5 layers) + §3.7 errata-only fast lane
- **target**: `ADR-042 §14 Real-Behavior-Proof Gate`
  - **kind**: `extend`
  - **summary**: Adds §4 test quality enforcement (mutation testing + AST anti-patterns + test-first verification)
- **target**: `ADR-042 §22.1 Language policy`
  - **kind**: `extend`
  - **summary**: Adds §6.1 data classification + §6.2 assessment rubric + §6.3 three-tier path boundary AGENTS.md required sections
- **target**: `ADR-042 §28.5 Meta-compliance checklist`
  - **kind**: `extend`
  - **summary**: Adds M12-M15 (§8)
- **target**: `ADR-042 §26.4 Phase 2 — CI flip baseline storage paragraph`
  - **kind**: `extend`
  - **summary**: Marks ADR-043 §3.2 .governance-paths.yaml registry (which lists docs/audit/baselines/**) as the upstream owner of ratchet-baseline file governance — §26.4 prose links there for the actual path declaration. (Audit fix F11/F12 + iter-7 ITER-FRESH-004 corrected scope.)
- **target**: `ADR-042 §13.1 Trailer formats`
  - **kind**: `extend`
  - **summary**: Adds 5 new git trailers introduced by this addendum: Loosening-Approved (§3.4.2), Loosening-Reason (§3.4.2), Governance-Modification-Approved-By (§3.3), Errata-Only (§3.7), Backfill-Test (§4.3.2). All follow ADR-042 §13.2 agent-agnostic format. (Audit fix iter-7 ITER-FRESH-001.)

**Body of ADR-043:**

<!--
TRANSITIONAL NOTE: This addendum is paired with ADR-042 and shares its
transitional exemption window per ADR-042 §3.0. Hardcoded values appear
with TODO markers linking to the umbrella tracking issue; substitution via
the fact registry (ADR-042 §10) applies after Phase 1. All section
references to ADR-042 use post-cascade numbering (§5.7 SpecFrontmatter,
§10 Fact Substitution, §11 Bidirectional Closure, §12 AGENTS.md, …,
§29 Consequences) consistent with the ADR-042 audit fix pass completed
2026-05-17.
-->

# ADR-042 Addendum A: Implementation Monitoring, Rule-Modification Hard Blocks, Test Quality, AGENTS.md Layered Design, 2026 Convention Adoptions

## 1. Purpose & Relation to ADR-042

### 1.1 What this addendum adds

ADR-042 defines WHAT the QA regime is (schemas, drift classification, workflow, exemptions, phases). Three implementation-side concerns were deliberately deferred from the main ADR to keep it focused on the rule set:

1. **How do we monitor that ADR-042 itself doesn't drift during its multi-month implementation?** (§2)
2. **How do we hard-block AI agents from modifying the rules to bypass them?** (§3)
3. **How do we ensure tests are not "test theater" — meaningless tests written just to satisfy coverage?** (§4)

This addendum addresses those three concerns. It also incorporates two updates that emerged from research conducted after ADR-042 was drafted:

4. **Detailed CLAUDE.md / AGENTS.md mechanism design** based on Anthropic's official guidance (sub-200-line ceiling; hooks/path-scoped rules/skills as first-class rule carriers) and OpenClaw's "telegraph style; skills own workflows; root owns hard policy and routing" pattern (§5).
5. **Four 2026 industry-convention adoptions**: data classification section, assessment rubric section, three-tier path boundary, weakened-CI automatic block (§6).

### 1.2 Relation to ADR-042

This is an addendum, not a supersession. Per ADR-042 §27.5 (audit P0.5
fix), precedence is determined by the `amends:` field in this addendum's
frontmatter, NOT by a global "addendum wins" rule. Each amendment declares
its kind (`extend` / `replace` / `constrain` / `clarify`); precedence
follows that kind. All amendments in this addendum are `extend`-kind
(target prose still applies; this addendum adds to it). See frontmatter
`amends:` for the complete list.

### 1.3 Lifecycle coupling

This addendum is paired with ADR-042 and follows its status lifecycle in lockstep. ADR-042 promoting to `Proposed` or `Accepted` also promotes this addendum to the same status. Both are reviewed and decided together. After acceptance, future evolutions are either further addendums (B, C, …) or full supersession of both.

### 1.4 Out-of-scope

Items raised during the design discussion but **not** included in this addendum (deferred to future addendums or separate ADRs):

- Agent fingerprinting CI job (Gap 4 from 2026 research; deferred — requires its own discussion of false-positive tolerance and privacy implications).
- Prompt-injection sanitization in gate scripts (Gap 5; deferred — needs its own threat model).
- Network egress allowlist for agent workflows (Gap 7; deferred — infrastructure concern).
- New attack patterns documented in 2026 research (settings-file copy-and-redirect, emoji smuggling, multilingual prompt mixing, NeMo guard regressions) — defenses for these go in a future addendum or a dedicated security ADR.

These are tracked as known gaps in §11 below.

---

## 2. Implementation Monitoring

> ADR-042 is itself an artifact that must not drift between its specification
> and its implementation. This section defines the monitoring infrastructure
> that catches divergence as it happens, not at Phase 4 revalidation.

### 2.1 Implementation Tracker

A structured, pydantic-validated, machine-checkable tracker lives at
`docs/audit/adr-042-implementation-tracker.yaml`. Every section of ADR-042
that introduces code or files (§5, §6, §7, §7.5, §9, §10, §11, §12,
§13, §14, §15, §16, §17, §19, §20, §21, §22, §23, §24, §25, plus every
section in this addendum) has a tracker entry declaring:

- Which artifacts must exist (file paths, dotted-symbol paths).
- Which verification checks must pass.
- Which PR(s) implemented the section.
- Current status (`not_started | in_progress | implemented | verified`).
- Which skill or script verifies the section.

```yaml
# docs/audit/adr-042-implementation-tracker.yaml — sample entry
adr: 42
sections:
  - section: "§5 Frontmatter Schema"
    requires_artifacts:
      files: ["src/scieasy/qa/schemas/frontmatter.py"]
      symbols:
        - "scieasy.qa.schemas.frontmatter.ADRFrontmatter"
        - "scieasy.qa.schemas.frontmatter.SpecFrontmatter"
        - "scieasy.qa.schemas.frontmatter.Governs"
        - "scieasy.qa.schemas.frontmatter.Translation"
        - "scieasy.qa.schemas.frontmatter.Status"
        - "scieasy.qa.schemas.frontmatter.AgentEditable"
        - "scieasy.qa.schemas.frontmatter.Phase"
      tests: ["tests/qa/test_schemas_frontmatter.py"]
    verification_checks:
      - id: "schema-importable"
        description: "All declared symbols import without error"
      - id: "validators-test-passing"
        description: "Test suite for §5.4 validators passes"
      - id: "json-schema-export"
        description: "Each model's .model_json_schema() produces valid JSON Schema Draft 2020-12"
    status: not_started
    implemented_in_pr: null
    verified_at: null
    verifier_skill: scieasy-skill-creator
    verifier_command: "python -m scieasy.qa.tracker.adr_implementation_check --section '§5'"
```

### 2.2 Tracker pydantic schema

```python
# src/scieasy/qa/schemas/tracker.py
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from .frontmatter import ADRRef, RepoRelativePath, FunctionOrClassPath


class SectionStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"


class RequiredArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: list[RepoRelativePath] = Field(default_factory=list)
    symbols: list[FunctionOrClassPath] = Field(default_factory=list)
    tests: list[RepoRelativePath] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str


class TrackerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: str
    requires_artifacts: RequiredArtifacts
    verification_checks: list[VerificationCheck]
    status: SectionStatus
    implemented_in_pr: int | None = None
    verified_at: datetime | None = None
    verifier_skill: str | None = None
    verifier_command: str


class ImplementationTracker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adr: ADRRef
    schema_version: int = 1
    sections: list[TrackerEntry]
```

### 2.3 Tracker state-transition rules

Status may only advance, never regress, except through an addendum:

```
not_started ──► in_progress ──► implemented ──► verified
                                      │
                                      └── must include implemented_in_pr
```

`scripts/audit/adr_implementation_check.py` enforces:

- Status advancement is monotonic.
- Transition to `in_progress` requires at least one open PR touching declared artifacts.
- Transition to `implemented` requires all declared artifacts to exist (files present, symbols importable).
- Transition to `verified` requires all `verification_checks` to pass.
- Every PR that touches an artifact declared by some section MUST update that section's tracker entry in the same PR (CI gate).

### 2.4 Meta-test discipline — every QA tool eats its own dogfood

Every QA tool introduced by ADR-042 MUST, as part of its own implementation
PR, demonstrate that it runs correctly **on ADR-042 itself**.

| Tool PR | Mandatory artifact |
|---|---|
| `doc_drift.py` introduction | `docs/audit/tool-self-test/doc_drift-on-adr-042.json` — diff against checked-in expected output |
| `frontmatter_lint.py` introduction | `docs/audit/tool-self-test/frontmatter_lint-on-adr-042.json` — must pass |
| `fact_drift.py` introduction | `docs/audit/tool-self-test/fact_drift-on-adr-042.json` |
| `closure.py` introduction | `docs/audit/tool-self-test/closure-on-adr-042.json` |
| `pytest-examples` integration | `docs/audit/tool-self-test/pytest_examples-on-adr-042.json` |
| `griffe` API-surface diff | `docs/audit/tool-self-test/griffe-on-adr-042.json` |
| `interrogate` docstring coverage | `docs/audit/tool-self-test/interrogate-on-adr-042.json` |
| `pydoclint` signature↔docstring | `docs/audit/tool-self-test/pydoclint-on-adr-042.json` |
| `monotonic_check.py` | `docs/audit/tool-self-test/monotonic-on-adr-042.json` |
| `test_quality.py` (this addendum) | `docs/audit/tool-self-test/test_quality-on-adr-042.json` |

Without this self-test artifact, the tool's introduction PR cannot merge.
The expected-output JSON for each tool is committed once and then updated
only when ADR-042 itself is intentionally revised.

### 2.5 Phase Gate Validator

Phase `N+1` MUST NOT start until Phase `N` is verified complete. The
validator script:

```python
# scripts/audit/phase_gate.py — algorithm overview
def check_phase_transition(from_phase: Phase, to_phase: Phase) -> PhaseGateResult:
    """Validate readiness to advance phases.

    Returns blocking failures if:
      1. Any §N tracker entry assigned to from_phase is not status=verified
      2. Any tool self-test artifact (§2.4) is missing or stale
      3. Any §N has implementation_in_pr referencing an unmerged PR
      4. The implementation tracker's pydantic validation fails
    """
```

```bash
$ python scripts/audit/phase_gate.py --check phase-1->phase-2
PHASE phase-1 -> phase-2 readiness check (target: ADR-042 + ADR-043):
  ✓ All §5–7.5 schemas implemented and verified (15/15)
  ✓ All §9, §10 audit tools implemented (5/5)
  ✓ All §2 tracker tools implemented (3/3)
  ✓ All §3 governance tools implemented (4/4)
  ✓ All §4 test-quality tools implemented (3/3)
  ✗ ADR-042 §17 required skills installed cross-runtime: 9/10 (missing 'mantis-proof' on Cursor)
  ✗ ADR-042 §12 AGENTS.md per-subtree files: 5/7 (missing engine/, ai/)
  ✗ Tool self-test artifacts: 8/10 (missing pytest-examples-on-adr-042.json, griffe-on-adr-042.json)

PHASE phase-2 BLOCKED. Resolve 3 issues before flipping CI to fail-on-error.
```

CLI accepts the `Phase` enum string values (`phase-0`, `phase-1`,
`phase-1-5`, `phase-2`, …, `phase-5`, `complete`) per ADR-042 §5.2; prose
in §26 uses 'Phase 1.5' for readability.

Tier-2 humans **cannot override** the phase gate. Override would require
publishing an addendum that documents the exception, which itself goes
through the 6-gate workflow.

### 2.6 Bidirectional ADR↔implementation monitoring

When an addendum is published (such as this one), `scripts/audit/addendum_propagate.py`:

1. Parses the addendum's `governs.contracts`, `governs.files`, `tests`.
2. Inserts corresponding tracker entries with status `not_started`.
3. Computes a grace period (default 14 days, configurable per addendum).
4. After grace period, any tracker entry still at `not_started` becomes a
   blocking CI error on every PR until resolved.

This prevents the failure mode "we added a new rule and forgot to implement it."

The reverse direction (code references something the tracker doesn't know
about) is caught by the bidirectional closure check (ADR-042 §11) extended
to also consume the tracker file.

### 2.7 Tool inventory (new for §2)

| Tool | Purpose | Trigger |
|---|---|---|
| `scripts/audit/adr_implementation_check.py` | Validate tracker.yaml ↔ code state | Pre-commit + CI |
| `scripts/audit/phase_gate.py` | Verify phase transition readiness | Manual + before phase flip |
| `scripts/audit/tool_self_test_runner.py` | Run all tools against ADR-042; diff vs expected.json | Per-tool-PR + nightly |
| `scripts/audit/governance_drift.py` | Detect ADR-claimed-value vs actual-config divergence (e.g., "ADR says 90% coverage but pyproject.toml says 70%") | Weekly cron |
| `scripts/audit/addendum_propagate.py` | Insert tracker entries when an addendum is added | Pre-commit on `docs/adr/ADR-*.md` change |

CI workflow `.github/workflows/adr-042-conformance.yml` orchestrates the
weekly run of all of the above.

---

## 3. Rule-Modification Hard Blocks

> AI agents under task-completion pressure will attempt to modify rules
> rather than satisfy them. This section defines layered hard blocks that
> make rule modification require explicit, traceable, human-Tier-2 approval.

### 3.1 Attack surface enumeration

| # | Scenario | Severity |
|---|---|---|
| 1 | Edit `CLAUDE.md` / `AGENTS.md` to delete a rule | Critical |
| 2 | Edit `.pre-commit-config.yaml` to remove a hook | Critical |
| 3 | Edit `pyproject.toml` to lower coverage threshold or relax `[tool.ruff]` rules | Critical |
| 4 | Edit ADR-042 (or this addendum) to add a self-exemption | Critical |
| 5 | Edit `.github/workflows/*.yml` to disable a CI job | Critical |
| 6 | Edit `scripts/committer.py` to skip trailer enforcement | Critical |
| 7 | Edit `docs/identity/humans.yml` to elevate own tier | Critical |
| 8 | Edit `MAINTAINERS` to expand `agents_allowed` | Medium |
| 9 | Edit `.workflow/schema-v2.yaml` to delete a gate | Critical |
| 10 | Edit `src/scieasy/qa/audit/*.py` to suppress a finding | Critical |
| 11 | Use `# noqa` without an issue link | Medium |
| 12 | Edit `docs/facts/generated.yaml` directly (bypassing extractor) | Critical |
| 13 | Settings-file copy-and-redirect (NemoClaw 2026 pattern: clone constraint file, point runtime at clone) | Critical |
| 14 | Edit `tools/codemods/*.py` to skip migration of caller (causing apparent zero-diff but real drift) | Critical |
| 15 | Edit `docs/audit/overrides.log` (or any append-only audit log) | Critical |
| 16 | Edit governance file via path that aliases to it (symlink trickery) | Critical |
| 17 | Submit changes via PR body / commit message prompt-injection that the docs-agent then executes | Critical |

Defenses are layered (3.2–3.6); no single layer is the sole protection.

### 3.2 Layer 1: Governance Paths registry + CODEOWNERS

A new file `.governance-paths.yaml` enumerates every file/glob considered
"governance":

```yaml
# .governance-paths.yaml — pydantic-validated
version: 1
governance_paths:
  # ADRs and specs
  - "docs/adr/**"
  - "docs/spec/**"
  - "docs/adr/_template/**"
  - "docs/spec/_template/**"

  # Agent-facing rule files
  - "AGENTS.md"
  - "CLAUDE.md"
  - "CURSOR.md"
  - "GEMINI.md"
  - ".aiderrc"
  - "**/AGENTS.md"

  # Tool configuration
  - "pyproject.toml"
  - ".pre-commit-config.yaml"
  - "pyrightconfig.json"
  - ".markdownlint.yaml"
  - ".yamllint"
  - ".codespellrc"

  # CI / workflows
  - ".github/workflows/**"
  - ".github/agent-prompts/**"
  - ".github/CODEOWNERS"
  - ".github/PULL_REQUEST_TEMPLATE.md"

  # Workflow state machine
  - ".workflow/**"

  # QA implementation
  - "src/scieasy/qa/**"
  - "scripts/audit/**"
  - "scripts/committer.py"

  # Ownership / identity
  - "MAINTAINERS"
  - "docs/identity/humans.yml"

  # Required-skill manifest
  - "docs/skills/required.yaml"

  # Generated facts (must be regenerated, not hand-edited)
  - "docs/facts/generated.yaml"

  # The governance registry itself (self-reference)
  - ".governance-paths.yaml"

  # Append-only audit logs
  - "docs/audit/governance-changes.log"
  - "docs/audit/baselines/**"            # ratchet wrapper baselines (ADR-042 §26.4)
  - "docs/audit/overrides.log"
  - "docs/audit/commit-log.jsonl"

  # Codemod surface
  - "tools/codemods/**"

honeypot_canaries:
  # See §3.6 — these are tripwires
  - path: ".governance-paths.yaml"
    marker_pattern: "# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE"
```

Pydantic schema validating the above YAML (audit fix W1):

```python
# src/scieasy/qa/schemas/governance.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from scieasy.qa.schemas._common import PathGlob

class HoneypotRuleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    marker_pattern: str

class GovernancePaths(BaseModel):
    """Validates .governance-paths.yaml."""
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    governance_paths: list[PathGlob] = Field(min_length=1)
    honeypot_canaries: list[HoneypotRuleEntry] = Field(default_factory=list)
```

`.github/CODEOWNERS` is generated from this registry:

```
# .github/CODEOWNERS — auto-generated from .governance-paths.yaml
docs/adr/**                @jiazhenz026
docs/spec/**               @jiazhenz026
AGENTS.md                  @jiazhenz026
CLAUDE.md                  @jiazhenz026
pyproject.toml             @jiazhenz026
.pre-commit-config.yaml    @jiazhenz026
.github/workflows/**       @jiazhenz026
.workflow/**               @jiazhenz026
src/scieasy/qa/**          @jiazhenz026
scripts/audit/**           @jiazhenz026
scripts/committer.py       @jiazhenz026
MAINTAINERS                @jiazhenz026
docs/identity/humans.yml   @jiazhenz026
.governance-paths.yaml     @jiazhenz026
docs/skills/required.yaml  @jiazhenz026
```

GitHub branch protection on `main` configures: "Require review from
Code Owners for governance paths." This is the platform-level enforcement
that no agent can bypass.

### 3.3 Layer 2: Pre-commit `governance_mod_guard`

Audit P0.3 fix: split into **two tools** by authority layer. Local pre-
commit cannot reliably verify remote PR review state (no GitHub token, no
PR context, may run before a PR exists). Therefore:

**Tool 1: `scripts/audit/governance_mod_guard.py` (LOCAL pre-commit hook)**

```python
# Local-only: validate trailer SHAPE and reject obvious violations.
# Cannot verify the cited approver actually reviewed (no remote access).
def check_governance_modification(staged_files: list[Path]) -> CheckResult:
    """Local-side governance-edit guardrail.

    Authority limits:
      - This is a LOCAL hook; it cannot query GitHub for PR review state.
      - Its role is to fail fast on obviously-missing trailers and provide
        helpful remediation instructions to the committer.
      - The CI-side tool (governance_mod_pr_check.py) does the actual
        approval verification at PR time.

    Logic:
      1. Resolve which staged files match .governance-paths.yaml entries.
      2. If none → OK.
      3. Detect commit author kind (per ADR-042 §16.2 + §25.2):
           - Human Tier-2 → OK (CI/CODEOWNERS still enforces at PR time)
           - Human Tier-1 / Agent → REQUIRE
               'Governance-Modification-Approved-By: @<Tier2>' trailer
               shape only (do NOT call GitHub here). Print remediation
               with link to docs/contributing/workflows/governance-modification.md.
           - Unknown → REJECT
      4. Cross-check no symlink trickery (resolve real path; reject if
         real path is also governance and staged path isn't).
      5. If governance file is auto-generated, reject any hand-edit;
         only generator scripts may commit (committer.py special mode).
    """
```

**Tool 2: `scripts/audit/governance_mod_pr_check.py` (CI gate, runs on PR)**

```python
# CI-side: verifies the trailer cited a real Tier-2 review on this PR.
def verify_governance_pr(pr_number: int, repo: str) -> CheckResult:
    """CI-side governance-edit verification (authoritative).

    Runs in the governance-modification.yml workflow (ADR-043 §3.5).
    Authority:
      - Has GITHUB_TOKEN (read:org, pull-requests:read).
      - Knows the PR number and can call GitHub API for review state.
      - Authoritative source of truth for approval verification.

    Logic:
      1. Identify governance files modified in the PR diff.
      2. Extract Governance-Modification-Approved-By: trailer from each commit.
      3. For each cited @handle:
           - Verify handle is registered as Tier-2 in docs/identity/humans.yml.
           - Verify GitHub API shows handle has APPROVED this PR via
             `pulls/<n>/reviews` endpoint (state: APPROVED, not stale).
           - Verify CODEOWNERS for the modified path lists the cited handle
             (or any Tier-2 handle).
      4. Verify monotonic_check.py + contradiction_audit + honeypot passed
         on the same PR (these are separate CI jobs; this check just
         confirms they all reported OK).
      5. Block merge if any step fails.
    """
```

**Authority separation**: local hooks enforce **local facts** (trailer
present, format valid, symlink not tricked); CI hooks enforce **remote
facts** (approver is real Tier-2, GitHub review state is current,
CODEOWNERS satisfied). Neither layer claims authority it cannot exercise.

The local hook is registered in `.pre-commit-config.yaml` AND mirrored as
per-runtime `PreToolUse` hooks in Claude Code / Codex hook configs (per
ADR-042 §4.1 three-layer hook scope clarification + §16 committer hard
tooling) — but only as best-effort guardrails (audit P0.1 fix). The CI
hook is the only authoritative check.

### 3.4 Layer 3: Monotonic Strengthening

Rules may only get stricter. Loosening requires explicit approval. This
is enforced by `scripts/audit/monotonic_check.py` running on every PR that
touches a governance file.

#### 3.4.1 Monotonic axes

| Axis | Allowed direction | Forbidden direction |
|---|---|---|
| Coverage threshold | 70 → 80 → 90 | 80 → 70 |
| Required CI gates | 7 → 8 → 9 | 7 → 6 |
| Pre-commit hooks | Add | Remove |
| ruff rule selection | Add rule sets | Remove rule sets |
| mypy strictness flags | Enable | Disable |
| Pytest timeout (lower is stricter) | 60 → 30 | 60 → 120 |
| Required-skill list | Add | Remove |
| `agent_editable: false` paths | Expand | Shrink |
| Path exemptions from doc-drift | Shrink | Expand |
| Trivial fast-lane line limits | Lower | Raise |
| Honeypot canary count | Increase | Decrease |
| Allowed agent runtimes for a MAINTAINERS path | Shrink | Expand |
| Frontmatter required fields | Add | Remove |
| `is_code_implementation: true` ADRs (more rigor) | More ADRs become code-impl | Demote ADR from code-impl |

#### 3.4.2 Loosening protocol

Any loosening change MUST carry all three:

1. **Trailer**: `Loosening-Approved: @<Tier2-handle>` plus
   `Loosening-Reason: <free-text>` on the commit.
2. **Companion addendum**: a new ADR-04N-X addendum (or supersession) that
   documents the loosening and its rationale.
3. **Contradiction audit re-run**: `$scieasy-adr-auditor` runs on the
   amended ruleset; zero critical findings required.

CI rejects loosening changes missing any of the three.

#### 3.4.3 Schema

```python
# src/scieasy/qa/schemas/governance.py (parallel to ADR-042 §6 MAINTAINERS schema pattern)
from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class LoosenedAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    axis: str
    before_value: str
    after_value: str
    file: str
    line: int | None = None


class MonotonicCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loosened: list[LoosenedAxis] = Field(default_factory=list)
    has_loosening_approved_trailer: bool
    approver_handle: str | None = None
    approver_is_tier2_verified: bool = False
    companion_addendum_pr: int | None = None
    contradiction_audit_clean: bool = False
    overall_blocking: bool
```

### 3.5 Layer 4: Recursive self-validation

Any PR that modifies a governance file triggers a special CI workflow:

```yaml
# .github/workflows/governance-modification.yml
name: governance-modification-check
on:
  pull_request: {}    # trigger on every PR; path-filter is done dynamically below

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # Audit fix C2 — derive paths dynamically from .governance-paths.yaml
      # at runtime instead of hand-maintaining a YAML `paths:` list that
      # drifts. The previous hand-list covered only ~12 of ~30 governance
      # paths, leaving CURSOR.md / GEMINI.md / .aiderrc / per-subtree
      # AGENTS.md / audit logs / codemods / agent prompts unprotected.
      - name: Determine governance-path matches in this PR
        id: gov_paths
        run: |
          python -m scieasy.qa.governance.path_filter \
            --paths-yaml .governance-paths.yaml \
            --base "${{ github.event.pull_request.base.sha }}" \
            --head "${{ github.event.pull_request.head.sha }}" \
            --output "$GITHUB_OUTPUT"
      - name: Skip if no governance paths touched
        if: steps.gov_paths.outputs.touched == 'false'
        run: echo "PR does not touch any .governance-paths.yaml entry; skipping recursive self-check."
      - name: Sync-check that this workflow file's path-filter logic was
              actually loaded from .governance-paths.yaml (no hand-edited
              shadow list)
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.governance.workflow_sync_check
      - name: Full audit on modified files
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.audit.full_audit --target-changed
      - name: Re-run contradiction audit on modified ADRs
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.audit.contradiction_audit --targets <modified-adrs>
      - name: Monotonic check (no loosening without approval)
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.governance.monotonic_check --base main --head HEAD
      - name: Honeypot integrity check
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.governance.honeypot --check-all
      - name: Implementation tracker freshness
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.tracker.adr_implementation_check --pr-aware
      - name: Weakened-CI block (§6.4)
        if: steps.gov_paths.outputs.touched == 'true'
        run: python -m scieasy.qa.governance.weakened_ci_check --base main --head HEAD
```

This is a separate, named, **required** check on branch protection — it
cannot be merged around. `path_filter` (a Phase 1E deliverable) reads
`.governance-paths.yaml` at runtime and matches the PR diff against it,
eliminating the hand-list drift the prior YAML `paths:` filter created
(audit fix C2).

### 3.6 Layer 5: Append-only audit log + Honeypot

#### 3.6.1 Audit log

`docs/audit/governance-changes.log` (append-only JSONL, committed to repo):

```python
# src/scieasy/qa/schemas/governance.py (continued)
# audit fix F6: pytest-examples treats each fenced block as independent;
# re-import what's used in this block.
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class GovernanceChangeLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha: str
    timestamp: datetime
    author_handle: str
    author_tier: Literal["agent", "human-tier-1", "human-tier-2"]
    runtime: str | None = None
    files_changed: list[str]
    diff_summary: str
    governance_paths_touched: list[str]
    has_approval_trailer: bool
    approver_handle: str | None = None
    approval_pr: int | None = None
    monotonic_check_result: Literal["ok", "loosening-approved", "loosening-rejected"]
    contradiction_audit_clean: bool
    honeypot_intact: bool
```

The log is written by a `post-commit` hook (after commit success) and a
weekly job verifies log-line-count matches PR-touch-count (catching log
tampering).

#### 3.6.2 Monthly review

A scheduled GitHub Action posts the past-30-days governance change
summary as a tracking-issue comment. Patterns flagged for human review:

- Same maintainer overriding the same rule >3 times.
- Loosening changes clustering on a single subsystem.
- Approval-trailer cited handle has not actually reviewed the corresponding PR.
- Bot or unknown-author commits on governance paths.

#### 3.6.3 Honeypot canaries

`.governance-paths.yaml` contains lines marked
`# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE`. These have **no functional role**;
their sole purpose is detection. Any modification (including whitespace)
triggers:

```python
# src/scieasy/qa/schemas/governance.py (continued)
# audit fix F6: pytest-examples per-block import.
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class HoneypotRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    marker_pattern: str
    expected_sha256: str
    last_verified: datetime


class HoneypotViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_path: str
    violating_commit_sha: str
    violating_author: str
    action_taken: Literal["auto-revert", "block-pr", "notify-only"]
```

The honeypot check runs on every CI run and in pre-commit. Any agent
modifying a canary line is flagged as unacceptable behavior; the
modification is auto-reverted by a bot, and the agent's session is
recorded for review.

### 3.7 ADR self-modification exception

ADR-042 (and this addendum) are themselves governance files. Direct
modification of their body is forbidden after acceptance. Legitimate
revision mechanisms:

1. **New addendum** (preferred): ADR-04N-B, -C, … each goes through full
   workflow, monotonic check, contradiction audit, Tier-2 approval.
2. **Supersession** (when accumulated addendums exceed 5, or a fundamental
   redesign is needed): a new ADR `supersedes` ADR-042 and this addendum,
   bundles all changes, replaces both.
3. **Errata-only patches** (typo, broken link, factual correction with no
   semantic change): allowed with `Errata-Only: <reason>` trailer plus
   Tier-2 approval. Diff size cap: 20 lines. CI auto-validates that the
   diff truly has no semantic content (no governs change, no validator
   change, no fact-value change).

   **Bypass scope for errata-only path** (clarifies §3.5 layered checks):

   | §3 Layer | Errata-only bypass? | Rationale |
   |---|---|---|
   | §3.2 CODEOWNERS + Tier-2 approval | ❌ Required | Errata still touches governance file |
   | §3.3 governance_mod_guard pre-commit | ⚠️ Pre-validates errata shape | Confirms trailer present + diff ≤20 lines + no governs/validator/fact change |
   | §3.4 monotonic_check | ❌ Required | Typo could mask a quantitative regression |
   | §3.5 recursive contradiction_audit | ⚠️ Skipped for pure-typo class (no §-reference, no logic change) | Tightens the bypass; CI heuristic auto-detects |
   | §3.6.1 governance_changes.log entry | ❌ Required | All errata edits logged |
   | §3.6.3 honeypot canary check | ❌ Required | Canary integrity invariant |
   | Tracker freshness (ADR-043 §2.6) | ❌ Required | Tracker mirror always current |

   **SLO**: 1-line typo fix MUST be mergeable within 1 hour of Tier-2 review
   request. If routine errata edits exceed this SLO, the friction model
   itself fails the design and §3.7 must be revisited.

No exception bypasses CODEOWNERS, monotonic check, honeypot, or governance
log; those apply to all three mechanisms. Errata-only only bypasses the
contradiction_audit when CI's syntactic check confirms the diff carries no
semantic content.

---

## 4. Test Quality Enforcement

> Agents under coverage pressure write tests that exercise code without
> verifying behavior. This section codifies the tooling, AST checks, and
> process discipline that detect "test theater."

### 4.1 Tool layer

| Tool | Purpose | Threshold | Phase |
|---|---|---|---|
| `mutmut` (mutation testing) | Modify code; verify tests catch the mutation | Mutation score per package — see §4.5 | Phase 1 introduced; Phase 3 enforced |
| `hypothesis` (property-based) | Force agent to think about invariants where invariants exist | Required for: pure transforms, schemas, parsers, serializers, deterministic invariants. Not required for: side-effectful wrappers, CLI entry points, subprocess launchers, external-app integration, GUI bridges, orchestration glue. When skipped, PR body must cite issue-linked justification. | Phase 1 (report-only); Phase 3 enforced |
| `pytest-deadfixtures` | Catch unused fixtures (lazy copy-paste residue) | 0 dead fixtures | Phase 1 |
| `pytest-randomly` (ordering) | Detect test order dependencies | All tests pass under randomized order | Phase 1 (already planned in ADR-042 §21.1) |
| Branch + path coverage (extending `coverage.py`) | Beyond line coverage | Branch ≥ 85% (Phase 3 target) | Phase 3 |
| `scripts/audit/test_quality.py` (AST anti-pattern) | Detect weak tests by code structure | 0 violations of §4.2 rules | Phase 1 |
| `scripts/audit/test_first_check.py` | Verify test commit precedes implementation commit in same PR (heuristic — test-name→symbol mapping is best-effort) | Per-PR, report-only by default | Phase 1 report-only; enforced only on PRs explicitly labeled `tdd-required` |

### 4.2 AST layer — anti-pattern detection

`src/scieasy/qa/test_quality/ast_lint.py` walks the AST of every test
file under `tests/**/*.py`. Anti-patterns flagged as errors:

```python
# src/scieasy/qa/schemas/test_quality.py
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AntiPattern(StrEnum):
    NO_ASSERT = "no-assert"
    ASSERT_NOT_NONE_ONLY = "assert-not-none-only"
    MOCKS_THE_SUBJECT = "mocks-the-subject"
    ASSERTS_ON_MOCK_CALL_ONLY = "asserts-on-mock-call-count-only"
    HARDCODED_MAGIC_WITHOUT_COMMENT = "hardcoded-magic-without-comment"
    TEST_NAME_CLAIM_MISMATCH = "test-name-says-validates-but-no-related-assert"
    RAISES_WITHOUT_MATCH = "exception-test-without-exception-match"
    SNAPSHOT_WITHOUT_REASONING = "snapshot-without-reasoning"
    EXCESSIVE_MOCKS = "excessive-mocks"
    TEST_ALSO_PROVIDES_GROUND_TRUTH = "test-also-provides-ground-truth"


class AntiPatternFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: AntiPattern
    test_file: str
    test_function: str
    line: int
    severity: Literal["error", "warning"]
    description: str
    suggested_fix: str | None = None


class MutationScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package: str
    mutations_total: int
    mutations_killed: int
    mutations_survived: int
    mutations_timeout: int
    score: float = Field(ge=0.0, le=1.0)
    threshold: float
    passed: bool


class TestQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    generated_at: datetime
    anti_pattern_findings: list[AntiPatternFinding]
    mutation_scores: list[MutationScoreResult]
    dead_fixtures: list[str]
    property_test_coverage: dict[str, bool]  # function -> has @given test
    overall_passed: bool
```

#### 4.2.1 Anti-pattern definitions

| Pattern | What it catches | Why it's bad |
|---|---|---|
| `no-assert` | Test function with no `assert`, `pytest.raises`, or `pytest.warns` | Exercises code without verifying anything |
| `assert-not-none-only` | The only assertion is `assert X is not None` | What should X *be*? Too weak |
| `mocks-the-subject` | The function/class under test is itself mocked | Tautological |
| `asserts-on-mock-call-count-only` | Only `mock.assert_called_once()`; no behavior assertion | Verifies invocation, not result |
| `hardcoded-magic-without-comment` | Magic numbers/strings with no inline comment | Reader can't tell what's significant |
| `test-name-claim-mismatch` | Test named `test_validates_X` but body has no assert touching X | Test theater |
| `raises-without-match` | `pytest.raises(SomeError)` without `match=` regex | Wrong exception passes |
| `snapshot-without-reasoning` | Snapshot test without one-line comment explaining what's locked | Snapshot becomes inviolable for unclear reasons |
| `excessive-mocks` | >6 mocks in a single test function | Likely testing implementation, not behavior |
| `test-also-provides-ground-truth` | The fixture used as expected value is derived from the function under test | Self-confirming |

### 4.3 Process layer

#### 4.3.1 PR template additions

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE.md (additions) -->

## Tests prove what

<!-- One sentence per behavior proven. Forbidden: "tests pass" / "tests added". -->

-

## Test discipline checklist

- [ ] For every behavior change, a failing test was written first (test-first verified in commit order)
- [ ] No tests mock the function or class under test
- [ ] Property tests (`hypothesis`) added for any new public function or pure transform
- [ ] Mutation score for touched packages still meets §4.5 threshold
- [ ] Reviewer has verified each test asserts a meaningful behavior, not just exercises code
```

The "Tests prove what" field is mandatory. CI rejects PRs where it is
empty, contains only "tests pass", or is filled with boilerplate.

#### 4.3.2 Test-first verification

`scripts/audit/test_first_check.py` examines commit history within a PR:

- For each new test function `test_X`, find the commit that introduces it.
- For the corresponding implementation (production function `X`'s
  introducing commit), require that the test commit is **earlier or equal**
  in the PR's commit chain.
- For each test commit, require that the test FAILED if checked out at that
  commit's parent (i.e., the test was genuinely failing before the
  implementation landed). This is verified by running pytest at the
  test-introducing commit's parent and confirming the new test was not
  passing.

This catches "I wrote impl, then wrote a test that immediately passed."

Exemption: tests added for existing code (debt-cleanup, Phase 3) carry
`Backfill-Test:` trailer and bypass the order check.

#### 4.3.3 Reviewer checkbox

The PR template includes:

```markdown
- [ ] **Test review**: I verified each test asserts a meaningful behavior
      (not just exercises code) and the mocks are necessary
```

Cannot be checked by the PR author. CODEOWNERS for `tests/**` enforces a
second reviewer.

### 4.4 The `test-author` skill

A new P0 required skill (additions to ADR-042 §17.1 P0 list):

```markdown
# .claude/skills/test-author/SKILL.md
---
name: test-author
description: Write meaningful tests that assert observable behavior, not exercise code
allowed-tools: [Read, Write, Edit, Bash]
metadata:
  priority: P0
---

# test-author

When asked to write tests, you MUST follow this protocol in order:

1. **Identify the contract.** What observable behavior is being tested?
   Articulate it in one sentence before writing any test code.

2. **Write the assertion first.**
   ```python
   def test_normalize_returns_lowercase():
       result = normalize("AbC")
       assert result == "abc"     # write THIS first
   ```

3. **Run pytest.** Confirm the test FAILS with the expected error type and
   message.

4. **Write the minimum implementation** to make the test pass.

5. **Run pytest again.** Confirm the test PASSES — and verify it's passing
   for the right reason (the assertion you wrote, not a coincidence).

6. **Add edge cases** by repeating 2–5 for each.

7. **Add a property test** with `hypothesis` for the function's invariants
   (e.g., `normalize(normalize(s)) == normalize(s)`).

## Forbidden patterns

The following are AST-flagged as errors by `scripts/audit/test_quality.py`:

- `assert response is not None` (too weak — what should `response` BE?)
- `mock.assert_called_once()` alone (only verifies invocation, not result)
- `def test_X(): foo()` (no assertion at all)
- Mocking the function or class under test
- Hardcoded magic numbers without a comment explaining significance
- Snapshot tests without one-line reasoning

## When uncertain, prefer no edit with explanation.

If you cannot identify a meaningful assertion for some behavior, do not
write a placeholder test. Add a `TODO(#NNN)` and a one-line note explaining
what assertion is missing and why.
```

Per ADR-042 §12.3, this skill is installed into all five supported agent
runtimes via the cross-runtime installer (`agent_provisioning`).

### 4.5 Mutation score targets

| Path | Mutation score target | Enforcement |
|---|---|---|
| `src/scieasy/qa/**` | ≥ 0.90 | Phase 1: report; Phase 3: hard gate |
| `src/scieasy/core/**` | ≥ 0.85 | Phase 3 |
| `src/scieasy/{blocks,engine,api,workflow}/**` | ≥ 0.75 | Phase 3 |
| `src/scieasy/ai/**` | ≥ 0.70 | Phase 3 (lower target — heavy external-API integration, fewer pure-logic paths). Not currently in ADR-042 §14.2 RBP auto-label scope; mutation-testing scope is intentionally broader than RBP scope here. (iter-7 ITER-FRESH-011: scope mismatch documented; ADR-043 owns mutation matrix, ADR-042 owns RBP matrix.) |
| Other (`scripts/`, `tools/`, `tests/` itself) | No target | — |
| **New code added after Phase 4** | **≥ 0.85 (all paths)** | Permanent |

Mutation testing of the entire tree is slow (hours). Strategy:

- **PR CI**: mutation testing scoped to PR-diff-touched modules only
  (10–30 minutes).
- **Weekly cron**: full mutation run; output to `docs/audit/test-quality-trends/`.
- **New code rule**: PR CI fails if any newly added function has mutation
  score below the threshold for its path (baseline + ratchet on this single
  axis only — see ADR-042 §4.3 for why we allow ratchet here: existing
  code's mutation score is unbounded-cost to fix in zero-tolerance mode).

**Platform constraints (audit P1.5 fix)**: per mutmut documentation,
mutation testing requires `os.fork()` and therefore runs cleanly only on
Linux / macOS. Windows users must run mutation locally inside WSL or skip
local mutation runs. CI mutation runs on Linux runners only; the per-PR
gate is Linux-CI-only by design. Documented under
`docs/contributing/reference/mutation-testing.md` (Phase 1 deliverable).

### 4.6 New meta-compliance: M12

Added to ADR-042 §28.5 (will be propagated when fixing the audit findings):

> **M12**: Every QA tool introduced by ADR-042 + ADR-043 has mutation score
> ≥ 0.90 and at least one property-based test. Verified at Phase 4
> revalidation (ADR-042 §28.3).

### 4.7 Audit module entry-point signatures (audit fix F14)

Mirroring ADR-042 §9.6 pattern. Every contract listed in this addendum's
`governs.contracts` that is a function (not a class) gets a stub signature
here so Sphinx nitpicky cross-reference resolution passes once Phase 1
schemas/tools land.

```python
# src/scieasy/qa/tracker/adr_implementation_check.py
from pathlib import Path
from scieasy.qa.schemas.report import AuditReport

def run(repo_root: Path | None = None, *, pr_aware: bool = False) -> AuditReport:
    """Validate the implementation tracker (§2.1) against actual repo state."""
    raise NotImplementedError("Phase 1A deliverable")

# src/scieasy/qa/tracker/phase_gate.py
from typing import Literal
from scieasy.qa.schemas.frontmatter import Phase

def check_phase_transition(from_phase: Phase, to_phase: Phase) -> Literal["ok", "blocked"]:
    """Verify Phase N→N+1 readiness (§2.5)."""
    raise NotImplementedError("Phase 1A deliverable")

# src/scieasy/qa/tracker/tool_self_test_runner.py
from pathlib import Path
from scieasy.qa.schemas.report import Finding

def run_self_test(tool_name: str, repo_root: Path | None = None) -> list[Finding]:
    """Run a QA tool against ADR-042 itself; compare to expected.json (§2.4)."""
    raise NotImplementedError("Phase 1B deliverable")

# src/scieasy/qa/governance/mod_guard.py
def check_governance_modification(staged_files: list[Path]) -> list[Finding]:
    """Local pre-commit guardrail; trailer shape only, no remote check (§3.3)."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/governance/mod_pr_check.py
def verify_governance_pr(pr_number: int, repo: str) -> list[Finding]:
    """CI-side; authoritative PR-approval verification via GitHub API (§3.3)."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/governance/monotonic_check.py
def verify_no_loosening(base_ref: str = "main", head_ref: str = "HEAD") -> list[Finding]:
    """Verify governance rules only get stricter, never weaker (§3.4)."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/governance/honeypot.py
def check_canary_intact(repo_root: Path | None = None) -> list[Finding]:
    """Verify .governance-paths.yaml canary markers unchanged (§3.6.3)."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/governance/weakened_ci_check.py
def verify_no_weakening(base_ref: str = "main", head_ref: str = "HEAD") -> list[Finding]:
    """Detect CI weakening per the 14 patterns in §6.4."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/test_quality/ast_lint.py
def check_test_file(path: Path) -> list[Finding]:
    """AST-walk a test file; emit anti-pattern findings per §4.2."""
    raise NotImplementedError("Phase 1F deliverable")

# src/scieasy/qa/test_quality/test_first_check.py
def verify_ordering(pr_number: int, repo: str) -> list[Finding]:
    """Heuristic: tests committed before impl in same PR (§4.3.2)."""
    raise NotImplementedError("Phase 1F deliverable")

# src/scieasy/qa/test_quality/mutation_runner.py
def run_targeted(changed_modules: list[str], baseline_path: Path) -> list[Finding]:
    """Run mutmut scoped to PR-changed modules; compare to baseline (§4.5)."""
    raise NotImplementedError("Phase 1F deliverable")

# src/scieasy/qa/classification/lint.py
def check_data_classification_present(agents_md_path: Path) -> list[Finding]:
    """Verify AGENTS.md contains §6.1 data-classification section."""
    raise NotImplementedError("Phase 1F deliverable")

def check_assessment_rubric_present(agents_md_path: Path) -> list[Finding]:
    """Verify AGENTS.md contains §6.2 assessment-rubric section."""
    raise NotImplementedError("Phase 1F deliverable")

def check_path_boundary_present(agents_md_path: Path) -> list[Finding]:
    """Verify AGENTS.md contains §6.3 three-tier path-boundary section."""
    raise NotImplementedError("Phase 1F deliverable")

# src/scieasy/qa/governance/path_filter.py    (audit fix iter-7 ITER-FRESH-002)
# Invoked by §3.5 governance-modification.yml step 'Determine governance-
# path matches in this PR'.
def filter(paths_yaml: Path, base: str, head: str, output: Path) -> bool:
    """Compare PR diff against .governance-paths.yaml entries; emit a
    GITHUB_OUTPUT-format 'touched=true|false' line. Returns True iff at
    least one governance path is modified in the diff."""
    raise NotImplementedError("Phase 1E deliverable")

# src/scieasy/qa/governance/workflow_sync_check.py   (audit fix iter-7 ITER-FRESH-002)
# Verifies that .github/workflows/governance-modification.yml uses the
# path_filter dynamic loader (no shadow hand-list of paths).
def verify(repo_root: Path | None = None) -> list[Finding]:
    """Static-parse governance-modification.yml; reject if it contains a
    hardcoded paths: list under `on.pull_request`. Defends against the
    drift mode where the YAML paths: list lags .governance-paths.yaml."""
    raise NotImplementedError("Phase 1E deliverable")
```

---

## 5. CLAUDE.md / AGENTS.md Layered Design (extends ADR-042 §12)

> ADR-042 §12 establishes AGENTS.md as the canonical root document with
> per-subtree nesting. This section refines that design with mechanism-type
> distinctions and a concrete migration plan based on Anthropic's official
> guidance and the OpenClaw pattern.

### 5.1 Mechanism types (4 carriers for rules)

Not all rules belong in the same carrier. Each rule must be assigned to
exactly one of four carriers, based on its required reliability and trigger
shape:

| Carrier | Determinism | Cost | When to use |
|---|---|---|---|
| **Hook** (Claude: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `InstructionsLoaded`, `SessionStart`, `SessionEnd`, `Notification`, `SubagentStop`, `PreCompact` — verified against `code.claude.com/docs/en/hooks`) | **Deterministic within a specific runtime** that supports the specific lifecycle event. NOT a cross-runtime guarantee — Codex / Cursor / Aider / Gemini each define their own hook lifecycles (or none). | High setup, near-zero per-invocation | Best-effort local guardrails per runtime. Hard merge-time guarantees live elsewhere (see row 5 below). |
| **Git hook + CI + branch protection** (cross-runtime guarantee layer) | **Deterministic across all runtimes** | Moderate setup; runs regardless of agent runtime | Rules that MUST hold at merge time for every contributor (e.g., `Assisted-by:` trailer presence, weakened-CI block, MAINTAINERS bidirectional closure). These are the only true hard guarantees. |
| **Path-scoped rule** (`.claude/rules/*.md` with `paths:` frontmatter) | Auto-load on file touch (high reliability) | Loaded on demand; near-zero when not relevant | Rules specific to a file class (e.g., test discipline → `tests/**`, core invariants → `src/scieasy/core/**`) |
| **Skill** (`.claude/skills/<name>/SKILL.md`) | Description-matched (medium reliability) OR manual `/<command>` (perfect) | Loaded on auto-trigger or invocation | Multi-step procedures (e.g., workflow gate, hotfix mode, agent-manager dispatch) |
| **Always-loaded** (`AGENTS.md` body) | Always in context | Context cost every turn | Hard policy, principles, and routing only |

### 5.2 Decision matrix — which carrier for which rule shape

| Rule shape | Carrier | Example |
|---|---|---|
| "Always do X" (every turn, every file) | Always-loaded AGENTS.md | "Do not create files unnecessarily" |
| "When tool T runs, verify Y first" | `PreToolUse` hook | Pre-commit trailer validation |
| "After tool T, do Z" | `PostToolUse` hook | Auto-run ruff format after Edit |
| "When file X is edited, follow rule Y" | Path-scoped rule | `tests/**` → pytest timeout = 60 rule |
| "Multi-step procedure, invoked on demand" | Skill (auto-trigger) | `agent-manager` dispatch |
| "Multi-step procedure, only on explicit user request" | Skill (`disable-model-invocation: true`) | `/hotfix` |
| "Rule that fires when narrowly-defined task arises" | Skill with strong description match | `doc-drift-guard` triggers on doc-edit tasks |
| "Behavior at session end" | `Stop` hook | Tracking branch verification |
| "Block specific tool invocations" | `PreToolUse` hook with reject-on-match | Block `git add .` for agents |
| "Inject reminder into context" | `UserPromptSubmit` hook | "You are in hotfix mode — gates suspended" |

### 5.3 Concrete migration plan: SciEasy current CLAUDE.md → layered structure

SciEasy's current CLAUDE.md is ~1300 lines. The migration produces:

```
AGENTS.md                        ~200 lines  (canonical root; commands + boundaries + routing)
  ├── CLAUDE.md                  ── symlink → AGENTS.md
  ├── CURSOR.md                  ── symlink → AGENTS.md
  ├── GEMINI.md                  ── symlink → AGENTS.md
  └── .aiderrc                   ── pointer: system: AGENTS.md

src/scieasy/core/AGENTS.md       ~40 lines   (frozen contracts list; ADR refs)
src/scieasy/blocks/AGENTS.md     ~40 lines   (block contract pointer; category vs subcategory)
src/scieasy/blocks/ai/AGENTS.md  ~30 lines   (ADR-035-specific constraints)
src/scieasy/qa/AGENTS.md         ~50 lines   (this addendum + ADR-042 scope rules)
frontend/AGENTS.md               ~40 lines   (React; Chrome smoke-test mandatory)
.workflow/AGENTS.md              ~30 lines   (gate state machine semantics)
docs/AGENTS.md                   ~30 lines   (doc authoring rules)
.github/AGENTS.md                ~30 lines   (CI/workflow rules)

.claude/skills/                  (multi-step procedures)
  ├── workflow-gate/             (was CLAUDE.md Appendix A)
  ├── hotfix-mode/               (was CLAUDE.md §11.5; disable-model-invocation: true)
  ├── bug-fix-workflow/          (was CLAUDE.md Appendix C)
  ├── speckit-feature/           (was CLAUDE.md Appendix B)
  ├── agent-manager/             (already exists; standardize via skill-creator)
  ├── dispatch-agents/           (wraps agent-manager with SciEasy defaults)
  ├── test-author/               (NEW per §4.4)
  ├── doc-drift-guard/           (NEW per ADR-042 §17)
  ├── provenance-tagger/         (NEW per ADR-042 §17)
  ├── adr-router/                (NEW per ADR-042 §17)
  ├── pr-maintainer/             (NEW per ADR-042 §17)
  ├── mantis-proof/              (NEW per ADR-042 §14.4)
  ├── session-logs/              (NEW per ADR-042 §17)
  └── release-maintainer/        (NEW per ADR-042 §17)

.claude/rules/                   (path-scoped reference content)
  ├── test-discipline.md         paths: tests/**       (pytest timeout, no npm run dev)
  ├── frontend-smoke-test.md     paths: frontend/**    (Chrome MCP mandatory)
  ├── core-contracts.md          paths: src/scieasy/core/**  (frozen contracts, ADR refs)
  ├── qa-edits.md                paths: src/scieasy/qa/**    (ADR-042/ADR-043 scope)
  ├── adr-edits.md               paths: docs/adr/**          (frontmatter validation reminder)
  ├── governance-edits.md        paths: see .governance-paths.yaml (this addendum §3)
  └── changelog-format.md        paths: CHANGELOG.md         (exact entry format)

scripts/hooks/                   (deterministic enforcement)
  ├── branch-before-edit.sh           (PreToolUse on Edit/Write; block if branch=main)
  ├── pytest-timeout-injection.sh     (PreToolUse on Bash matching pytest)
  ├── block-npm-run-dev.sh            (PreToolUse on Bash matching `npm run dev`)
  ├── trailer-validation.sh           (commit-msg)
  ├── governance-mod-guard.sh         (PreToolUse on Edit/Write of governance paths)
  ├── codex-review-reconcile-cap.sh   (Stop hook; warn on >1 reconcile round)
  ├── tracking-branch-verify.sh       (PreToolUse on gh pr merge)
  └── instructions-loaded-audit.sh    (InstructionsLoaded; log which rules loaded)
```

### 5.4 Migration mapping (current CLAUDE.md → new carriers)

| Current CLAUDE.md content | New carrier | Notes |
|---|---|---|
| §1 Project Identity (what it is / isn't) | Stays in AGENTS.md (always-loaded) | Tightened to ~10 lines |
| §2 Non-Negotiable Principles | Stays in AGENTS.md (always-loaded) | Tightened to one-liners |
| §3 Repository Working Model | Skill (`workflow-overview`) — referenced from AGENTS.md | Multi-step explanation, not a fact |
| §4 Standard Development Workflow | Skill (`workflow-gate`) | Procedure |
| §5 SpecKit Integration | Skill (`speckit-feature`) | Procedure |
| §6 Required Engineering Discipline | Split: hard rules → hooks (branch, no force-push, etc.); soft rules → AGENTS.md | "Must create branch before changes" becomes a hook |
| §7 Coding Boundaries | Path-scoped rule (`core-contracts.md` etc.) per subtree | File-specific rules |
| §9 AI Assistant Operating Rules | Stays in AGENTS.md (always-loaded) | These ARE the universal agent rules |
| §10 Required Documentation Updates | Path-scoped rule (`adr-edits.md`, `changelog-format.md`) | File-specific |
| §11 Definition of Done | Stays in AGENTS.md (always-loaded) | Universal |
| §11.5 Hotfix Mode | Skill (`hotfix-mode`, `disable-model-invocation: true`) | Only fires on explicit `/hotfix` |
| §13 Preferred Task Checklist | Skill (`task-onboarding`) | Procedure |
| §14 Preferred Response Style | Stays in AGENTS.md | Universal |
| Appendix A (6-gate workflow) | Skill (`workflow-gate`) + replaced by ADR-042 §19 Workflow v2 | Procedure |
| Appendix B (SpecKit) | Skill (`speckit-feature`) | Procedure |
| Appendix C (Bug fix workflow) | Skill (`bug-fix-workflow`) | Procedure |

After migration, target AGENTS.md root size: **≤ 200 lines**. Current CLAUDE.md
will be auto-checked against this ceiling by a CI gate added in §6.1 below.

### 5.5 InstructionsLoaded audit (debug which rules actually load)

A `InstructionsLoaded` hook (`scripts/hooks/instructions-loaded-audit.sh`)
logs to `docs/audit/instructions-loaded-trace/<session>.jsonl` every rule
file that was loaded during a session. Run for one week, then analyze
output to identify:

- Rules that loaded but were never cited (candidates for removal).
- Rules that did NOT load when they should have (carrier choice was wrong;
  migrate to hook or path-scoped rule).
- Rules that loaded too often (over-broad `paths:` glob).

This is an explicit debugging step, not a permanent runtime overhead. After
analysis, the hook is disabled until the next audit cycle.

### 5.6 Required AGENTS.md sections (combines §6 additions)

The root `AGENTS.md` and every per-subtree `AGENTS.md` MUST contain the
following sections (in order). Linted by
`scripts/audit/classification_lint.py`:

| Section | Required? | Lint rule |
|---|---|---|
| Identity / Scope | Yes | Section header `## Identity` or `## Scope` |
| Hard policy | Yes | Section header `## Policy` |
| Routing table | Yes | Section header `## Routing` with at least 3 rows |
| **Data classification** (§6.1) | Yes | Section header `## Data classification` |
| **Assessment rubric** (§6.2) | Yes | Section header `## Assessment rubric` |
| **Path boundary** (§6.3) | Yes | Section header `## Paths` with `✅`/`⚠️`/`🚫` markers |
| Out-of-scope TODO format | Yes (root only) | Section header `## Out-of-scope` |

Per-subtree AGENTS.md sections are scoped to that subtree; root sections
are universal. Linting verifies presence; the content is reviewed by
humans.

---

## 6. 2026 Convention Adoptions

> Four conventions emerging from 2026 community research (Gap 1, 2, 3, 8 in
> the original tracking list) are codified here as repo requirements.

### 6.1 Data Classification section (Gap 1)

**Source**: arXiv 2604.21090, 5-principle AGENTS.md completeness rubric;
37% of 34 audited AGENTS.md files fail this requirement.

**Requirement**: every AGENTS.md MUST contain a `## Data classification`
section enumerating, per path glob, the kind of data present and the
sensitivity level:

```python
# src/scieasy/qa/schemas/classification.py
from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    USER_DATA = "user-data"
    SECRETS = "secrets"
    MODEL_ARTIFACTS = "model-artifacts"
    GENERATED_CODE = "generated-code"
    TEST_FIXTURES = "test-fixtures"


class DataClassificationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_glob: str
    data_class: DataClass
    description: str
    handling_constraint: str | None = None


class DataClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[DataClassificationEntry]
```

Example for SciEasy root AGENTS.md:

```markdown
## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/**`, `tests/**`, `docs/**` | public | None special |
| `.github/secrets/**` (if exists) | secrets | Never read in code; only injected via GH Actions |
| `frontend/dist/**` | generated-code | Do not edit directly; regenerate via build |
| `data/fixtures/**` (if exists) | test-fixtures | May edit; never commit large binaries |
| `_skills/`, `agent_provisioning/templates/` | internal | Templates; treat as data assets |
| `docs/identity/humans.yml` | user-data | Edit-blocked; CODEOWNERS-gated (§3.2) |
| `docs/audit/**` | internal | Append-only logs; do not rewrite history |
```

The CI lint `scripts/audit/classification_lint.py` validates:

- The section exists in root AGENTS.md and every per-subtree AGENTS.md.
- Every governed path (per ADR-042 governs.files / MAINTAINERS) is
  classified by at least one entry.
- No path is classified inconsistently between AGENTS.md files (root vs
  subtree must agree on overlapping paths).

### 6.2 Assessment Rubric section (Gap 2)

**Source**: arXiv 2604.21090; the second-most-missing section.

**Requirement**: every AGENTS.md MUST contain an `## Assessment rubric`
section listing concrete, agent-self-checkable done-criteria for tasks
in this scope:

```python
# audit fix W3: pytest-examples per-block imports.
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str
    verification_command: str | None = None
    blocking: bool = True


class AssessmentRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str
    criteria: list[RubricCriterion]
```

Example for SciEasy root AGENTS.md:

```markdown
## Assessment rubric

Before declaring any task complete, verify ALL of the following:

| ID | Criterion | Verify with |
|---|---|---|
| R1 | All new code has docstrings | `interrogate src/` |
| R2 | All new tests assert behavior (no anti-patterns) | `python -m scieasy.qa.test_quality src/` |
| R3 | Mutation score for changed packages meets §4.5 threshold | `mutmut run --paths-to-mutate <changed>` |
| R4 | ADR `governs` updated if public surface changed | `python -m scieasy.qa.audit.doc_drift` |
| R5 | MAINTAINERS bidirectional closure passes | `python -m scieasy.qa.audit.closure` |
| R6 | Trailer `Assisted-by:` present on all agent commits | `python -m scieasy.qa.audit.trailer_lint` |
| R7 | RBP attached if change touches src/scieasy/{blocks,engine,api,workflow}/** or frontend/** | Visual review |
| R8 | CHANGELOG entry added if user-visible change | `git diff CHANGELOG.md` |
| R9 | `docs/zh-CN/<mirror>.md` regenerated if any English doc changed | Translation workflow CI |
| R10 | Workflow v2 stage 5 (implement_validate) passed locally before push | `python -m scieasy.qa.workflow.gate status` |
```

Per-subtree AGENTS.md add scope-specific criteria (e.g., `src/scieasy/qa/`
rubric requires mutation score ≥ 0.90 not 0.75).

CI lint verifies presence + that every criterion has a verification command
(or is explicitly marked `verification_command: null` for human-only checks).

### 6.3 Three-tier Path Boundary convention (Gap 3)

**Source**: GitHub Blog 2025-11 analysis of 2,500 AGENTS.md files; emerging
de-facto convention.

**Requirement**: every AGENTS.md MUST contain a `## Paths` section using the
three-tier marker convention:

| Marker | Meaning |
|---|---|
| ✅ | Always allowed — agent may freely edit |
| ⚠️ | Ask first — agent must obtain explicit approval before edit |
| 🚫 | Never — agent must refuse to edit, even with approval |

```python
class BoundaryLevel(StrEnum):
    ALWAYS = "always"           # ✅
    ASK_FIRST = "ask-first"     # ⚠️
    NEVER = "never"             # 🚫


# audit fix W4: pytest-examples per-block imports.
from pydantic import BaseModel, ConfigDict, Field

class PathBoundaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_glob: str
    level: BoundaryLevel
    reason: str


class PathBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[PathBoundaryEntry]
```

Example for SciEasy root AGENTS.md:

```markdown
## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/**` (excl. core/, qa/) | Free edit; tests required |
| ✅ | `tests/**` | Free edit |
| ✅ | `docs/specs/**`, `docs/audit/**` (own session reports only) | Free edit |
| ⚠️ | `src/scieasy/core/**` | Frozen contracts; requires ADR |
| ⚠️ | `pyproject.toml`, `.pre-commit-config.yaml` | Governance per §3.2 |
| ⚠️ | `docs/adr/**` | Requires Tier-2 approval per §3.3 |
| 🚫 | `src/scieasy/qa/**` (unless ADR-042 implementation phase) | QA tooling owned exclusively |
| 🚫 | `MAINTAINERS`, `docs/identity/humans.yml`, `.github/CODEOWNERS` | Identity/ownership — never auto-edit |
| 🚫 | `docs/audit/overrides.log`, `docs/audit/governance-changes.log`, `docs/audit/commit-log.jsonl` | Append-only audit logs |
| 🚫 | `.governance-paths.yaml` canary lines | Honeypot tripwire per §3.6.3 |
| 🚫 | `docs/facts/generated.yaml` | Auto-generated; hand-edit rejected |
```

CI lint verifies:

- Section exists in root and every subtree AGENTS.md.
- Every path glob in MAINTAINERS appears in at least one boundary entry.
- No glob appears at conflicting boundary levels across files (root vs
  subtree must agree on overlapping coverage).
- ✅/⚠️/🚫 markers are exactly those Unicode characters (not similar-looking
  substitutes).

Per-subtree AGENTS.md may **tighten** but never **loosen** root boundaries
(per §3.4 monotonic strengthening).

### 6.4 Weakened-CI Automatic Block hard gate (Gap 8)

**Source**: GitHub Blog 2026-05-07 explicit doctrine — "Any change that
weakens CI is a blocker. Full stop."

**Requirement**: `scripts/audit/weakened_ci_check.py` runs on every PR. It
inspects the diff for:

| Weakening pattern | Detection |
|---|---|
| Deleted test file | `git diff --diff-filter=D tests/**/*.py` |
| Removed test function within a file | AST diff: function present in main, absent in PR |
| Lowered coverage threshold | `pyproject.toml` `--cov-fail-under` numeric decrease |
| Lowered mutation score threshold | §4.5 thresholds numeric decrease |
| Added `pytest.skip` / `pytest.xfail` without justification trailer | AST scan for new skip/xfail markers without `reason=` containing a `#NNN` issue ref |
| Disabled lint rule | `[tool.ruff.lint]` `select` shrinks OR `ignore` grows |
| Disabled type-check strictness | mypy / pyright config: any strict-* flag set to `false` that was `true` |
| Disabled pre-commit hook | `.pre-commit-config.yaml` hook removal |
| Removed CI job | `.github/workflows/*.yml` job deletion |
| Increased pytest timeout | `timeout = N` value increase |
| Added path to ADR-042 §27 exemptions | `governs.exclusions` growth |
| Added path to `noqa` exemptions | Inline `# noqa` count growth without `(#NNN)` issue link |
| Reduced required-skill list | ADR-042 §17 entry removal |
| Lowered honeypot canary count | `.governance-paths.yaml` count decrease |

Each detected weakening produces a `Finding(severity=error)` and blocks PR
merge UNLESS:

1. The PR carries `Loosening-Approved: @<Tier2-handle>` trailer (per
   §3.4.2).
2. A companion addendum ADR documents the loosening (per §3.4.2).
3. The contradiction audit re-ran clean (per §3.4.2).

This check is **independent** of and **stricter than** §3.4 monotonic check
— §3.4 covers all governance axes; §6.4 specifically covers CI weakening
because GitHub identified it as the highest-frequency-and-impact failure
mode in 2026 agent-PR analysis.

#### 6.4.1 Schema

```python
# src/scieasy/qa/schemas/governance.py (extends §3.4)
# audit fix F6: pytest-examples per-block import.
from enum import StrEnum
from pydantic import BaseModel, ConfigDict
from typing import Literal

class WeakeningKind(StrEnum):
    DELETED_TEST_FILE = "deleted-test-file"
    REMOVED_TEST_FUNCTION = "removed-test-function"
    LOWERED_COVERAGE_THRESHOLD = "lowered-coverage-threshold"
    LOWERED_MUTATION_THRESHOLD = "lowered-mutation-threshold"
    UNJUSTIFIED_SKIP_OR_XFAIL = "unjustified-skip-or-xfail"
    DISABLED_LINT_RULE = "disabled-lint-rule"
    DISABLED_TYPECHECK_FLAG = "disabled-typecheck-flag"
    DISABLED_PRECOMMIT_HOOK = "disabled-precommit-hook"
    REMOVED_CI_JOB = "removed-ci-job"
    INCREASED_PYTEST_TIMEOUT = "increased-pytest-timeout"
    EXPANDED_EXEMPTION_PATHS = "expanded-exemption-paths"
    EXPANDED_NOQA_USAGE = "expanded-noqa-usage"
    REDUCED_SKILL_LIST = "reduced-skill-list"
    REDUCED_HONEYPOT_COUNT = "reduced-honeypot-count"


class WeakeningFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: WeakeningKind
    file: str
    line: int | None = None
    before_value: str
    after_value: str
    has_loosening_approval: bool
    blocking: bool
```

---

## 7. Phase plan adjustments (extends ADR-042 §26)

The deliverables introduced by this addendum are absorbed into the existing
Phase plan as follows:

| Phase | New deliverable (from this addendum) |
|---|---|
| Phase 0 | This addendum (ADR-043) reaches `Accepted` status alongside ADR-042 |
| Phase 0 | `.governance-paths.yaml` created with initial coverage |
| Phase 0 | `.github/CODEOWNERS` generated from governance paths |
| Phase 1 | All §2 monitoring tools (`tracker`, `phase_gate`, `tool_self_test_runner`, `addendum_propagate`) |
| Phase 1 | All §3 governance hard-block tools (`governance_mod_guard`, `monotonic_check`, `honeypot_check`) + workflow `governance-modification.yml` |
| Phase 1 | All §4 test-quality tools (`test_quality` AST lint, `test_first_check`, mutation runner integration) + `test-author` skill |
| Phase 1 | All §5 mechanism design: hooks scaffolded, path-scoped rule files created, CLAUDE.md migration begins |
| Phase 1 | All §6 classification linters + AGENTS.md required-section enforcement |
| Phase 1 | `InstructionsLoaded` audit hook enabled for the audit week |
| Phase 1.5 | Baseline review absorbs the new findings from §2 / §3 / §4 / §6 tooling |
| Phase 2 | CI flip includes the new §3 governance-modification workflow and §6.4 weakened-CI block |
| Phase 3 | CLAUDE.md migration to <200 lines completed; per-subtree AGENTS.md files written; test-quality debt cleaned (anti-patterns purged, mutation scores ratcheted to per-§4.5 targets) |
| Phase 3 | All AGENTS.md required-sections (§6.1, §6.2, §6.3) populated for every per-subtree file |
| Phase 4 | Post-Phase-4 revalidation includes M12 (mutation score) check |
| Phase 5 | Monthly governance-changes review enabled; weekly mutation cron stable |

---

## 8. Updated meta-compliance (M12–M15)

Added to ADR-042 §28.5 (will be propagated during Phase 0 fix pass):

| ID | Requirement | Verification | Status |
|---|---|---|---|
| M12 | Every QA tool from ADR-042 + ADR-043 has mutation score ≥ 0.90 and at least one property-based test | Phase 4 revalidation; `tool_self_test_runner` per-tool report | To be verified at Phase 4 revalidation |
| M13 | Governance change log (§3.6) contains an entry for every commit touching `.governance-paths.yaml`-listed paths in the past 30 days | Weekly cron; absent entries flag log tampering | To be enabled in Phase 5 |
| M14 | Implementation tracker (§2.1) has zero entries past their 14-day grace window in status `not_started` | Per-PR CI gate | To be enabled in Phase 2 (CI flip) |
| M15 | Every AGENTS.md (root + per-subtree) contains all required sections per §5.6 (Identity/Scope, Hard policy, Routing table, Data classification, Assessment rubric, Path boundary, Out-of-scope TODO format) | `classification_lint.py` in pre-commit + CI | To be enabled in Phase 1 (lint scaffold) |

---

## 9. Frontmatter additions to ADR-042 (status: applied)

The audit findings this addendum originally enumerated as "to be added to
ADR-042's frontmatter" were applied during the ADR-042 fix pass completed
2026-05-17 (see ADR-042 audit B1.1 / B2.1 / B3.1 / G3.1 / H3.1 resolutions).
Re-audit (Iter-1 finding B1.043.2) confirmed that virtually all items
listed here were already present in ADR-042's frontmatter; this section is
retained as a record of what was added, not as an active task list.

All items previously enumerated here have been applied; ADR-042 frontmatter
already includes `docs/audit/latest/**` (line 101) as of the iter-4 fix pass.
(Audit fix C4: removed stale "still owed" claim that contradicted
ADR-042's current state.)

Applied (no further action required):

- contracts: `SpecFrontmatter`, `HumanIdentity`, `IdentityRegistry`,
  `frontmatter_lint.lint_file`, `full_audit.run`, `trailer_lint.run`,
  `committer_enforce.check`
- files: `generate_facts.py`, `run_docs_agent.py`,
  `docs_agent_rate_limit.py`, `.github/agent-prompts/docs-agent.md`,
  `docs/skills/required.yaml`, `docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md`,
  `tools/git-fixes-graph.py`, `tools/codemods/**`,
  `docs/audit/commit-log.jsonl`, `docs/audit/reports/**`,
  `docs/audit/archive/**`, `.aiderrc`, three `scripts/migrate/*.py`,
  `docs/sphinx/conf.py`, `pyrightconfig.json`, `.codespellrc`,
  `.yamllint`, `.markdownlint.yaml`
- tests: `tests/qa/test_doc_examples.py`
- related: `[40, 43]` (ADR-042 frontmatter line 11)

---

## 10. Consequences

### 10.1 Positive

- ADR-042's implementation cannot silently drift from spec (§2).
- AI agents cannot self-loosen rules without explicit Tier-2 sign-off (§3).
- Test theater is mechanically detectable (§4).
- CLAUDE.md size reduction frees context budget; narrow rules become
  reliably-firing hooks/path-rules (§5).
- 2026 industry conventions adopted without delay (§6).

### 10.2 Negative

- Substantial additional tooling (~15 new scripts, 10 new schemas, 3 new CI
  workflows, 1 new pre-commit hook bundle).
- Mutation testing on every PR adds 10–30 min CI latency for affected
  modules.
- Governance-modification workflow adds friction for legitimate rule edits
  (intentional — that's the point).
- CLAUDE.md migration is a Phase 3 deliverable that touches many files at
  once; will need careful sub-task decomposition.
- Honeypot canaries occasionally cause confused agents to surface
  themselves; manageable but visible.

### 10.3 Alternatives considered

| Alternative | Reason rejected |
|---|---|
| No implementation tracker (rely on PR descriptions) | PR descriptions are not machine-checkable; the §2 tracker is |
| Trust CODEOWNERS alone for governance | Single layer; defeated if agent CC's a maintainer who rubber-stamps. §3 layers prevent this |
| Mutation testing only on weekly cron | New code's bad tests would land before next cron; per-PR is necessary |
| Keep large CLAUDE.md and "tell agents to follow it harder" | Anthropic official + empirical research both reject this |
| Defer 2026 conventions to a future ADR | Inexpensive to adopt now; standards consolidating fast |
| Make `Human-Override:` apply broader exemptions | Risk: humans become a laundering vector for agent shortcuts |

---

## 11. Known gaps (deferred to future addendums)

| Item | Source | Tracked for | Why deferred |
|---|---|---|---|
| Agent fingerprinting CI job | 2026 research Gap 4 | Future addendum B | Needs separate discussion of false-positive tolerance and privacy implications |
| Prompt-injection sanitization | 2026 research Gap 5 | Future addendum B or security ADR | Needs explicit threat model design |
| Network egress allowlist for agent workflows | 2026 research Gap 7 | Future addendum or ops ADR | Infrastructure concern; depends on hosting environment |
| Defenses for: settings-file copy-and-redirect (NemoClaw), emoji smuggling, multilingual prompt mixing, NeMo-style guardrail regression | 2026 attack-patterns research | Future security ADR | Each needs its own threat model + countermeasure design |
| ICSE/FSE 2026 published governance findings | Conference timing | Future addendum after publication | Not yet available at this addendum's drafting time |
| Lifecycle-provenance work emerging from OpenSSF AI/ML Security WG | 2026 OpenSSF SIGs | Track for future addendum | Spec still maturing |

---

## Appendix A: Cross-references to research sources

| Topic | Source |
|---|---|
| §2 implementation tracker | (novel — no direct precedent; design responds to user-raised gap) |
| §3 governance hard blocks | Linux kernel maintainer-hierarchy + CODEOWNERS pattern; OpenClaw `scripts/committer` enforcement |
| §3.6 honeypot canaries | NemoClaw 2026 attack-pattern research; security-by-detection convention |
| §4 mutation testing | Standard practice (mutmut, cosmic-ray); 2026 research confirms agent-written tests vulnerable to mutation gaps |
| §4.4 test-author skill | OpenClaw skill pattern; Anthropic skill-creator |
| §5 mechanism types | Anthropic official guidance ([memory doc](https://code.claude.com/docs/en/memory), [best-practices](https://code.claude.com/docs/en/best-practices)); OpenClaw "Skills own workflows; root owns hard policy" |
| §6.1 data classification | arXiv 2604.21090 (34-file AGENTS.md completeness rubric) |
| §6.2 assessment rubric | arXiv 2604.21090 |
| §6.3 three-tier path boundary | GitHub Blog 2025-11 analysis of 2,500 AGENTS.md files |
| §6.4 weakened-CI block | GitHub Blog 2026-05-07: "Any change that weakens CI is a blocker. Full stop." |

---

## Appendix B: Decision log (this addendum)

| # | Decision | Date | Decided by | Rationale |
|---|---|---|---|---|
| 1 | Single addendum for Q1+Q2+Q3+AGENTS.md+Gap 1/2/3/8 | 2026-05-17 | @jiazhenz026 | Avoid splintering into 5+ small addendums |
| 2 | Addendum naming: ADR-043 with title prefix "ADR-042 Addendum A" | 2026-05-17 | @claude proposed | Sequential ADR number + clear addendum semantics |
| 3 | Implementation tracker as separate YAML, not inside ADR | 2026-05-17 | @claude proposed | Machine-modifiable per PR; ADR is static |
| 4 | Honeypot canaries in `.governance-paths.yaml` | 2026-05-17 | @claude proposed | Adopted from 2026 security pattern |
| 5 | Mutation score targets: 0.90 / 0.85 / 0.75 by subsystem; new code ≥ 0.85 anywhere | 2026-05-17 | @jiazhenz026 (implied via "test quality" directive) | Phase-3-achievable; permanent ratchet on new code |
| 6 | Test-first verification by commit order, not by TDD enforcement | 2026-05-17 | @claude proposed | Tighter than gentleman's agreement; less than full TDD overhead |
| 7 | Four mechanism types (hook / path-rule / skill / always-loaded) | 2026-05-17 | Anthropic research | Validated by official docs |
| 8 | CLAUDE.md ceiling ≤ 200 lines | 2026-05-17 | Anthropic official | Aligns with documented best practice |
| 9 | Three-tier ✅/⚠️/🚫 marker convention adopted verbatim | 2026-05-17 | GitHub Blog 2025-11 | Emerging fact convention |
| 10 | Weakened-CI block as separate workflow, not part of §3.4 monotonic | 2026-05-17 | @claude proposed | High-frequency-and-impact warrants dedicated check |
| 11 | Deferred items (fingerprinting, prompt-injection, network allowlist, 2026 attack patterns) to future addendums | 2026-05-17 | @claude proposed | Scope discipline; each item needs its own threat model |

---

## Appendix C: Open Discussion Items (Reserved)

> Mirror of ADR-042 Appendix D pattern. Reserved for project owner to add
> items related specifically to this addendum.

### C.1 [Reserved]

(To be filled.)

### C.2 [Reserved]

(To be filled.)

---

<!-- End of ADR-042 Addendum A (ADR-043). -->

---

### ADR-044 — ADR-042 Addendum B: Unified Documentation Set (Contributor / User / Production-Agent / Doc-Guide)

_Status: Accepted_

**Amendments declared in frontmatter (§27.5):**

- **target**: `ADR-042 §21 Tool Stack & CI Topology`
  - **kind**: `extend`
  - **summary**: Adds 9 Sphinx-ecosystem tools (numpydoc, autodoc-pydantic, sphinx-click, sphinxcontrib-openapi, sphinx-gallery, sphinx-design, sphinx-copybutton, sphinx-issues, pydata-sphinx-theme) per §10.1
- **target**: `ADR-042 §23 Docs Build & Cross-reference Enforcement`
  - **kind**: `extend`
  - **summary**: Adds custom Sphinx directives (block/runner/AI-block catalogs) + 5 generators (llms_txt, entry_point_catalog, cli_reference, openapi_reference, schema_reference) per §10.2-10.3
- **target**: `ADR-042 §23.1 (component: furo theme bullet)`
  - **kind**: `replace`
  - **summary**: Replaces the 'furo' bullet under §23.1 Engine list with 'pydata_sphinx_theme'. Other §23.1 bullets (sphinx-autoapi, myst-parser, sphinx-needs, sphinx-substitution-extensions, intersphinx) unchanged. Paired with the §23.2 conf.py snippet update below. (Audit fix W6: corrected from 'in conf.py snippet' — conf.py is in §23.2, not §23.1.)
- **target**: `ADR-042 §23.2 (component: html_theme line in conf.py snippet)`
  - **kind**: `extend`
  - **summary**: Adds 'html_theme = \"pydata_sphinx_theme\"' line to the §23.2 conf.py example (§23.2 currently lacks an explicit html_theme setting). Companion to the §23.1 bullet replace above. (Audit fix W6.)
- **target**: `ADR-042 §21.1 (component: Docs build row furo theme component)`
  - **kind**: `replace`
  - **summary**: Replaces the 'furo' theme component in §21.1 Docs build row with 'pydata_sphinx_theme' to keep §21.1 and §23.1 in lockstep. (Audit fix I5/F16: uses §27.5 resolution-level-2 component syntax.)
- **target**: `ADR-042 §26.2 Phase 1 sub-phase 1B deliverables list`
  - **kind**: `extend`
  - **summary**: Adds auto_generated_lint + doc_length_lint (this addendum's audit tools) to Phase 1B; adds consolidate_cascade.py + doc-set directory skeletons to Phase 1D (audit fix F11)
- **target**: `ADR-042 §26.2 Phase 1 sub-phase 1D deliverables list`
  - **kind**: `extend`
  - **summary**: Adds Sphinx config + custom directives (scieasy_block_catalog / scieasy_runner_catalog / scieasy_ai_block_catalog) + 5 generators + ~40 doc skeletons + translation workflow (audit fix F11)
- **target**: `ADR-042 §17 Required Skills & Cross-Runtime Installer`
  - **kind**: `extend`
  - **summary**: Adds skill-as-pointer convention (skills body ≤ 30 lines referencing canonical workflow/reference doc) per §11
- **target**: `ADR-042 §11 Bidirectional Closure`
  - **kind**: `extend`
  - **summary**: Extends closure to cover docs/contributing/, docs/user/, docs/prod-agent/, docs/doc-guide/; adds skill ↔ workflow-doc closure per §12.3
- **target**: `ADR-042 §28.5 Meta-compliance checklist`
  - **kind**: `extend`
  - **summary**: Adds M16-M19 (§15)
- **target**: `ADR-043 §5 CLAUDE.md / AGENTS.md Layered Design`
  - **kind**: `extend`
  - **summary**: Concretizes mechanism types into the 4-category doc set (contributor/user/prod-agent/doc-guide) per §2.2

**Body of ADR-044:**

<!--
TRANSITIONAL NOTE: This addendum is paired with ADR-042 / ADR-043 and shares
their transitional exemption window (per ADR-042 §3.0). Hardcoded values use
TODO markers; substitution via the fact registry (ADR-042 §10) applies after
Phase 1.

Important clarification: this addendum was authored after a corrected
investigation of ADR-040 (Appendix A). Earlier drafts in the design session
contained a drift error treating ADR-040 as "just FastMCP migration"; the
correct framing is "four-layer production-environment embedded-agent
reliability stack". Where Appendix A and any other ADR text disagree,
Appendix A is correct.
-->

# ADR-042 Addendum B: Unified Documentation Set

## 1. Purpose & Relation to ADR-042 / ADR-043

### 1.1 What this addendum adds

ADR-042 governs QA rules; ADR-043 adds implementation monitoring, rule-mod
hard blocks, test-quality enforcement, AGENTS.md layered design refinement,
and four 2026 convention adoptions. Neither addresses the project's missing
documentation layer.

The missing layer is **HOW** documentation — procedural, machine- and
human-actionable, distinct from WHY (ADR), WHAT (spec), and ENFORCEMENT
(hooks/CI). Without it:

- Human contributors have no consolidated entry to the project's procedures
  (the symptom: even rule authors lose track of their own rules after one
  working day — empirical evidence ADR-042 §2.3 applies to humans too).
- AI agents are routed to skills but skills are short by design (per
  research §3 — Anthropic recommends ≤ 200 lines for instruction files);
  the canonical procedural text has nowhere to live.
- End users (people who `pip install scieasy`) have no documentation at
  all today.
- The production-environment embedded agent (ADR-040) has substantial
  user-facing surface but no maintained operator docs.

### 1.2 What this addendum delivers

- A four-category documentation hierarchy under `docs/` covering
  contributor / user / production-agent / doc-guide concerns.
- Three explicit entry points (`AGENTS.md` for agents, `onboarding.md`
  for human contributors, `quickstart.md` for end users).
- A 2-letter-page document-length discipline (machine-enforced).
- Pydantic schemas for every category's frontmatter.
- Auto-generation infrastructure for user-facing reference (API / CLI /
  blocks / runners / AI blocks / schemas / server API / entry-points / `llms.txt`).
- Anti-drift via skill-as-pointer (per research recommendation).
- Extension of ADR-042's consistency checks to cover ALL documentation
  categories, not only ADR/spec.
- Minimal-viable initial structure (~40 files, not 70+) with explicit
  expansion triggers for later phases.

### 1.3 Relation to ADR-042 and ADR-043

This is an addendum, not a supersession. Per ADR-042 §27.5, precedence is
determined by the `amends:` field in this addendum's frontmatter, NOT by
a global "addendum wins" rule. Each amendment declares its kind (`extend`
/ `replace` / `constrain` / `clarify`); precedence follows that kind. All
amendments in this addendum are `extend`-kind (target prose still applies;
this addendum adds to it). See frontmatter `amends:` for the complete
list — covers ADR-042 §11, §17, §21, §23, §27.5, §28.5 and ADR-043 §5.

### 1.4 Out of scope (deferred)

- Multi-version docs (sphinx-multiversion) — defer to v1.0 release.
- Translation to languages beyond zh-CN — defer.
- Interactive in-browser try-it (`jupyterlite-sphinx`) — defer (post-v1).
- Plot-regression tooling — defer.
- Migrating existing ADRs / specs / architecture into this addendum's
  rules — that work belongs to ADR-042 Phase 3 cleanup, not here.

---

## 2. Documentation Layer Model

### 2.1 Layers

```
WHY (Rationale)         →  ADR        ── architectural decision records
WHAT (Contract)         →  Spec       ── pydantic / JSON schemas, contracts
HOW (Procedure)         →  ★ this addendum's contributor / user / prod-agent docs
HOW (Machine-actionable)→  Skill      ── short pointer + executable steps
ENFORCEMENT             →  Hook / CI  ── deterministic guardrails
```

The HOW layer is the new one. ADRs answer "why we decided X"; specs answer
"what X looks like as a contract"; the doc set answers "how do I do X".

### 2.2 Four document categories

| Category | Path | Audience | Length limit |
|---|---|---|---|
| Contributor | `docs/contributing/` | Human contributors + agents working on the SciEasy repo | ≤ 2 letter pages per file |
| User | `docs/user/` | End users (people running SciEasy in their projects) | ≤ 2 letter pages for hand-authored; AG pages exempt |
| Production-Agent | `docs/prod-agent/` | SciEasy maintainers of ADR-040's prod-env stack + end users seeing prod-env artifacts | ≤ 2 letter pages |
| Doc-Guide | `docs/doc-guide/` | Doc authors (meta-meta) | ≤ 2 letter pages |
| ADR | `docs/adr/` | Architectural decisions | **Exempt** (long-form by design) |
| Spec | `docs/specs/` | Contracts | **Exempt** |
| Architecture | `docs/architecture/` | Big-picture | **Exempt** |

### 2.3 Why categories are siblings, not nested

Each category has different writing style, audience model, and update
cadence. Nesting them (e.g., user docs under contributor docs) would
conflate ownership and confuse readers. The kernel pattern (separate
top-level dirs per audience) is the proven model.

---

## 3. Four Entry Points

### 3.1 The four first-go documents (audit fix F9: was 3, now 4)

| Role | First-read file | Purpose |
|---|---|---|
| AI agent (any runtime) | `AGENTS.md` (repo root) | Canonical agent policy + routing, ≤ 200 lines (per ADR-042 §12) |
| Human contributor (new) | `docs/contributing/onboarding.md` | Short, friendly, ≤ 2 pages, sends reader to relevant workflow |
| Human contributor (configuring AI assistance — read AFTER onboarding) | `docs/contributing/configuring-your-agent.md` | Tabbed instructions for Claude Code / Codex / Cursor / Aider / Gemini setup against this repo, ≤ 2 pages |
| End user (just installed SciEasy) | `docs/user/quickstart.md` | First runnable workflow in 5 minutes |

Each entry is small. Each routes to deeper content. No entry duplicates
another's content.

### 3.2 Shared routing hub

`docs/contributing/index.md` is the common destination for both
contributors and agents AFTER the entry handshake. It is a routing table,
not narrative. It lists every workflow with one-line summaries and links.

`AGENTS.md` links to `docs/contributing/index.md` for full procedural
content; `onboarding.md` likewise. The index is the single source of
project-procedure navigation.

### 3.3 Why configure-your-agent is a peer entry

AI-assisted development is mainstream, so the configure-your-agent doc
is promoted to a peer first-read alongside `onboarding.md` — NOT a
sub-page under `reference/`. The peer-entry status is reflected in §3.1's
table (4 rows, not 3). Reading order for a new human contributor:
`onboarding.md` first (project orientation), then
`configuring-your-agent.md` (wire up your AI assistant).

---

## 4. Document-Length Discipline (2-letter-page rule)

### 4.1 Statement

> Every file under `docs/{contributing,user,prod-agent,doc-guide}/` is
> capped at 2 letter pages. Files exceeding this limit are CI errors. ADR,
> spec, and architecture files are exempt.
>
> **Measurement** (audit P2.1 fix): the cap is enforced on **source-file
> metrics**, not rendered output:
> - non-empty source lines (frontmatter excluded) ≤ 120; AND
> - word count (frontmatter + code blocks excluded) ≤ 600
>
> Source-based metrics are deterministic across themes, viewports, and
> output formats. "Two letter pages" remains editorial guidance for
> authors; the lint enforces the two numeric bounds above.

### 4.2 Rationale

- A 2-page doc fits a single screen + scroll. Reader engagement does not
  collapse the way it does at 5+ pages.
- Maintenance friction scales superlinearly with document length. Short
  docs get updated; long docs go stale.
- Forcing short docs forces tight scope: when a doc grows past the cap,
  it is a signal to split into two procedural files, not to write more
  text.
- Industry evidence: Anthropic's official ≤ 200-line guidance for
  CLAUDE.md and Crosley's ≤ 150-line rule for AGENTS.md (research
  §B) both demonstrate that short instruction files are followed
  better than long ones — the same applies to human-readable workflow
  docs.

### 4.3 Enforcement

`scripts/audit/doc_length_lint.py` runs in pre-commit and CI:

```python
# src/scieasy/qa/audit/doc_length_lint.py — algorithm overview
def check(repo_root: Path) -> list[Finding]:
    """Verify covered docs are ≤ source-line and word-count caps.

    Subject paths: docs/{contributing,user,prod-agent,doc-guide}/**/*.md
    Exempt paths: docs/{adr,specs,architecture}/**/*.md
    Measurement (source-based, deterministic):
      - Strip YAML frontmatter
      - Strip fenced code blocks (for word count only; not for line count)
      - Count non-empty source lines: error if > 120, warning if > 100
      - Count words: error if > 600
    Auto-generated files (frontmatter generation: auto) are exempt
    (length is determined by source code, not by author).
    """
```

### 4.4 What this rules out

| Pattern | Why rejected |
|---|---|
| Long tutorial walkthroughs in `docs/contributing/` | Use `docs/user/tutorials/` (sphinx-gallery, separately governed) |
| Comprehensive reference pages with all options | Use `docs/user/reference/` (auto-generated) |
| Multi-procedure workflow docs | Split into per-procedure files |
| Long narrative explanations | Move to `docs/architecture/` or `docs/adr/` (exempt) |

### 4.5 Exemption mechanism

If a contributor doc legitimately exceeds 120 lines, the frontmatter must
carry `length_exception_reason: "<one-line>"` AND link to an open issue
proposing how to split. The exemption auto-expires 30 days later (CI
escalates to error after expiry).

---

## 5. Pydantic Schemas

### 5.1 Shared enums

```python
# src/scieasy/qa/docs/schemas.py
from __future__ import annotations
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scieasy.qa.schemas.frontmatter import (
    ADRRef, GitHandle, RepoRelativePath, AssistedByLine, LocaleCode,
    AgentEditable, IssueRef, Translation,
)


class Generation(StrEnum):
    """Doc-source authorship kind.

    NOTE: `Generation` is independent of ADR-042 `Translation.auto_generated`.
    `Generation` classifies the source-doc authorship (AUTO=code-generated /
    HAND=hand-authored / HYBRID=mixed). `Translation.auto_generated` flags
    only whether `docs/zh-CN/X.md` was machine-rendered from English source.
    A HAND-generation source doc may still have an auto_generated translation.
    """
    AUTO = "auto"      # code-generated; hand-edits rejected by §10
    HAND = "hand"      # hand-authored
    HYBRID = "hybrid"  # scaffold AG, body HA; mixed editing allowed in marked regions


class DocAudience(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    BOTH = "both"
    END_USER = "end-user"
    OPERATOR = "operator"
    MAINTAINER = "maintainer"


class DocCategory(StrEnum):
    CONTRIBUTING = "contributing"
    USER = "user"
    PROD_AGENT = "prod-agent"
    DOC_GUIDE = "doc-guide"


class AutoGenSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["entry-points", "pydantic-model", "typer-cli", "openapi",
                  "sphinx-autoapi", "facts-registry", "custom"]
    targets: list[str]                  # module paths / file paths / EP groups
    generator: str                      # dotted path to generator function
    last_generated_sha: str | None = None
```

### 5.2 `WorkflowDocFrontmatter`

```python
class WorkflowDocFrontmatter(BaseModel):
    """Frontmatter for docs/contributing/workflows/*.md."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workflow_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    audience: list[DocAudience]
    category: Literal[DocCategory.CONTRIBUTING] = DocCategory.CONTRIBUTING
    generation: Literal[Generation.HAND] = Generation.HAND

    related_skills: list[str] = Field(default_factory=list)
    related_adrs: list[ADRRef] = Field(default_factory=list)
    related_personas: list[str] = Field(default_factory=list)
    related_workflows: list[str] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date

    length_exception_reason: str | None = None
    length_exception_issue: IssueRef | None = None

    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exception_paired_with_issue(self) -> "WorkflowDocFrontmatter":
        if self.length_exception_reason and self.length_exception_issue is None:
            raise ValueError("length_exception_reason requires length_exception_issue")
        return self
```

### 5.3 `UserDocFrontmatter`

```python
class UserDocFrontmatter(BaseModel):
    """Frontmatter for docs/user/**/*.md."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9/-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.USER] = DocCategory.USER
    audience: list[DocAudience]                          # END_USER default
    generation: Generation
    source: AutoGenSource | None = None                  # required iff generation in (AUTO, HYBRID)

    related_adrs: list[ADRRef] = Field(default_factory=list)
    related_user_docs: list[str] = Field(default_factory=list)
    related_blocks: list[str] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _auto_requires_source(self) -> "UserDocFrontmatter":
        if self.generation in (Generation.AUTO, Generation.HYBRID) and self.source is None:
            raise ValueError(
                f"generation={self.generation.value} requires source: AutoGenSource"
            )
        return self
```

### 5.4 `ProdAgentDocFrontmatter`

```python
class ProdAgentDocFrontmatter(BaseModel):
    """Frontmatter for docs/prod-agent/**/*.md.

    Specifically governs documentation about ADR-040's production-environment
    embedded-agent reliability stack (see Appendix A for the corrected
    ADR-040 reference card).
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.PROD_AGENT] = DocCategory.PROD_AGENT
    audience: list[DocAudience]
    governs_adr: Literal[40] = 40                        # explicitly ADR-040
    generation: Literal[Generation.HAND] = Generation.HAND

    related_addenda: list[Literal["A1", "A2", "A3", "A4"]] = Field(default_factory=list)
    related_user_docs: list[str] = Field(default_factory=list)
    related_known_gaps: list[str] = Field(default_factory=list)   # OQ-1, OQ-2, OQ-3, §10 items

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)
```

### 5.5 `DocGuideFrontmatter`

```python
class DocGuideFrontmatter(BaseModel):
    """Frontmatter for docs/doc-guide/**/*.md (meta-meta)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.DOC_GUIDE] = DocCategory.DOC_GUIDE
    generation: Literal[Generation.HAND] = Generation.HAND

    applies_to_categories: list[DocCategory]              # which categories this meta-doc governs
    related_adrs: list[ADRRef] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)
```

### 5.6 Cross-schema invariants

`scripts/audit/frontmatter_lint.py` (extended from ADR-042 §5) gains
category-specific dispatch: a file under `docs/contributing/workflows/` is
validated against `WorkflowDocFrontmatter`; a file under `docs/user/`
against `UserDocFrontmatter`; etc. Files outside the four categories
remain governed by `ADRFrontmatter` / `SpecFrontmatter`.

---

## 6. `docs/contributing/` Structure

### 6.1 Layout

```
docs/contributing/
├── index.md                       # shared routing hub
├── onboarding.md                  # human entry (≤2 pages)
├── first-pr.md                    # human first PR (≤2 pages)
├── configuring-your-agent.md      # peer entry; AI dev is mainstream
├── workflows/                     # 6 core procedural files
│   ├── _template.md
│   ├── new-feature.md
│   ├── bug-fix.md                 # includes triage decision-tree
│   ├── hotfix.md
│   ├── file-adr-or-spec.md        # merged; both are similar
│   ├── testing.md                 # merged unit + integration + weekly e2e
│   └── agent-dispatch.md          # merged agent-manager + multi-agent cascade
├── policy/
│   └── ai-assistance.md           # kernel-standard policy doc
├── reference/
│   ├── gate-cli.md
│   └── trailer-conventions.md
└── handbooks/
    └── README.md                  # placeholder; explains when to add a handbook
```

### 6.2 Workflow doc template (every file follows)

```markdown
---
workflow_id: new-feature
title: "Workflow: New feature development"
audience: [human, agent]
category: contributing
generation: hand
related_skills: [adr-router, workflow-gate]
related_adrs: [42]
related_personas: ["$scieasy-adr-author"]
related_workflows: [file-adr-or-spec, testing]
maintenance_owner: "@jiazhenz026"
last_reviewed: 2026-05-17
---

# Workflow: New Feature Development

## When to use this
…

## When NOT to use this
…

## Prerequisites
- [ ] …

## Steps
1. …
2. …

## Definition of done
- [ ] …

## Common mistakes
- …

## Related
- Skill: `.claude/skills/new-feature/SKILL.md`
- ADR-042 §19 Workflow v2
```

### 6.3 Handbooks deferred

`handbooks/` ships as an empty directory with a README. Subsystem-specific
handbooks (block-development, frontend, etc.) get added when the subsystem
matures enough to need one. Threshold: when the same instruction is
duplicated across ≥ 3 workflow docs, that's a signal to extract a
handbook.

---

## 7. `docs/user/` Structure

### 7.1 Layout

```
docs/user/
├── index.md                       HA
├── install.md                     HA
├── quickstart.md                  HA  single page, ~2 pages, 5-minute first workflow
├── user-guide/                    HA  6 core concepts only
│   ├── workflow-graph.md
│   ├── blocks-and-contracts.md
│   ├── data-objects.md
│   ├── execution-model.md
│   ├── code-runners.md
│   └── ai-blocks.md
├── tutorials/                     HY  sphinx-gallery executable .py, start with 2
│   ├── 01-first-workflow/
│   └── 02-using-r-runner/
├── reference/                     AG  all code-generated, no hand-editing
│   ├── api/                       #   sphinx-autoapi
│   ├── cli.md                     #   sphinx-click from typer
│   ├── blocks/                    #   custom directive over entry-points
│   ├── schemas/                   #   autodoc-pydantic
│   ├── server-api.md              #   sphinxcontrib-openapi from FastAPI
│   └── entry-points.md            #   custom generator
├── plugin-authoring.md            HA  single page, expand later if needed
├── glossary.md                    HA  sklearn-style single page, cross-linked
├── faq.md                         HA
├── prod-env-artifacts.md          HA  explains <project>/CLAUDE.md etc.
└── llms.txt                       AG  emitted at build, OpenClaw pattern
```

### 7.2 User doc style

- "Concise but precise" (per project owner directive).
- Each HA file ≤ 2 pages.
- Code-driven examples preferred over prose explanation.
- Cross-link aggressively to glossary terms.
- Tutorials carry the bulk of the narrative content (sphinx-gallery
  exempt from the 2-page rule since they're self-bounded by example
  size).

### 7.3 Why no separate `getting-started/` directory

Earlier drafts proposed `getting-started/quickstart.md` +
`getting-started/absolute-basics.md` + `getting-started/concepts-overview.md`.
Per the trim discipline, these are merged: `quickstart.md` covers the
first 5 minutes; concepts move to `user-guide/`. One file, one purpose.

### 7.4 `prod-env-artifacts.md`

A single user-doc page that explains what `<project>/CLAUDE.md`,
`<project>/AGENTS.md`, `<project>/.claude/`, `<project>/.codex/` are when
end users see them in their own projects (per ADR-040 §3.5–§3.7). Cross-
links to `docs/prod-agent/README.md` for maintainer-facing content.

---

## 8. `docs/prod-agent/` Minimal Entry

### 8.1 Statement

ADR-040 itself is the source of truth for the production-environment
embedded-agent stack. `docs/prod-agent/README.md` is a single short file
serving as:

- A navigation card pointing readers to ADR-040 for design / decisions
- A maintenance notes index (known issues, upgrade path)
- A pointer to `docs/user/prod-env-artifacts.md` for the user-facing side

When the README exceeds 2 pages OR more than 3 distinct concerns (developer
guidance, ops runbook, user-visible behavior, security model, etc.) emerge,
the README is split into `developer/`, `ops/`, `user-visible/` subdirectories
(this is the original proposal, deferred until size justifies it).

### 8.2 README mandatory contents

```markdown
---
doc_id: prod-agent-readme
title: "Production-environment embedded agent — overview"
category: prod-agent
audience: [maintainer, operator, end-user]
governs_adr: 40
generation: hand
related_addenda: [A1, A2, A3, A4]
related_user_docs: [prod-env-artifacts]
related_known_gaps: [OQ-1, OQ-2, OQ-3]
maintenance_owner: "@jiazhenz026"
last_reviewed: 2026-05-17
---

# Production-environment embedded agent

## What this is
(2 sentences, point to ADR-040)

## What it produces in user projects
(table of artifacts written, ≤ 8 rows, point to user-visible doc)

## Known issues / gaps
(Codex 0.130 Windows gap; OQ-1/OQ-2/OQ-3; ADR-040 §10 deferred items)

## Upgrade flow
(point to ADR-040 §6 phased implementation + Addendum 1 flatten paths)

## How to extend
(brief: add a hook = edit src/scieasy/agent_provisioning/templates/;
add a skill = edit src/scieasy/_skills/scieasy/<name>/;
add an MCP tool = edit src/scieasy/ai/agent/mcp/tools_<group>.py)
```

### 8.3 Why not more pages now

Per project owner directive (current project stage), the documentation
ecosystem must remain medium-scale. Premature subdirectory split creates
empty placeholders that drift; a single dense README serves the small
number of maintainers (currently one) better.

---

## 9. `docs/doc-guide/` Meta-Meta

### 9.1 Three files

```
docs/doc-guide/
├── how-to-write-a-doc.md      ≤2 pages, covers workflow / user / prod-agent in one
├── auto-vs-hand.md            ≤2 pages, AG/HA/HY rules + when each is appropriate
└── ownership-and-review.md    ≤2 pages, owner assignment + 90-day cadence + handoff
```

### 9.2 Self-application

`doc-guide/` files themselves follow the rules they define. They use
`DocGuideFrontmatter` and are subject to the 2-page rule (meta-recursion
preserved).

---

## 10. Auto-Generation Mechanisms

### 10.1 Tool stack additions (extend ADR-042 §21.1)

| Tool | Purpose | Generation target |
|---|---|---|
| `numpydoc` | Docstring grammar (Parameters/Returns/Notes/Examples) | All API ref |
| `sphinx-autoapi` (already in ADR-042 §21.1) | Module API ref | `docs/user/reference/api/` |
| `sphinx-autosummary` | Per-symbol page generation | Same |
| `autodoc-pydantic` | Pydantic model → docs | `docs/user/reference/schemas/` |
| `sphinx-click` | Click/typer CLI → docs | `docs/user/reference/cli.md` |
| `sphinxcontrib-openapi` | FastAPI OpenAPI → docs | `docs/user/reference/server-api.md` |
| `sphinx-gallery` | Executable `.py` examples | `docs/user/tutorials/` + `docs/user/examples-gallery/` |
| `sphinx-design` | Tabs, grids, cards | `configuring-your-agent.md` (per-runtime tabs) |
| `sphinx-copybutton` | Copy-to-clipboard on code blocks | Everywhere |
| `sphinx-issues` | GitHub issue/PR cross-link | Release notes, decision logs |
| `sphinx.ext.linkcode` | Source line links | API ref |
| `sphinx.ext.intersphinx` | Cross-project xref | numpy, pandas, pydantic, fastapi, zarr |
| `pydata-sphinx-theme` | Theme | Whole site |

### 10.2 Custom Sphinx directives

```python
# docs/sphinx/_ext/scieasy_directives.py
# audit fix W5: pytest-examples per-block imports (Sphinx directive API).
# Block is also marked illustrative — see "# pytest-examples: skip" below.
# pytest-examples: skip
from sphinx.util.docutils import SphinxDirective
from docutils.parsers.rst import directives

class ScieasyBlockCatalog(SphinxDirective):
    """Render one autosummary page per block discovered via entry-points.

    Pattern adopted from scikit-learn's per-estimator template:
    every block gets a uniform page with sections:
      - Parameters (from config_schema pydantic model)
      - Inputs / Outputs (from block port declarations)
      - Examples (from block's docstring Examples)
      - Gallery examples (sphinx-gallery thumbnails linking back)
      - Source (linkcode-rendered GitHub line ref)
    """
    has_content = False
    option_spec = {"entry-point-group": directives.unchanged}

    def run(self):
        group = self.options.get("entry-point-group", "scieasy.blocks")
        # ... walk entry_points, render
        return [...]


class ScieasyRunnerCatalog(SphinxDirective):
    """Per-runner doc page (Python / R / Julia) from runner plugin metadata."""
    ...


class ScieasyAIBlockCatalog(SphinxDirective):
    """Per-ADR-035 AI-block registry entry."""
    ...
```

### 10.3 Generators

Build-time generators run before `sphinx-build`:

| Generator | Output | Source |
|---|---|---|
| `llms_txt.generate` | `docs/user/llms.txt` | Walks source toctrees (runs BEFORE sphinx-build) — see note below |
| `entry_point_catalog.generate` | `docs/user/reference/entry-points.md` | `importlib.metadata.entry_points()` for all SciEasy groups |
| `cli_reference.generate` | `docs/user/reference/cli.md` | Reuses sphinx-click |
| `openapi_reference.generate` | `docs/user/reference/server-api.md` | FastAPI `app.openapi()` export |
| `schema_reference.generate` | `docs/user/reference/schemas/*.md` | Walks pydantic models in `src/scieasy/qa/schemas/` etc. |

All generators emit files with `generation: auto` frontmatter and a
`source.last_generated_sha` field. `auto_generated_lint.py` (§11.5 stub +
algorithm note above) refuses hand-edits.

**Generation order note (audit P1.3 fix)**: `llms_txt.generate` reads
**source toctrees** from `docs/sphinx/conf.py` + `*.rst`/`*.md` files, NOT
the rendered HTML ToC. Therefore it runs BEFORE `sphinx-build`. If the
output needs post-render fidelity (e.g., resolved cross-references with
final anchors), a second pass after `sphinx-build` may be added in Phase 5;
for v1, source-toctree walk is sufficient.

### 10.4 Sphinx config

Single `docs/sphinx/conf.py` extends ADR-042 §23.2 with:

```python
# Verified extension module names (per upstream package docs, audit P1.1):
extensions = [
    # ADR-042 §23.2 originals (names corrected):
    "autoapi.extension",            # sphinx-autoapi package
    "myst_parser",
    "sphinx_needs",
    "sphinx_substitution_extensions",
    "sphinx.ext.intersphinx",
    # ADR-044 additions:
    "numpydoc",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.linkcode",
    "sphinx.ext.viewcode",
    "sphinx.ext.graphviz",
    "sphinx_click",
    "sphinxcontrib.openapi",
    "sphinxcontrib.autodoc_pydantic",  # autodoc-pydantic package
    "sphinx_gallery.gen_gallery",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_issues",
    "sphinxext.opengraph",
    # custom (this addendum):
    "scieasy_directives",
    "llms_txt_builder",
]

nitpicky = True
html_theme = "pydata_sphinx_theme"
```

`linkcheck` is a Sphinx **builder**, not an extension. Invoke separately:

```bash
sphinx-build -b linkcheck docs/sphinx _build/linkcheck
```

---

## 11. Anti-Drift via Skill-as-Pointer

### 11.1 Principle (per research recommendation)

> Skills do not duplicate workflow text. Each skill is a short pointer
> file that names a workflow doc and supplies the runtime-specific
> invocation tail.

### 11.2 Skill template

```markdown
---
name: new-feature
description: New feature development workflow
allowed-tools: [Read, Write, Edit, Bash]
---

# new-feature skill

For canonical procedure, read: `docs/contributing/workflows/new-feature.md`

After reading, execute in order:
1. `python .workflow/gate.py start "feat: <one-line>"`
2. Follow the workflow doc's "Steps" section in order
3. Verify against "Definition of done"

When uncertain, prefer no edit with explanation.
```

That is the entire skill file. ~20 lines. No duplicated procedure body.

### 11.3 Skill kinds and pointer targets

Not all skills point to workflow docs. Three skill kinds exist:

| Kind | Pointer target | Examples (per ADR-042 §17.1) |
|---|---|---|
| **Procedural** | `docs/contributing/workflows/<x>.md` | new-feature, bug-fix, hotfix, agent-dispatch, testing |
| **Tool-wrapping** | `docs/contributing/reference/<x>.md` OR the audit tool's module docstring | doc-drift-guard, provenance-tagger, adr-router, mantis-proof, session-logs |
| **Bootstrap/meta** | This addendum's `docs/doc-guide/` or ADR-042 §17.5 | scieasy-skill-creator |

All three kinds remain ≤ 30 body lines and point to a single canonical
target. Tool-wrapping skills MUST cite the tool's module (e.g.,
`scieasy.qa.audit.doc_drift`) AND a one-line behavior summary that
`skill_pointer_sync.py` can verify against the module's `__doc__`.

### 11.4 Audit: `skill_pointer_sync.py`

```python
# src/scieasy/qa/audit/skill_pointer_sync.py — algorithm overview
def check(repo_root: Path) -> list[Finding]:
    """Validate skill-as-pointer convention.

    For every SKILL.md under .claude/skills/ (and cross-runtime equivalents
    per ADR-042 §17.2):
      1. Detect skill kind from frontmatter `kind` field
         (procedural / tool-wrapping / bootstrap-meta).
      2. Extract referenced target path:
         - procedural   → docs/contributing/workflows/[a-z0-9-]+\\.md
         - tool-wrap    → docs/contributing/reference/[a-z0-9-]+\\.md
                          OR scieasy.qa.audit.* module path
         - bootstrap    → docs/doc-guide/[a-z0-9-]+\\.md
      3. Verify the target exists.
      4. Verify SKILL.md body length ≤ 30 lines (excluding frontmatter) —
         enforces the pointer-not-copy discipline.
      5. Verify no procedural text duplication (heuristic: any sequence of
         3+ consecutive numbered list items in SKILL.md is flagged).

    For every docs/contributing/workflows/*.md:
      1. Verify at least one procedural skill references it.
      2. Verify it has a related_skills frontmatter entry naming that skill.

    For every docs/contributing/reference/*.md cited by a tool-wrapping skill:
      1. Verify the reference doc exists and is HAND-generated.
    """
```

### 11.5 Audit module entry-point signatures (audit fix F14)

Mirroring ADR-042 §9.6 pattern. Every function in this addendum's
`governs.contracts` gets a stub signature so Sphinx nitpicky
cross-reference resolution passes once Phase 1 tools land.

```python
# src/scieasy/qa/audit/workflow_sync.py
from pathlib import Path
from scieasy.qa.schemas.report import Finding

def run(repo_root: Path | None = None) -> list[Finding]:
    """Verify skill ↔ workflow-doc pointer integrity (§11.4)."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/audit/auto_generated_lint.py
def check(repo_root: Path | None = None) -> list[Finding]:
    """Reject hand-edits to files with frontmatter generation=auto (§10.3).

    Comparison: each file's mtime vs source.last_generated_sha; if file
    modified after generation without a regenerated_at trailer in commit,
    flag as hand-edit attempt.
    """
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/audit/doc_length_lint.py
def check(repo_root: Path | None = None) -> list[Finding]:
    """Verify docs/{contributing,user,prod-agent,doc-guide}/ files satisfy
    §4.3 source-based length caps (120 lines, 600 words)."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/audit/skill_pointer_sync.py
def check(repo_root: Path | None = None) -> list[Finding]:
    """Validate skill-as-pointer convention per §11 (≤30 body lines,
    references real workflow/reference doc, no procedural duplication)."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/generators/llms_txt.py
from pathlib import Path

def generate(docs_root: Path, output: Path) -> None:
    """Walk source toctrees (BEFORE sphinx-build) and emit OpenClaw-pattern
    llms.txt index for AI consumption (§10.3 note on generation order)."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/generators/entry_point_catalog.py
def generate(docs_root: Path, output: Path) -> None:
    """Emit docs/user/reference/entry-points.md from importlib.metadata
    entry_points() per §10.3."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/generators/cli_reference.py
def generate(docs_root: Path, output: Path) -> None:
    """Emit docs/user/reference/cli.md via sphinx-click integration."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/generators/openapi_reference.py
def generate(docs_root: Path, output: Path) -> None:
    """Emit docs/user/reference/server-api.md from FastAPI app.openapi()."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/generators/schema_reference.py
def generate(docs_root: Path, output: Path) -> None:
    """Emit docs/user/reference/schemas/*.md via autodoc-pydantic over
    every governed pydantic model in src/scieasy/qa/schemas/."""
    raise NotImplementedError("Phase 1D deliverable")

# src/scieasy/qa/docs/directives/scieasy_block_catalog.py
# scieasy_runner_catalog.py / scieasy_ai_block_catalog.py — Sphinx directive
# classes; instantiated by sphinx-build per §10.2. Implementations under
# the corresponding modules. See §10.2 for the directive contract.
```

**`auto_generated_lint` definition site (audit fix F15)**: see signature
stub above + algorithm prose in §10.3 "Generation order note". Earlier
draft language cited §11.3 / §10.3 for the algorithm; corrected to point
here (§11.5 stub block + §10.3 prose).

---

## 12. Extension of ADR-042 Consistency Rules to All Doc Categories

### 12.1 Scope expansion

ADR-042's consistency machinery (§9 a/b/c1/c2/c3/d classification, §10
fact substitution, §11 bidirectional closure, §13 trailer validation,
§14 monotonic strengthening per ADR-043 §3.4) now applies to:

- All ADRs (§/specs/architecture — already in scope)
- **All contributor docs** (`docs/contributing/`) — new
- **All user docs** (`docs/user/`) — new
- **All prod-agent docs** (`docs/prod-agent/`) — new
- **All doc-guide docs** (`docs/doc-guide/`) — new
- **Auto-generated reference files** — drift detection runs, but hand-edit
  attempts are rejected by `auto_generated_lint` (§11.5) before reaching
  drift check

### 12.2 Drift classification adaptations

| Class | Applied to user/contributor/prod-agent docs as |
|---|---|
| a | Doc references symbol; symbol resolves; signature matches |
| b | Symbol resolves but doc claims different behavior |
| c1 | Symbol cited but missing from code; git history shows it existed and was deleted |
| c2 | Symbol cited but never existed |
| c3 | Mixed evidence — manual review |
| d | Public symbol coverage split into two tiers (audit P1.5 fix). **Tier A (user-workflow coverage; hard-required by Phase 2)**: stable public **block classes**, **CLI commands**, **HTTP endpoints**, **plugin contracts**, **data-object contracts**, **externally documented workflow names** — each must appear in a curated user doc. **Tier B (API reference coverage; auto-generated, no hand-doc requirement)**: public Python helper classes / functions / methods — appear via `sphinx-autoapi` in `docs/user/reference/api/`, no separate user-doc obligation unless explicitly exported as supported public API |

### 12.3 Bidirectional closure extension

`closure.py` (ADR-042 §11) extends to include:

- Every workflow doc has at least one skill pointer (forward) AND every
  skill has a workflow doc target (reverse). Symmetric difference = error.
- Every entry-point in `pyproject.toml [project.entry-points.*]` appears
  in `docs/user/reference/entry-points.md` (auto-generated, so naturally
  closed; CI verifies).
- Every public Pydantic model in `governs.contracts` appears in
  `docs/user/reference/schemas/`.
- Every typer CLI command appears in `docs/user/reference/cli.md`.

### 12.4 Translation freshness extension

`docs/zh-CN/` mirror now includes all four new categories. The translator
script (ADR-042 §22.7) handles them identically to ADR / spec
translations.

---

## 13. CI / pre-commit Additions

### 13.1 New pre-commit hooks

```yaml
# .pre-commit-config.yaml additions
- repo: local
  hooks:
    - id: doc-length-lint
      name: Doc length limit (≤2 letter pages)
      entry: python -m scieasy.qa.audit.doc_length_lint
      language: system
      files: ^docs/(contributing|user|prod-agent|doc-guide)/.*\.md$
    - id: workflow-sync
      name: Workflow doc ↔ skill pointer consistency
      entry: python -m scieasy.qa.audit.workflow_sync
      language: system
      pass_filenames: false
    - id: skill-pointer-sync
      name: Skill-as-pointer discipline
      entry: python -m scieasy.qa.audit.skill_pointer_sync
      language: system
      pass_filenames: false
    - id: auto-generated-lint
      name: Reject hand-edits to AG files
      entry: python -m scieasy.qa.audit.auto_generated_lint
      language: system
      files: ^docs/.*\.(md|txt)$    # audit fix I3: include llms.txt
```

### 13.2 New CI workflow `docs-build.yml`

```yaml
name: docs-build
on: [pull_request, push]
jobs:
  docs:
    steps:
      - uses: actions/checkout@v4
      - name: Regenerate auto sources
        run: |
          python -m scieasy.qa.docs.generators.llms_txt
          python -m scieasy.qa.docs.generators.entry_point_catalog
          python -m scieasy.qa.docs.generators.cli_reference
          python -m scieasy.qa.docs.generators.openapi_reference
          python -m scieasy.qa.docs.generators.schema_reference
      - name: Verify no AG drift
        run: git diff --exit-code docs/user/reference/
      - name: Sphinx build (strict)
        run: sphinx-build -b html docs/sphinx _build/html -W --keep-going
      - name: Linkcheck
        run: sphinx-build -b linkcheck docs/sphinx _build/linkcheck
      - name: Doctest
        run: sphinx-build -b doctest docs/sphinx _build/doctest
      - name: Doc-length limit
        run: python -m scieasy.qa.audit.doc_length_lint
      - name: Skill-pointer sync
        run: python -m scieasy.qa.audit.skill_pointer_sync
```

### 13.3 Aggregator `check` extension

The single required check (ADR-042 §21.5) gains a `docs` dependency.

---

## 14. Phase Plan Adjustments

| Phase | New deliverables from this addendum |
|---|---|
| Phase 0 | This addendum reaches `Accepted` status alongside ADR-042 / ADR-043 |
| Phase 1 | (1) All schemas in `src/scieasy/qa/docs/schemas.py`; (2) `doc_length_lint`, `skill_pointer_sync`, `workflow_sync`, `auto_generated_lint` tools; (3) Sphinx config + all custom directives + all generators; (4) `docs/contributing/`, `docs/user/`, `docs/prod-agent/`, `docs/doc-guide/` directory skeletons with stub/placeholder content for every listed file |
| Phase 1.5 | Baseline review of doc-length warnings (existing long docs flagged for split planning) |
| Phase 2 | CI flip — all doc-side checks become fail-on-error |
| Phase 3 | Fill all stub workflow / user / prod-agent / doc-guide content (this is the bulk of the writing) |
| Phase 4 | Post-revalidation: re-render auto pages, verify full closure, verify zh-CN translations complete |
| Phase 5 | Quarterly review cadence on `last_reviewed` fields; auto-issue on stale docs |

---

## 15. Meta-Compliance (M16–M19)

Extends ADR-042 §28.5 (M1–M11) and ADR-043 (M12–M15):

| ID | Requirement | Verification | Status |
|---|---|---|---|
| M16 | Every file under `docs/{contributing,user,prod-agent,doc-guide}/` satisfies the two source-based caps (≤ 120 non-empty source lines AND ≤ 600 words excluding frontmatter+code), or has valid length_exception | `doc_length_lint.py` | To be enabled in Phase 1 |
| M17 | Every skill under any runtime's skill path is a pointer-only file (≤ 30 body lines) referencing a real workflow doc | `skill_pointer_sync.py` | To be enabled in Phase 1 |
| M18 | Tier-A surfaces (block classes / CLI commands / HTTP endpoints / plugin contracts / data-object contracts) each appear in a curated user doc. Tier-B (helper API) auto-appears via sphinx-autoapi; no curated obligation. | `closure.py` reverse-pass extension (Tier-A only) + sphinx-autoapi build (Tier-B) | Tier-A enforced Phase 2; Tier-B verified Phase 4 |
| M19 | Every `docs/zh-CN/` file's `source_sha` matches the current English source | `translation_ok` check (ADR-042 §22.6 AuditReport field) extended to cover all four new doc categories | To be enabled in Phase 1 |

---

## 16. Consequences / Alternatives

### 16.1 Positive

- Single discoverable entry per role (AGENTS.md / onboarding.md / quickstart.md).
- Skills become un-driftable by construction (pointer pattern).
- User-facing surface fully code-generated where machine-knowable.
- 2-page rule forces tight, maintainable docs.
- All docs subject to same consistency machinery as code.

### 16.2 Negative

- ~40 new files to create + maintain. Phase 3 is the bulk of writing work.
- Custom Sphinx directives require their own testing + maintenance.
- 2-page rule will feel restrictive at first; some legitimate docs may
  need splitting that didn't before.
- AG / HA / HY tagging adds frontmatter complexity.
- Translation now covers ~40 more files; DeepL API cost increases.

### 16.3 Alternatives considered

| Alternative | Reason rejected |
|---|---|
| One mega CONTRIBUTING.md (current model) | The exact failure mode we're escaping — long files lose adherence |
| Per-subtree handbooks only (no workflows/ dir) | Workflows cut across subtrees; orthogonal to subsystem ownership |
| Hand-write API reference | Drift inevitable; only auto-gen survives |
| Notebook tutorials instead of sphinx-gallery `.py` | Notebooks don't roundtrip with version control cleanly; gallery `.py` is the proven pattern |
| Full prod-agent split (developer/ops/user-visible from day 1) | Owner directive: medium-scale, no premature subdivision |
| Defer user docs to v1 | User docs are missing TODAY; can't ship without them |
| 5-page limit instead of 2 | Anthropic ≤200-line guidance + research evidence; 5 is too lax |
| No length limit; trust authors | Empirical evidence (research §B): unconstrained docs reliably grow past usefulness |

---

## Appendix A: ADR-040 Corrected Understanding (Reference Card)

> **This appendix is the canonical short summary of ADR-040 for use by any
> ADR / doc that references it.** Earlier ADR-044 drafts contained a drift
> error treating ADR-040 as "just FastMCP migration." This card supersedes
> any such phrasing.

### A.1 True scope of ADR-040

**Title**: Production-environment agent reliability — FastMCP, project
context injection, multi-skill split, prod-env CLAUDE/AGENTS provisioning,
project hooks, Codex parity

**Status**: proposed (2026-05-15), promotes to accepted after Phase 1
green parity test

**One-line characterization**: a four-layer reliability stack for the
production-environment embedded agent (the claude/codex CLI spawned by
SciEasy GUI inside a user's project), comprising six deliverables.

### A.2 The dev-vs-prod binding boundary (§2.1)

| Environment | What | ADR-042/043/044 cover? | ADR-040 cover? |
|---|---|---|---|
| Development | The SciEasy source repo (where contributors work) | YES | NO (explicitly out of scope) |
| Production | A user's SciEasy project (created by `scieasy init` or via GUI) | NO (not directly) | YES (exclusively) |

### A.3 Six deliverables (§3.1–§3.9)

1. FastMCP 3.x migration replacing hand-rolled JSON-RPC MCP server
2. Per-project context injection (fixes unused `project_dir`)
3. Multi-skill split (monolithic SKILL.md → 5 task skills) + relocation
   to `src/scieasy/_skills/` for wheel installability
4. `<project>/CLAUDE.md` + `<project>/AGENTS.md` auto-provisioning
5. Project-scoped `.claude/settings.json` hooks (6 hook scripts)
6. Codex `.codex/config.toml` MCP provisioning + cross-install skills to
   both `~/.claude/skills/` and `~/.agents/skills/`

### A.4 What ADR-040 writes into every user project

- `<project>/CLAUDE.md`, `<project>/AGENTS.md`
- `<project>/.claude/settings.json`, `<project>/.claude/hooks/*.py` (6 scripts)
- `<project>/.claude/skills/<name>/SKILL.md` (flat per Addendum 1)
- `<project>/.agents/skills/<name>/SKILL.md` (flat)
- `<project>/.codex/config.toml`

### A.5 Addenda (all 2026-05-17)

- **A1**: Flatten skill install paths (one level under `skills/`)
- **A2**: Commit-message convention (`[agent]` prefix, `Co-Authored-By:`)
- **A3**: MCP server must silently drop JSON-RPC notifications
- **A4**: Codex hook parity (reverses §3.10 deferral)

### A.6 Explicit out-of-scope (§10) — known gaps

- Layer 7 filesystem ACL on `blocks/`
- BlockRegistry runtime port-type validation
- Sub-agent dispatch, custom slash commands, telemetry, per-turn refresh,
  overlays, eval framework

### A.7 ADR-040's open questions

- **OQ-1**: Provisioning version stamps (upgrade path semantics)
- **OQ-2**: Skill boundary refinement
- **OQ-3**: CLAUDE.md content sign-off process

### A.8 Common misstatements to avoid

These ❌ phrasings would be wrong if encountered in any future ADR / spec /
doc / skill that references ADR-040. The ✅ phrasings are accurate. Listed
here as a defensive reference so downstream agents regenerating from
training-distribution priors do not re-introduce these errors.

- ❌ "ADR-040 = FastMCP migration" → ✅ "ADR-040 = four-layer prod-env agent
  reliability stack (FastMCP is one of six deliverables)"
- ❌ "ADR-040 covers backend MCP cleanup only" → ✅ "ADR-040 has heavy
  user-facing surface (writes 8+ artifacts per user project, defines
  user-visible block/deny semantics)"
- ❌ "ADR-040 touches only `src/scieasy/ai/agent/`" → ✅ "Also `agent_provisioning/`,
  `_skills/`, `cli/install.py`, `cli/main.py::init`, `api/runtime.py`,
  `pyproject.toml`"
- ❌ "No dev/prod distinction" → ✅ "§2.1 makes the dev/prod boundary THE
  binding constraint"

---

## Appendix B: Decision Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Single addendum for all doc-set concerns | Avoid splintering; cohesive design |
| 2 | Addendum named ADR-042 Addendum B (= ADR-044) | Parallel to ADR-043 Addendum A pattern |
| 3 | Four sibling categories (contributing / user / prod-agent / doc-guide) | Kernel audience-by-directory pattern |
| 4 | 2 letter pages per file in non-core docs | Anthropic ≤ 200 line guidance + research evidence |
| 5 | ADR / spec / architecture exempt from length limit | Long-form by design; their drift is governed differently |
| 6 | Skill-as-pointer (no body duplication) | Research §5.3; the only proven anti-drift pattern |
| 7 | Custom Sphinx directive for block catalog | sklearn-style per-estimator template, novel for SciEasy |
| 8 | OpenClaw's llms.txt pattern adopted | AI-native project; strategic advantage |
| 9 | Three entry points (AGENTS.md / onboarding.md / quickstart.md) | One file per role; no entry confusion |
| 10 | `configuring-your-agent.md` at contributing/ root, not in reference/ | AI-assisted dev is mainstream; this is a first-day concern |
| 11 | `docs/prod-agent/` minimal single README | Owner directive: medium-scale; ADR-040 itself is the canonical source |
| 12 | ADR-040 NOT modified by this addendum | Avoid one ADR mutating another; ADR-040 owns its own frontmatter backfill in a future Addendum 5 |
| 13 | AG file hand-edits rejected by CI | Force regeneration; humans/agents cannot drift the auto layer |
| 14 | 90-day review cadence | Research §5.5 evidence; quarterly is the SOTA |
| 15 | Phasing: skeleton in Phase 1, content in Phase 3 | Cap Phase 1 scope; defer bulk writing to dedicated cleanup |
| 16 | Translation extends to all four new categories | One-rule-for-all-docs consistency |
| 17 | Tutorials use sphinx-gallery `.py` not notebooks | Roundtrip with VCS; drift visible in plain diffs |
| 18 | Glossary as single page (sklearn pattern) | Cross-link bridge between API and user-guide |

---

## Appendix C: Cross-references

| ADR-044 element | Source |
|---|---|
| Four-category split | Linux kernel `Documentation/process/` `dev-tools/` `admin-guide/` `doc-guide/` audience separation |
| Workflow doc template | Linux kernel `process/submitting-patches.rst` shape |
| Skill-as-pointer | Research recommendation (no precedent project does this; novel) |
| 2-page rule | Anthropic memory doc ≤ 200 line guideline; Crosley blog ≤ 150 line analysis |
| `llms.txt` | OpenClaw `docs.openclaw.ai/llms.txt` |
| Block catalog directive | scikit-learn per-estimator template pattern |
| `autodoc-pydantic` / `sphinx-click` / `sphinxcontrib-openapi` triumvirate | User-doc research §6 |
| 90-day review cadence | scikit-learn maintainer.rst.template + named-owner pattern |
| Tutorials as sphinx-gallery `.py` | NumPy / scikit-learn convergence |
| AGENTS.md canonical entry | ADR-042 §12 + AGENTS.md open standard (Linux Foundation 2025) |
| Three entry points | This addendum (novel synthesis) |

---

## Appendix D: Open Discussion Items (Reserved)

> Per Appendix D convention from ADR-042 / ADR-043. Reserved for the
> project owner to add items. **Documentation convention (not
> schema-enforced — audit fix W8)**: enforced via human review per
> ADR-043 §3.3 governance_mod_guard, not by the pydantic schema.

### D.1 [Reserved]

(To be filled.)

### D.2 [Reserved]

(To be filled.)

### D.3 [Reserved]

(To be filled.)

---

<!-- End of ADR-042 Addendum B (ADR-044). -->

---

