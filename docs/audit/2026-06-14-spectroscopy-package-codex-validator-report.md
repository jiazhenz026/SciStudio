# Spectroscopy Package Checker Report - Codex-Labeled Implementation

Date: 2026-06-14

Target implementation: PR #1663,
`codex/spectroscopy-package-20260614@ebf0f3ba5a443c5b9e5812f4a6cb0ec29d82e17f`

Checker source: PR #1665,
`track/adr-049-package-validator-implementation@b86c1de29e626d8df38dbc3fd206401b61b3ab10`

## Merge Step

Command run in throwaway worktree
`C:\Users\jiazh\Desktop\workspace\sci-wt\spectroscopy-benchmark-codex`:

```powershell
git merge --no-commit --no-ff origin/track/adr-049-package-validator-implementation
```

Result: success, no conflicts. The merge was intentionally not committed; it
was used only to run PR #1665's checker against PR #1663's package.

## Checker Commands

```powershell
$env:PYTHONPATH = "src"
python -m scistudio.cli.package_validator packages/scistudio-blocks-spectroscopy --profile development --json
python -m scistudio.cli.package_validator packages/scistudio-blocks-spectroscopy --profile production --json
```

## Results

| Profile | Exit | Status | Decision | Findings | Contract rows |
|---|---:|---|---|---:|---:|
| `development` | 0 | `pass` | `accept` | 0 | 45 |
| `production` | 0 | `pass` | `accept` | 0 | 45 |

Production report summary:

| Field | Value |
|---|---|
| Schema | `adr049.package_validation_report.v1` |
| Package | `scistudio-blocks-spectroscopy` |
| Version | `0.1.0.dev0` |
| Entry points | 3 |
| Blocks inventoried | 26 |
| Types inventoried | 2 |
| Previewers inventoried | 2 |
| Format capabilities inventoried | 33 |
| Dry-run blocks | 26 |
| Dry-run types | 9 |
| Dry-run previewers | 2 |
| Dry-run format capabilities | 33 |

Inventory highlights:

- Entry points:
  - `scistudio.blocks:spectroscopy`
  - `scistudio.previewers:spectroscopy`
  - `scistudio.types:spectroscopy`
- Block roster includes exactly the accepted 26 spectroscopy blocks.
- Format capability roster includes 33 ADR-043 capabilities.

## Additional Package Test Evidence

```powershell
$env:PYTHONPATH = "src"
python -m pytest packages/scistudio-blocks-spectroscopy/tests -q --no-cov --timeout=60
```

Result: exit 0; 199 tests collected.

## Checker Limitation Observed

The ADR-049 checker validates generic package registration and package-contract
shape. It did not flag spec-specific behavioral drift found in the audit:
static previewer envelopes and SPC/vendor handlers that treat proprietary
formats as generic text or pseudo datasets.
