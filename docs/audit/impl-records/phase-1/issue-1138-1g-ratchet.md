---
title: "Implementation record — TC-1G (ratchet + SARIF + ci-implementability)"
issue: 1138
phase: 1
tc: 1G
date: 2026-05-18
tracks: "#1113"
agent_editable: true
---

# TC-1G implementation record

## Files added

| Path | Purpose | LOC |
|------|---------|-----|
| `.workflow/ci/__init__.py` | Package marker / module docstring. | ~20 |
| `.workflow/ci/baselines.py` | Read/write helpers for `docs/audit/baselines/<tool>.json`. | ~120 |
| `.workflow/ci/ratchet.py` | TC-1G.1 ratchet wrapper. Pure decision function + Checks-API payload builder + CLI. | ~310 |
| `.workflow/ci/sarif/__init__.py` | SARIF subpackage marker. | ~10 |
| `.workflow/ci/sarif/_common.py` | TC-1G.3 fingerprint + SARIF 2.1.0 envelope helpers. | ~150 |
| `.workflow/ci/sarif/ruff_to_sarif.py` | TC-1G.2 ruff JSON-Lines → SARIF. | ~65 |
| `.workflow/ci/sarif/mypy_to_sarif.py` | TC-1G.2 mypy text → SARIF. | ~65 |
| `.workflow/ci/sarif/bandit_to_sarif.py` | TC-1G.2 bandit JSON → SARIF (with partialFingerprints adapter). | ~65 |
| `.workflow/ci/sarif/pyright_to_sarif.py` | TC-1G.2 pyright JSON → SARIF. | ~75 |
| `docs/audit/baselines/<tool>.json` × 20 | TC-1G.4 zero-finding seed baselines for the ADR-042 §21.1 tool stack. | ~7 each |
| `docs/audit/ci-implementability.schema.json` | TC-1G.4 JSON Schema (Draft 2020-12) for the Phase-1-end artifact. | ~125 |
| `docs/contributing/reference/ci-implementability.md` | TC-1G.4 schema reference doc (mandated by ADR-042 §4.3 line 525-526). | ~95 |
| `tests/workflow_ci/conftest.py` | Insert `.workflow/` on `sys.path` so the `ci` package is importable in tests. | ~20 |
| `tests/workflow_ci/test_baselines.py` | Round-trip + validation tests for baselines I/O. | ~175 |
| `tests/workflow_ci/test_ratchet.py` | Pure-decision + CLI tests for the ratchet wrapper. | ~275 |
| `tests/workflow_ci/sarif/test_common.py` | Tests for SARIF envelope + fingerprint determinism. | ~120 |
| `tests/workflow_ci/sarif/test_ruff_to_sarif.py` | ruff → SARIF conversion tests. | ~80 |
| `tests/workflow_ci/sarif/test_mypy_to_sarif.py` | mypy → SARIF conversion tests. | ~75 |
| `tests/workflow_ci/sarif/test_bandit_to_sarif.py` | bandit → SARIF conversion tests. | ~70 |
| `tests/workflow_ci/sarif/test_pyright_to_sarif.py` | pyright → SARIF conversion tests. | ~80 |

## Files modified

| Path | Change |
|------|--------|
| `.github/workflows/ci.yml` | Additive: pin `mypy --soft-error-limit=-1` (per ADR-042 §4.3 line 510-511); inline comment documenting the ruff JSON-Lines pin (Phase 2 wires the actual JSON-Lines step). No job restructuring. |
| `CHANGELOG.md` | Added cascade entry. |

## Rationale

ADR-042 §4.3 lines 481-526 specify zero-tolerance enforcement with three
required Phase-1 deliverables:

1. **`.workflow/ci/ratchet.py`** — per-tool wrapper exploiting GitHub
   `conclusion=neutral` semantics for required checks.  Implemented as a
   pure decision function (`compute_ratchet_decision`) + a Checks-API
   payload builder (`emit_checks_api_payload`) + a CLI (`main`).  The
   HTTP transport to actually POST the payload is intentionally deferred
   to Phase 2 wiring — Phase 1 ships the *infrastructure*, not the live
   CI flip.
2. **SARIF unification** — converters for ruff/mypy/bandit/pyright with
   deterministic `partialFingerprints.primaryLocationLineHash` based on
   SHA-256(rule_id ‖ file_path ‖ normalized_message ‖ line).  Zizmor is
   not in scope because it already emits SARIF natively per §4.3 line
   504-505.
3. **`partialFingerprints` per ADR-042 §4.3 line 506-507** — fingerprint
   computed in `.workflow/ci/sarif/_common.py::compute_partial_fingerprint`.
4. **Tool-flag pinning per §4.3 line 508-515** — applied to mypy
   (`--soft-error-limit=-1`) in `.github/workflows/ci.yml`.  ruff already
   runs; the JSON-Lines variant is wired in Phase 2 alongside the SARIF
   upload step.  zizmor / pydoclint are not currently in CI; their pin
   documentation is captured in this record and in
   `docs/contributing/reference/ci-implementability.md`.

## Decisions / deviations

- **Module path for SARIF**: `.workflow/ci/sarif/` rather than
  `src/scieasy/qa/ci/sarif/`.  The dispatch prompt explicitly allows
  either location; co-locating with the ratchet wrapper keeps the
  CI-adjacent infrastructure layer cohesive and signals that this code
  is *not* part of the importable `scieasy` package surface.
- **`docs/audit/baselines/<tool>.json` are seeded with zero**.  Per
  ADR-042 §4.3 line 467 (*"There is no baseline.json of tolerated
  violations"*), the ratchet starts from zero and learns empirical
  per-tool baselines during the Phase 1.5 sweep.  These seeds exist
  solely as schema-valid placeholders the ratchet can read on its first
  invocation.
- **CLI script invocation** (`python .workflow/ci/ratchet.py`):
  supported via a `__package__` guard that inserts `.workflow/` on
  `sys.path` and imports absolutely.  Module invocation
  (`PYTHONPATH=.workflow python -m ci.ratchet`) is also supported.

## Out of scope (TODO-tagged)

| Area | Location | Followup |
|------|----------|----------|
| HTTP transport to GitHub Checks API | `.workflow/ci/ratchet.py` line ~92 | Phase 2 wiring sub-issue. |
| One-shot workflow that populates `ci-implementability.json` | `docs/contributing/reference/ci-implementability.md` end section | Follow-up issue under #1113 (Phase 1 closing). |
| zizmor / pydoclint flag wiring in CI | `.github/workflows/ci.yml` | Wired in the same Phase 2 PR that adds the upload-sarif step. |

## Test coverage

| Module | Statements | Missed | Coverage |
|--------|-----------|--------|----------|
| `ci/__init__.py` | 1 | 0 | 100% |
| `ci/baselines.py` | 50 | 1 | 98% |
| `ci/ratchet.py` | 79 | 3 | 96% |
| `ci/sarif/__init__.py` | 1 | 0 | 100% |
| `ci/sarif/_common.py` | 38 | 0 | 100% |
| `ci/sarif/bandit_to_sarif.py` | 24 | 0 | 100% |
| `ci/sarif/mypy_to_sarif.py` | 26 | 0 | 100% |
| `ci/sarif/pyright_to_sarif.py` | 31 | 0 | 100% |
| `ci/sarif/ruff_to_sarif.py` | 26 | 0 | 100% |

Aggregate coverage of new code: **≥96%** (clears the ADR-042 §21.6 ≥95%
bar for new QA-cascade code).

The 3 missed lines in `ratchet.py` are the `__main__` direct-script
fallback's `sys.path` insertion (covered indirectly by the on-disk seed
test) and one defensive branch in `_format_summary`.

## Verification

- `ruff check` — clean.
- `ruff format --check` — clean.
- `mypy --soft-error-limit=-1 .workflow/ci/ --ignore-missing-imports` — clean.
- `pytest tests/workflow_ci/ --no-cov --timeout=60` — 79 passed, 0 failed.
- `python -m scripts.audit.temp_review --ci` — 0 findings.
- Manual CLI smoke: `python .workflow/ci/ratchet.py --tool=ruff
  --current=clean.json --baselines-dir=docs/audit/baselines` → emits
  `conclusion=success`; with a non-zero current → emits
  `conclusion=failure` (exit code 1) as expected.
