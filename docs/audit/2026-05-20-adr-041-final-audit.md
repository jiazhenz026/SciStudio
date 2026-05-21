# ADR-041 Final Audit

## Verdict

ADR-041 scoped audit status: pass.

The CodeBlock v2 implementation has no ADR-041-related ADR-042 audit errors
after regenerating `docs/facts/generated.yaml`. The repository-wide aggregate
audit still reports pre-existing failures in older ADR/spec frontmatter and the
ADR-042 consistency spec; those findings do not reference ADR-041 docs,
CodeBlock v2 modules, or the ADR-041 implementation tracks.

## Scope

Audited branch: `feat/issue-1228/adr041-final-audit`

Base branch: `track/adr-041/codeblock-v2`

Included ADR-041 artifacts:

- `docs/adr/ADR-041.md`
- `docs/specs/adr-041-codeblock-v2.md`
- `src/scistudio/blocks/code/**`
- `src/scistudio/workflow/validator.py` CodeBlock validation integration
- `frontend/src/components/BottomPanel.tsx` CodeBlock v2 editor integration
- `tests/blocks/code/**`
- `tests/workflow/test_validator_codeblock_v2.py`
- `frontend/src/components/BottomPanel.test.tsx`

## Checks

| Check | Result | Evidence |
|---|---|---|
| Facts regeneration | Pass | `python scripts/audit/generate_facts.py --write` updated `docs/facts/generated.yaml`. |
| Facts freshness | Pass | `python scripts/audit/generate_facts.py --check`. |
| ADR/spec frontmatter load | Pass | `load_adr_frontmatter("docs/adr/ADR-041.md")` and `load_spec_frontmatter("docs/specs/adr-041-codeblock-v2.md")`. |
| Scoped ADR-042 facts audit | Pass | `python -m scistudio.qa.audit.full_audit --skip-frontmatter-lint --skip-doc-drift --skip-closure --skip-signature-drift --format markdown --output docs/audit/2026-05-20-adr-041-final-audit-scoped.md`; generated report had zero error findings before being summarized here. |
| CodeBlock/workflow tests | Pass | `PYTHONPATH=src python -m pytest tests/blocks/code tests/workflow/test_validator.py tests/workflow/test_validator_dynamic_ports.py tests/workflow/test_validator_codeblock_v2.py --timeout=60 --no-cov` passed with 116 tests and 7 optional-runtime skips. |
| Child PR CI | Pass | PRs #1231, #1233, #1239, #1247, #1248, #1249, #1250, #1255, and #1256 were green before merge into the tracking branch. |

## Repository-Wide Residuals

The full aggregate ADR-042 audit was also run without skips. It failed on
pre-existing or concurrently owned areas:

- missing frontmatter in older ADRs ADR-031 through ADR-040
- invalid/missing frontmatter in older specs such as `appblock-variadic-ports`,
  `data-preview-3d-viewer`, and phase10/phase11 specs
- signature drift in `docs/specs/adr-042-consistency-tools.md`

No full-audit error finding in that run referenced:

- `docs/adr/ADR-041.md`
- `docs/specs/adr-041-codeblock-v2.md`
- `src/scistudio/blocks/code`
- `tests/blocks/code`
- `tests/workflow/test_validator_codeblock_v2.py`
- `frontend/src/components/BottomPanel.tsx`

## Conflict Check

ADR-041 did not modify ADR-043 conflict-guarded files:

- `src/scistudio/blocks/io/capabilities.py`
- `src/scistudio/blocks/io/simple_io.py`
- `src/scistudio/blocks/io/io_block.py`
- `src/scistudio/blocks/registry.py`
- `src/scistudio/engine/materialisation.py`
- `src/scistudio/blocks/app/app_block.py`
- `src/scistudio/blocks/app/bridge.py`
- `packages/scistudio-blocks-*`
- `docs/adr/ADR-043.md`
- `docs/specs/adr-043-*`

## Notes

Optional live runtime tests skip when local tools are unavailable:
Jupyter `nbconvert`, `Rscript`, POSIX shell on Windows, MATLAB, and Octave.
Each backend still has deterministic command construction, missing-tool
diagnostics, and output-collection tests in CI.
