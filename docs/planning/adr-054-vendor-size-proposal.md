---
title: "ADR-054 Pinned Library Size Exception Proposal"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [54]
language_source: en
---

# ADR-054 Pinned Library Size Exception Proposal

Phase A (#2293) requires offline, versioned Plotly and PDF.js distributions.
Two upstream minified distributions exceed the existing 1000 KiB added-file
limit. The proposal below is pending owner authorization; it has not changed
the repository hook configuration.

| Fixed distribution path under `src/scistudio/panels/lib/` | Upstream bytes | License |
|---|---:|---|
| `plotly@2.35.3/dist/plotly.min.js` | 4558732 | MIT |
| `pdfjs@5.4.149/build/pdf.worker.min.mjs` | 1039207 | Apache-2.0 |

The library index records the package archive integrity, upstream SHA-256,
shipped SHA-256, and repository whitespace/final-newline normalization.
The frontend library test verifies every shipped file against the index.
The complete pinned distributions support the Phase B plot and PDF viewers.

## Proposed Configuration Change

Apply only after explicit owner approval of these two fixed paths:

```diff
       - id: check-added-large-files
         args: ["--maxkb=1000"]
+        # ADR-054: reviewed pinned offline browser distributions (#2293).
+        exclude: >-
+          ^src/scistudio/panels/lib/(plotly@2\.35\.3/dist/plotly\.min\.js|pdfjs@5\.4\.149/build/pdf\.worker\.min\.mjs)$
         stages: [manual]
```

The size threshold and all other hygiene hooks retain their existing settings.
A version upgrade falls outside these anchored paths and requires a new review.
No splitting, encoding, or generated reconstruction is proposed to evade the
size rule.

## Verification Before Landing

- Reproduce the current hook result with the files represented as staged
  additions in an isolated temporary index; preserve the real index and HEAD.
- After approval, verify the exact two paths match the exception and nearby
  paths or other versions do not.
- Run library digest tests, wheel asset checks, and the normal gate hygiene
  check on the integrated candidate.

An ordinary hook run after a file was already committed is not recorded as
evidence that its initial addition met the size limit.
