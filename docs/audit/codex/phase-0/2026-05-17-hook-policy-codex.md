# Phase 0 Hook Policy — Fail/Pass Contract
Date: 2026-05-17
Owner: Manager-codex

## Policy levels
- `FAIL`: blocks merge / phase advancement.
- `WARN`: non-blocking but must be listed in drift or backlog.
- `PASS`: no blocking violations.

## FAIL conditions (mandatory)
1. Any `B` entry without explicit canonical decision (`code` or `docs`).
2. Any `C` or `D` entry without issue linkage.
3. Any accepted interface entry without evidence refs (code/doc path).
4. Duplicate `interface_id` definitions with conflicting normalized signatures.

## WARN conditions
1. Alias-based matches with confidence below configured threshold.
2. Missing optional metadata (`notes`, `owner`) on A entries.
3. Unmapped interface kinds discovered by parser but absent from manifest.

## Phase gate behavior
- Phase 0 completes only if policy baseline is documented and checklist row references this file.
- Phase 1+ execution requires keeping this policy unchanged unless manager logs a policy revision decision with rationale.

## Issue linkage format
- Accepted forms: `#<number>` or full URL to repository issue.
- Multiple issues allowed when split into code-fix/docs-fix.
