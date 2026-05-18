# Phase -1 bug-fix sprint checklist

> Single source of truth for the ADR-028 §D8 + adjacent bug-fix wave.
> Conventions: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
> Each tick MUST append → <PR-link>.
>
> Plan: `docs/planning/phase-minus-1-bugfix-plan.md`.

## Wave 1 (Owner: WAVE-1)
- [ ] #1073 IOBlock supported_extensions ClassVar + _detect_format

## Wave 2-A (Owner: WAVE-2-A) — unlocked once #1073 PR merges
- [ ] #1074 LoadData/SaveData
- [ ] #1075 LoadImage/SaveImage

## Wave 2-B (Owner: WAVE-2-B) — unlocked once #1073 PR merges
- [ ] #1076 LCMS plugin IO blocks (SRS has no IO blocks — verified)
- [ ] #1077 BlockRegistry find_loader/find_saver/find_io_blocks_for_type

## Wave 3 (Owner: WAVE-3) — unlocked once #1076 + #1077 PRs merge
- [ ] #1078 core/materialisation.py + utils/fs.mount_pathlike helpers
- [ ] #1079 AppBlock _bin_outputs_by_extension typed reconstruction
- [ ] #1080 AppBlock bridge.py::prepare type-dispatched materialisation

## Acceptance criteria
- [ ] All 8 issues closed via merged PRs
- [ ] No regressions in subprocess smoke / UI smoke
- [ ] CHANGELOG entry added per merged PR (format already compliant)
- [ ] `git grep -nE "_TIFF_EXTS|_ZARR_EXTS|_SUPPORTED_EXTS|_EXT_TO_FORMAT"` returns 0 matches in `packages/` and `src/`
- [ ] `git grep -n "json.dumps(value, default=str)"` in `src/scieasy/blocks/app/bridge.py` returns 0 matches
- [ ] Ready for repo freeze (P-1.2)

## Drift log (append-only)
(empty)
