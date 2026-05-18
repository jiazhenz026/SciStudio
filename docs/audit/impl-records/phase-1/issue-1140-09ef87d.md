# Implementation record: #1140

Phase 1B sub-PR 1 of the ADR-042/043/044 cascade — audit core (TCs
1B.1, 1B.2, 1B.3, 1B.4). Ships the four foundational audit tools that
the orchestrators (sub-PR 2) and specialised lint tools (sub-PR 3) will
compose with. Builds on the merged 1A schemas via the
`track/adr-042/1b-audit-tools` tracking branch.

Implementation SHA: pending (this file is renamed to
`issue-1140-<sha>.md` at commit time).

## Files modified

- `src/scieasy/qa/audit/__init__.py` — NEW. Package marker;
  `__all__` re-exports the four sub-modules so consumers can `from
  scieasy.qa.audit import closure, doc_drift, fact_drift,
  frontmatter_lint`.
- `src/scieasy/qa/audit/closure.py` — NEW. `check_bidirectional()`
  ADR-042 §11 implementation. Loads every Accepted ADR via
  `load_accepted_adrs()` and the top-level `MAINTAINERS` via
  `load_maintainers()`, expands `governs.modules` → set-of-files via
  `_module_to_paths()` (walks `src/<pkg>/` recursively for `*.py`),
  expands `governs.files` and `MAINTAINERS.path_glob` via
  `_glob_to_paths()` + `_fnmatch_recursive()` (treats `**` as
  cross-separator, `*` as segment-bounded). Returns
  `closure.asymmetric` findings for both directions of the symmetric
  difference, `closure.no-maintainers-file` when the file is absent,
  and `closure.multi-adr-conflict` warnings when multiple ADRs share
  `governs.files` ownership with disagreeing `agent_editable` per
  §11.3.2 / Q1B.4.2. Includes a `TODO(#1140-ext)` marker for the
  deferred ADR-044 §12.3 closure extensions (Q1B.4.1).
- `src/scieasy/qa/audit/doc_drift.py` — NEW. `classify_repo()`
  ADR-042 §9 implementation. Builds a static symbol index via
  `griffe.GriffeLoader(search_paths=['src'])`, runs the forward pass
  (ADR `governs.contracts` symbol must resolve in code; signatures
  must match — Phase 1 stub `signatures_match()` returns
  `(True, "")`), runs the reverse pass (`doc-drift.orphan-class` for
  public classes lacking ADR coverage, `doc-drift.missing-docstring`
  warnings for public functions, `doc-drift.missing-all` Phase-1
  warnings for modules without `__all__`), delegates closure to
  `closure.check_bidirectional()`, aggregates into a
  `scieasy.qa.schemas.report.AuditReport`. c-class disambiguation via
  `git log -S --diff-filter=D` (c1 = deleted, c2 = never-existed,
  c3 = mixed) with Levenshtein-on-segments nearest-symbol suggestions
  for c2 hallucinations. Subprocess timeouts and missing-git fall
  back to `unknown`/`never_existed`.
- `src/scieasy/qa/audit/fact_drift.py` — NEW.
  `check_substitutions()` ADR-042 §10 implementation.
  `_load_facts()` reads `docs/facts/generated.yaml` into a
  `FactsRegistry`; `collect_fact_values()` flattens it into a
  `{value: dotted_path}` map via `_walk()` (booleans skipped to avoid
  prose collision; numerics below `numeric_floor=3` and strings
  below `min_length=2` skipped). `_scan_file()` reads each prose
  file (`docs/**/*.{md,rst}` plus root README/AGENTS/CLAUDE/
  CONTRIBUTING), strips fenced code (`_FENCED_RE`), indented blocks
  (`_INDENTED_RE`), and existing substitutions (`_SUBSTITUTION_RE`),
  and emits `fact-drift.hardcoded` findings at a configurable
  severity floor (`--severity-floor` CLI flag, default `warning` per
  ADR §10.6 / Q1B.3.1). `main()` wires the CLI. Numeric values are
  matched with `\b...\b` word boundaries so `7` doesn't false-match
  `17`. Archive / consolidated / baseline paths are excluded.
- `src/scieasy/qa/audit/frontmatter_lint.py` — NEW.
  `lint_file()` ADR-042 §5 + ADR-044 §5.6 dispatch.
  `select_schema()` picks the right pydantic model from one of:
  `ADRFrontmatter`, `SpecFrontmatter`, `WorkflowDocFrontmatter`,
  `UserDocFrontmatter`, `ProdAgentDocFrontmatter`,
  `DocGuideFrontmatter`, or `None` for the permissive fall-through
  bucket (Q1B.2.2). Each pydantic `ValidationError` becomes a
  `frontmatter-lint.<SchemaName>.<error-type>` `Finding`; missing
  closing `---` or non-mapping frontmatter become their own
  rule-IDs. Line numbers are `None` for v1 (full `ruamel.yaml`
  SourceMap deferred per Q1B.2.2 non-blocking note).
- `docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` — NEW.
  Companion file (per §28.0 / Q1B.1.1). Contains the prose-form
  pseudocode for `classify_repo()` that the ADR itself only
  function-overviews. `pytest-examples` allowlist exempt.
- `pyproject.toml` — adds `griffe>=0.45` runtime dep (ADR-042 §9.2
  static symbol-table extraction).
- `tests/qa/test_audit_doc_drift.py` — NEW. 24 tests.
- `tests/qa/test_audit_frontmatter_lint.py` — NEW. 19 tests.
- `tests/qa/test_audit_fact_drift.py` — NEW. 22 tests.
- `tests/qa/test_audit_closure.py` — NEW. 33 tests.
- `CHANGELOG.md` — appended a single `[#1140]` entry under
  `[Unreleased] § Added`.

## Manager defaults applied (from SUMMARY §2)

| ID | Decision | Where applied |
|---|---|---|
| Q1B.1.1 | companion file in `docs/adr/ADR-042/algorithms/` subdir | `docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` |
| Q1B.2.1 | `src/scieasy/qa/audit/frontmatter_lint.py` canonical | path placement |
| Q1B.2.2 | permissive fall-through schema | `select_schema()` returns `None` for non-recognised `docs/contributing/` |
| Q1B.3.1 | `warning` severity floor (CLI configurable) | `fact_drift.main()` default + ADR §10.6 docstring |
| Q1B.4.1 | defer ADR-044 §12.3 closure extensions | `TODO(#1140-ext)` marker in `closure.py` module docstring |
| Q1B.4.2 | conflict-attribute = `agent_editable` | `_check_shared_ownership_conflicts()` |
| Q1B.4.3 | symbol-level closure owned by `doc_drift` d-class, not `closure` | `doc_drift._class_is_governed` + the reverse pass d-class emit |

## Verbatim deviations from ADR text

1. `signatures_match()` is a Phase-1 stub: per §9.5 it should compare
   parameter names, parameter types, return type, and raised
   exceptions; the v1 implementation returns `(True, "")`
   unconditionally for callables that resolve in code. The b-class
   strict-signature path in `classify_repo()` exists but is
   unreachable until the Phase-2 tightening. Recorded as
   `TODO: # tighten signature-matcher` in the function docstring;
   `doc-drift.signature-mismatch` Finding code paths are otherwise
   dead in Phase 1.
2. `git_history_for_symbol()` only differentiates c1 (deletion seen
   in `git log -S --diff-filter=D`) and c2 (no deletion found). The
   §9.3 spec contemplates a richer c3 path that inspects the kind
   of historical match; v1 routes any non-deletion result to c2 and
   only emits c3 when explicit external evidence is passed via
   `_c_class_finding()`. Mentioned in the companion pseudocode.
3. `frontmatter_lint.lint_file()` returns `line=None` for every
   ValidationError finding. ADR §5 implies precise line numbers;
   surfacing them requires `ruumel.yaml` `SourceMap`. Deferred per
   Q1B.2.2 non-blocking note.
4. `closure._glob_to_paths()` walks the working tree via
   `rglob('*')` rather than using `Path.glob(glob)` with the user's
   pattern, because the latter has subtly different `**` semantics
   across Python versions. The custom regex-based matcher is
   documented inline.

## Test summary

- 98 new tests across the four new test files.
- Per-module coverage (audit modules only):
  - `closure.py`: 97% (5 uncovered lines = defensive subprocess fallbacks)
  - `doc_drift.py`: 94% (12 uncovered = mostly the dead b-class signature-mismatch emit path)
  - `fact_drift.py`: 95% (5 uncovered = defensive float-walk + load-fallback branches)
  - `frontmatter_lint.py`: 98% (2 uncovered = empty-docs-subpath edge)
- Existing 1A schema tests (243 prior tests) all still pass.
- mypy `--strict` on `src/scieasy/qa/audit/` clean (resolved one
  `ErrorDetails` arg-type cast and one `Literal` exit_status by
  tightening `_compute_exit_status` return type).
- ruff `check` + `format --check` clean on owned files.
- Phase -0.5 `scripts/audit/temp_review.py` clean.

## Out-of-scope items (deferred with tracking)

- ADR-044 §12.3 closure extensions (workflow↔skill,
  entry-points↔reference, schemas↔reference, CLI↔reference). See
  `TODO(#1140-ext)` in `closure.py`. Manager decision: re-dispatch as
  `1B.4-ext` after sub-phase 1D ships docs translator (per SUMMARY
  Q1B.4.1).
- Phase-2 strict `signatures_match()` (real parameter / type /
  exception comparison). The Phase-1 stub is recorded in the
  function docstring and in the companion pseudocode.
- Real translation freshness check — currently `translation_ok =
  True` placeholder; Phase 1D ships the implementation.
