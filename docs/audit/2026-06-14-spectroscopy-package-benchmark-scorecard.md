# Spectroscopy Package Benchmark Scorecard

Date: 2026-06-14

Competitors:

- Codex-labeled implementation: PR #1663,
  `codex/spectroscopy-package-20260614@ebf0f3ba5a443c5b9e5812f4a6cb0ec29d82e17f`
- Claude-labeled implementation: PR #1666,
  `claudecode/spectroscopy-package@3a9a145e40bffb144eed7647489aa5e4e8569549`

Checker: PR #1665,
`track/adr-049-package-validator-implementation@b86c1de29e626d8df38dbc3fd206401b61b3ab10`

## Result

Winner: **Claude-labeled implementation (PR #1666)**.

Both implementations pass the generic ADR-049 package checker and their local
package test suites. Claude wins because it more fully implements the
user-visible previewer contract, has clearer IO failure boundaries, and carries
substantially deeper tests.

## Scores

| Dimension | Weight | Codex PR #1663 | Claude PR #1666 | Notes |
|---|---:|---:|---:|---|
| Core package roster and entry points | 15% | 9.0 | 9.0 | Both expose 2 types, 26 accepted blocks, 3 entry points, 2 previewers, and 33 format capabilities. |
| Spec contract completeness | 20% | 6.5 | 8.0 | Codex misses previewer behavior and misrepresents SPC/vendor formats. Claude has deferred SPC/vendor handlers but cleaner boundaries. |
| Previewer implementation | 15% | 4.0 | 8.5 | Codex returns static envelopes with no frontend manifest. Claude has providers, bounded data access tests, resources, diagnostics, and `viewer.js`. |
| IO and capability fidelity | 15% | 5.0 | 7.0 | Codex treats SPC/vendor paths as text or pseudo datasets. Claude explicitly defers binary/vendor paths with TODOs; xlsx tests skipped locally. |
| Processing block behavior | 10% | 8.0 | 8.5 | Both cover accepted methods and outputs. Claude has broader e2e and boundary coverage. |
| Test depth and evidence | 10% | 6.5 | 8.5 | Codex: 17 test files, 111 test functions, 199 collected. Claude: 40 test files, 355 test functions, 461 passed plus 6 local xlsx skips. |
| Package checker result | 5% | 10.0 | 10.0 | Both `development` and `production` profiles pass with 0 findings across 45 contract rows. |
| Scope discipline and drift risk | 5% | 6.0 | 8.0 | Codex has silent format behavior drift. Claude's remaining gaps are visible and tracked. |
| Maintainability | 5% | 7.0 | 8.0 | Codex is compact but hides too much in one file. Claude has more files but clearer IO/provider separation. |

Weighted score:

| Implementation | Weighted score |
|---|---:|
| Codex PR #1663 | 6.95 / 10 |
| Claude PR #1666 | 8.25 / 10 |

## Checker Results Summary

| Implementation | Checker merge | Development profile | Production profile |
|---|---|---|---|
| Codex PR #1663 | no conflicts | pass / accept / 0 findings | pass / accept / 0 findings |
| Claude PR #1666 | no conflicts | pass / accept / 0 findings | pass / accept / 0 findings |

The checker is useful for package shape and registration readiness, but it is
not sufficient as the sole benchmark for this spec. It did not catch the
Codex previewer shallowness or SPC/vendor fidelity drift, and it did not judge
Claude's deferred SPC/vendor implementation against the spectroscopy-specific
success criteria.

## Merge Recommendation

Prefer PR #1666 as the implementation base. Do not merge PR #1663 without
fixing the previewer and SPC/vendor format fidelity issues. Before declaring
the spectroscopy package complete, require a follow-up decision for SPC/vendor
binary support: either implement with fixtures/optional dependencies or amend
the capability contract to make those paths explicitly unavailable until later.
