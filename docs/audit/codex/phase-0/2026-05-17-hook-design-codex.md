# Phase 0 Hook Design — Deterministic SSOT Gap Detection
Date: 2026-05-17
Owner: Manager-codex

## Goal
Create an automated, deterministic gate that compares SSOT interface declarations with repository code and project documentation and emits A/B/C/D classifications.

## Proposed tooling layout
- `tools/spec_audit/manifest.yml`
- `tools/spec_audit/extract_code.py`
- `tools/spec_audit/extract_docs.py`
- `tools/spec_audit/compare.py`
- `tools/spec_audit/policy.py`
- `tools/spec_audit/report.py`

## Deterministic data model
`audit.json` top-level shape:
- `run_metadata`: commit, timestamp, branch, manifest_version
- `interfaces[]`: normalized interface objects
  - `interface_id`
  - `module`
  - `kind` (api/event/schema/convention/block/runtime)
  - `code_evidence[]`
  - `doc_evidence[]`
  - `classification` (`A|B|C|D`)
  - `decision` (`code|docs|defer`)
  - `issue_refs[]`
  - `notes`
- `summary`: counts by class/severity
- `policy_result`: pass/fail + violations

## Extraction strategy
1. `extract_code.py`
   - Parse Python AST for routes/models/events/contracts.
   - Parse TS/TSX for frontend API calls and schema-bearing types.
2. `extract_docs.py`
   - Parse Markdown tables/headings/code-fences in architecture + selected planning/spec docs.
   - Normalize declared contract names and fields.
3. `compare.py`
   - Canonicalize names (`snake_case` + namespace path).
   - Match by interface_id and aliases from manifest.
   - Emit A/B/C/D with field-level diff details.

## CI entrypoint
`python tools/spec_audit/report.py --manifest tools/spec_audit/manifest.yml --out docs/audit/codex/phase-0/generated/`

Outputs:
- `audit.json` (machine)
- `audit.md` (human)
- non-zero exit when `policy.py` fails.
