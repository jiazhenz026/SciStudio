# `ci-implementability.json` reference

> Required by ADR-042 §4.3 (lines 523-526) as the Phase-1-end empirical
> dry-run verification artifact.  Phase 2 (CI flip to all-red enforcement)
> is BLOCKED until this artifact exists and shows every tool in the
> §21.1 stack ran to completion with per-finding output.

## Purpose

ADR-042 §4.3 commits to a zero-tolerance ratchet model.  That model only
works if **every** tool in the §21.1 stack can:

1. Run to completion on the repo without crashing or being silently
   truncated.
2. Emit per-finding output (count + locations).
3. Be wrapped by `.workflow/ci/ratchet.py` (TC-1G.1).
4. Emit SARIF either natively or via an adapter in `.workflow/ci/sarif/`
   (TC-1G.2/1G.3).

`ci-implementability.json` records the empirical answer to those four
questions for each of the 20 tools, at a fixed `phase_1_end_sha`.  The
artifact is produced once, at the end of Phase 1, and pinned in
`docs/audit/reports/<phase-1-end-sha>/ci-implementability.json` for
audit-cycle traceability.

## Schema

The schema is published as
[`docs/audit/ci-implementability.schema.json`](../../audit/ci-implementability.schema.json)
(JSON Schema Draft 2020-12).  Validate with:

```bash
python -m jsonschema -i docs/audit/reports/<sha>/ci-implementability.json \
  docs/audit/ci-implementability.schema.json
```

## Example artifact (template)

```json
{
  "schema_version": "1.0",
  "phase_1_end_sha": "0123456789abcdef0123456789abcdef01234567",
  "generated_at": "2026-06-01T12:34:56Z",
  "branch": "track/adr-042/phase-1-final",
  "ci_runner": "github-actions/ubuntu-latest",
  "tools": [
    {
      "tool": "ruff",
      "version": "0.7.0",
      "command": "ruff check --output-format=json-lines --statistics .",
      "ran_to_completion": true,
      "exit_code": 1,
      "duration_seconds": 4.2,
      "total_findings": 5237,
      "sarif_emitted": true,
      "sarif_path": "docs/audit/sarif/ruff-<sha>.sarif",
      "ratchet_decision": "failure",
      "notes": "Seed baseline is zero; ratchet failure expected on first run."
    }
    // ... 19 more tools
  ]
}
```

## Producing the artifact (Phase 1 end)

The artifact is produced by a one-shot workflow run that:

1. Checks out the Phase-1-end commit.
2. Installs all 20 tools per `pyproject.toml [tool.ci.implementability]`.
3. Runs each tool with its pinned flags (see ADR-042 §4.3 lines 508-515).
4. For each tool, computes:
   - `ran_to_completion` = process exited within timeout AND output file
     is present and non-empty.
   - `total_findings` = count of findings parsed from the tool's output.
   - `sarif_emitted` = SARIF log exists (native or via converter).
   - `ratchet_decision` = invokes `python -m workflow_ci.ratchet
     --tool=<tool> --current=findings.json` and records the verdict.
5. Aggregates per-tool records into one JSON file and uploads as a CI
   artifact.

The wiring step (one-shot workflow) is **out of scope** for the Phase 1G
deliverable; it is opened as a follow-up issue under the Phase 1
umbrella (#1113).  Phase 1G ships the *schema* and *contract* so the
follow-up wiring has a fixed target.

## What "ran to completion" means

A tool ran to completion when:

- The process exited (no SIGKILL by the CI 6-hour wall-clock cap).
- The process exited within a tool-specific budget (default 5 minutes
  per tool; mutmut allowed 30 minutes per ADR-042 §21.1).
- The tool's output file exists at the expected path AND is non-empty
  AND is valid for its format (JSON-parseable, SARIF-parseable, etc.).

A non-zero exit code does **not** mean "did not run to completion" —
most lint tools exit non-zero precisely when they find issues.  The
ratchet wrapper interprets the exit code in context.

## Why we don't ship empirical data in this PR

Phase 1G ships the **infrastructure** to produce `ci-implementability.json`
— not the empirical data itself.  The data is produced once, at the end
of Phase 1, when all 57 toolchains are landed and the stack is complete.

Until then, the seeded baselines under `docs/audit/baselines/` all carry
`total_findings: 0`, and the ratchet wrapper treats any non-zero current
finding count as a regression (which is exactly what we want during the
Phase 1 buildout: every new line of QA code must be self-clean from day
one per ADR-042 §21.6).
