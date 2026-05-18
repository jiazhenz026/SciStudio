# Phase -1 bug-fix sprint checklist

> Single source of truth for the ADR-028 §D8 + adjacent bug-fix wave.
> Conventions: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
> Each tick MUST append → <PR-link>.
>
> Plan: `docs/planning/phase-minus-1-bugfix-plan.md`.

## Wave 1 (Owner: WAVE-1)
- [x] #1073 IOBlock supported_extensions ClassVar + _detect_format → https://github.com/zjzcpj/SciEasy/pull/1104

## Wave 2-A (Owner: WAVE-2-A) — unlocked once #1073 PR merges
- [x] #1074 LoadData/SaveData → https://github.com/zjzcpj/SciEasy/pull/1106
- [x] #1075 LoadImage/SaveImage → https://github.com/zjzcpj/SciEasy/pull/1108

## Wave 2-B (Owner: WAVE-2-B) — unlocked once #1073 PR merges
- [x] #1076 LCMS plugin IO blocks (SRS has no IO blocks — verified) → https://github.com/zjzcpj/SciEasy/pull/1105
- [x] #1077 BlockRegistry find_loader/find_saver/find_io_blocks_for_type → https://github.com/zjzcpj/SciEasy/pull/1107

## Wave 3 (Owner: WAVE-3 — split 3a + 3b + 3c by dispatcher)
- [~] #1078 core/materialisation.py + utils/fs.mount_pathlike helpers (WAVE-3a; dispatched as template-verbatim agent; PR pending)
- [ ] #1079 AppBlock _bin_outputs_by_extension typed reconstruction (WAVE-3b — blocked by #1078 merge)
- [ ] #1080 AppBlock bridge.py::prepare type-dispatched materialisation (WAVE-3c — blocked by #1078 merge, can run parallel with #1079)

## Acceptance criteria
- [x] All 5 of WAVE-1 + WAVE-2 issues closed via merged PRs (#1073/#1074/#1075/#1076/#1077 → merged to main 2026-05-18)
- [ ] All 3 of WAVE-3 issues closed (#1078/#1079/#1080)
- [ ] No regressions in subprocess smoke / UI smoke
- [x] CHANGELOG entry added per merged PR (5 of 5 entries in [Unreleased])
- [ ] `git grep -nE "_TIFF_EXTS|_ZARR_EXTS|_SUPPORTED_EXTS|_EXT_TO_FORMAT"` returns 0 matches in `packages/` and `src/` — to be verified after WAVE-3 merges
- [ ] `git grep -n "json.dumps(value, default=str)"` in `src/scieasy/blocks/app/bridge.py` returns 0 matches — verified after #1080
- [ ] Ready for repo freeze (P-1.2)

## Follow-up issues opened during the sprint

- #1109 — BlockRegistry.find_loader/find_saver: compound-extension fallback (Codex P1 from PR #1107, deferred under Phase -1 6-gate workflow).
- #1110 — SaveData.supported_extensions: include .markdown / .htm (Codex P2 from PR #1106).

## Drift log (append-only)

- 2026-05-18 — WAVE-1 / WAVE-2 dispatches did NOT use the agent-manager skill templates verbatim. The `[DISPATCH-TEMPLATE-V1: implement]` + `[DISPATCH-COMMON-V1]` markers were missing; the dispatch hook (`scripts/hooks/check-agent-template.sh`) warns rather than blocks, so the dispatches landed despite the deviation. The 5 PRs merged cleanly with no scope drift, but the in-repo checklist update step was skipped (this update is the catch-up commit). WAVE-3a (#1078) dispatched template-verbatim 2026-05-18; WAVE-3b + WAVE-3c will follow the same template-verbatim pattern.
