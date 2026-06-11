---
title: "ADR-048 Diff-Only Conformance Review (no-context) — #1577 / #1580 / #1581"
issue: 1589
branch: audit/2026-06-11-codebase-no-context
author: 3 no-context diff-only audit_reviewer agents (one per PR) + manager verification
date: 2026-06-11
status: committed
mode: no-context, diff-only
prs_reviewed: [1577, 1580, 1581]
allowed_inputs_per_agent: ["git diff <base>..<head> (incremental diff only)", "docs/adr/ADR-048.md", "the corresponding spec"]
---

# ADR-048 Diff-Only Conformance Review (no-context) — Track C (2026-06-11)

## 1. What this is

The strictest of the three ADR-048 lenses. Each agent could read **only three
things**: the incremental `git diff <base>..<head>` of one PR, `docs/adr/
ADR-048.md`, and that PR's spec. No PR title/description/comments, no CI, no gate
ledger, no full source at the head ref (only the diff hunks), no other code, no
other audit track. Pure "does this change, as written, conform to the written
contract."

| PR | Spec | Incremental diff |
|---|---|---|
| #1577 SPEC 1 | `adr-048-preview-system.md` | `origin/main..origin/track/adr-048-spec1-preview-system` |
| #1580 SPEC 2 | `adr-048-ai-plot-tools.md` | `…spec1..…spec2-plot-tools` |
| #1581 SPEC 3 | `adr-048-developer-docs-refresh.md` | `…spec2..…spec3-docs` |

The diff-only lens is **rigorous on the exact hunks** (it caught things the other
lenses didn't — see §8) but, by construction, rates "absence" claims as
"not-evidenced-in-diff" and can miss reasoning that needs the whole resolved
system. One such miss is reconciled in §3.

## 2. Verdict summary (as reported by the diff-only agents)

| PR | Diff-only recommendation | Findings |
|---|---|---|
| #1577 SPEC 1 | pass | 4 × P3 |
| #1580 SPEC 2 | pass-with-fixes | 4 × P3 |
| #1581 SPEC 3 | pass-with-fixes | 4 × P3 |

All four agents reported only P3s. **However, the manager's cross-track
reconciliation escalates one #1577 item to P1 (§3).**

## 3. Cross-track reconciliation — the #1577 collection-routing bug (manager: **P1**)

This is the headline result of running three independent lenses.

- **Track B (full context)** rated it **P1** (its F1): for a collection target,
  router tiers 2 & 4 call `_pick(want_collection=False)` unconditionally, so
  `Collection[Image]` with the imaging package installed resolves to
  `imaging.image.viewer` (a single-image previewer) before the core collection
  fallback.
- **Track C (diff-only)** rated the same area only **P3** (its F4): it traced the
  **core** tier-8 item fallback and reasoned `core.collection.basic` (tier 7)
  always wins first — but it **did not flag the package tier-4 item pick that
  runs before tier 7**. Its F3 separately (and correctly) noted that the *legacy*
  REST adapter never builds collection targets — only the session API does.
- **Manager adjudication (verified in code):** Track B is correct. In
  `previewers/router.py::resolve`, for `is_collection`, the order is tier-3
  (PACKAGE, `want_collection=True`, guarded) → **tier-4 (PACKAGE,
  `want_collection=False`, unconditional)** → … → tier-7 (core collection). `_pick`
  filters only on `owner_kind`, `target_type`, and `bool(supports_collection) ==
  want_collection` — **there is no `target.is_collection` guard**. The imaging
  spec is `target_type="Image", supports_collection=False`. So tier-4 returns
  `imaging.image.viewer` for `Collection[Image]`, never reaching tier-7. This is a
  real ADR-048 §3 / FR-003 / US4 contract violation.
- **Why the two lenses diverged — and why it matters:** the bug needs two facts
  to see — the tier ordering (in the diff) *and* that a package registers an
  item-type previewer that lands at tier-4 (also in the diff, but requires
  resolving "what is actually registered" against the tier walk). Track C's
  diff-only discipline traced the tiers but stopped at the core tiers; Track B,
  reasoning over the whole resolved registry, connected the package previewer to
  tier-4.
- **Live reachability today:** mitigated but not removed. The legacy route never
  emits collection targets (Track C F3), and `PreviewHost` — the session-API
  client that *would* request a `collection_ref` — is not mounted on any live UI
  surface yet (Track B F2). So today the bug is reachable via the session API and
  tests, **not** via the live UI. It is a **latent P1**: a genuine router contract
  break that bites the moment the collection preview path goes live.
- **Fix:** gate the item `_pick` calls (tiers 2/4, the parent tiers 5/6 item
  branch, and the core tier-8) on `not is_collection`, so a collection target
  only matches collection-capable previewers before falling to the core
  collection fallback. Add a router test for `Collection[Image]` **with** the
  imaging package present asserting `core.collection.basic`. Fix in #1577.

## 4. PR #1577 — SPEC 1 (diff-only): conforms; 4 × P3

Overall the diff visibly satisfies FR-001..FR-026, FR-028..FR-030 and
SC-001..SC-009 with matching tests; SC-004 (bounded Zarr/TIFF reads) is a genuine
improvement. Diff-only findings:

- **F1 (P3, contract):** the asset route is `/api/previews/assets/{previewer_id}/
  {asset_path}` vs the spec table's `/api/previews/assets/{asset_id}`. The spec
  explicitly permits route-name changes; semantics preserved (per-previewer
  path-confinement). **Accept.**
- **F2 (P3, conformance):** the legacy text-preview branch **dropped its suffix
  allowlist** (`.txt/.json/.yaml/.yml/.md`); `text_chunk` now byte-truncates any
  Text-typed file. Shape stays legacy-compatible (FR-008), but the per-record
  routing decision can differ from pre-ADR behavior. *Diff-only limit: could not
  see the full `test_data.py` to confirm a regression fixture.* Confirm a Text
  record's `kind` still matches frontend expectations.
- **F3 (P3, by design):** collection-kind targets are built only by the session
  API/frontend, never by the legacy `preview_data` adapter — consistent with US4.
  No change. *(This is the reachability fact that feeds §3.)*
- **F4 (P3 → see §3):** router tier-8 core item fallback could mis-route a
  collection if the core collection fallback were ever removed. The manager
  reconciliation in §3 shows the **package tier-4** variant of this is the real
  **P1**.

Diff-only not-evidenced: FR-027/SC-008 (MCP inspection 8 MiB cap) — no MCP file
in this diff (pre-existing or sibling PR); SC-010 (manual ten-image smoke) — not
judgeable from a diff.

## 5. PR #1580 — SPEC 2 (diff-only): conforms; 4 × P3 (incl. a new one)

The diff visibly satisfies all 35 FRs and 10 SCs with strong isolation tests
(FR-025/SC-005) and the PlotPreviewer consumption test (SC-010). No P1/P2.

- **F1 (P3, contract) — new, not seen by the other tracks:** the **R** harness
  `to_dataframe` does **not** clamp `max_rows` to the runtime ceiling. The hunk
  is `cap <- min(as.integer(max_rows), max_rows)` (i.e. `min(x,x)=x`, the caller's
  own value), whereas the Python harness correctly does `cap = min(cap,
  self._max_rows)`. FR-017 bounded conversion is only advisory on the R path; an
  R script passing a huge `max_rows` can over-read rows (byte/file caps still
  hold). Clamp against the injected global cap; add an R-path row-cap test.
- **F2 (P3, contract):** the R harness passes raw `refs` to `render()` and its
  `to_dataframe` ignores the `collection` argument (reads the closure instead).
  Works today via closure, but the documented `collection` arg is inert in R —
  asymmetric with Python. Make R pass a structured collection.
- **F3 (P3, scope/traceability):** `pyproject.toml` adds `matplotlib>=3.8` to
  `[dev]` (justified for SC-006) but `pyproject.toml` is not in the spec's/ADR's
  `governs.files` and is a governance-protected path — declare it. *(Track B's
  ledger note F4 and Track A's governance-touch awareness corroborate this is a
  governance-surface edit.)*
- **F4 (P3, bug):** `validate_plot`'s broken-target check is environment-dependent
  — for an **unregistered** block, discovery emits a single synthetic `output`
  port, so a manifest bound to a real port (e.g. `measurements`) is reported as a
  false "broken target", and one bound to `output` validates as if the port
  existed. Distinguish "plugin not installed" from "port deleted" (downgrade to a
  warning).

## 6. PR #1581 — SPEC 3 (diff-only): conforms; 4 × P3 (incl. a new one)

Faithful delete-and-rewrite; removes `OutputPort.produced_type` everywhere, fixes
the scaffold template, teaches the three entry-point groups, reproduces the
9-tier routing precedence, and adds the impact matrix + a stale-phrase/link guard.

- **F1 (P3, bug) — new, diff-only-specific catch:** `previewers-and-plots.md`
  links to `publishing.md#entry-points`, but the **same PR renames** that heading
  to `## The three entry-point groups` (anchor `#the-three-entry-point-groups`).
  The new `test_relative_links_resolve` strips the `#fragment` and only checks the
  file path, so **CI passes while the anchor is dead** (the link lands at the page
  top). Fix the anchor; optionally extend the test to validate heading anchors.
- **F2 (P3, low):** the imaging-README anchor
  `#package-owned-imagelabel-previewers-adr-048-spec-1` cannot be confirmed from
  the diff (the defining heading is above the changed hunk). Verify it exists.
- **F3 (P3, not-evidenced):** the plot skill / base `SKILL.md` / `cli-integration`
  plot inventory (SC-005/FR-023/FR-024) are **not in this incremental slice** —
  the in-diff CHANGELOG indicates they shipped in the SPEC 2 base branch. Confirm.
- **F4 (P3, scope):** files outside `governs.files` — the two extra skills
  (`build-workflow`, `debug-run`) are **correct** stale-signature fixes required
  by the new docs guard (same as Track B P3-2; accept); the rest are non-shipping
  process artifacts.

## 7. Manager verification

- **#1577 router P1 (§3):** read `router.py::resolve` (tiers 1-9) and `_pick`
  at the head ref. `_pick` filters on `owner_kind` / `target_type` /
  `supports_collection == want_collection` with **no `is_collection` guard**;
  tier-4 (PACKAGE item) precedes tier-7 (core collection). `Collection[Image]` +
  imaging → `imaging.image.viewer`. **Confirmed P1.**
- #1577 F2/F3, #1580 F1-F4, #1581 F1-F4: high-quality, diff-grounded; accepted at
  the agents' stated confidence. #1580 F1 (R clamp) and #1581 F1 (dead anchor) are
  fully visible in the cited hunks.

## 8. What the diff-only lens added

Running the strictest lens was not redundant. Beyond corroborating the other
tracks, Track C surfaced findings **no other lens reported**:

- **#1580 F1** — the R-path `max_rows` clamp gap (Python clamps, R does not). A
  close read of the exact hunk; the full-context lens did not flag it.
- **#1581 F1** — a **dead doc anchor that passes CI** because the link test
  ignores fragments. Classic "the test guards the wrong thing" — only visible by
  diffing the link against the same PR's heading rename.
- **#1577 F2** — the dropped text-suffix allowlist (a silent behavior change).

It also **under-rated the #1577 router bug** (P3 vs the true P1), which is itself
instructive: the diff-only constraint is excellent at "is this hunk correct
against the contract" but weaker at "what does the fully-resolved system do",
where the full-context lens (Track B) won. The two lenses are complementary; the
manager reconciliation in §3 is where they meet.

This review changes **no implementation, source, or test file** — evidence only.
