---
title: "No-Context Audit: Public API Docstring Quality + Cross-Module Consistency (3)"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 52
language_source: en
---

# No-Context Audit: Public API Docstring Quality + Cross-Module Consistency (3)

Date: 2026-06-28
Reviewer persona: audit_reviewer (no current-task context)
Branch / worktree: `audit/1845-3` @ `/Users/jiazhenz/scistudio-wt-1845-audit3`

## 1. Scope Audited

Primary surface (full read): `src/scistudio/previewers/**` public author surface —
`scistudio.previewers.models` (`__all__`, 21 symbols), `scistudio.previewers.data_access`
(`__all__`, 11 symbols), `scistudio.previewers.helpers` (`sanitize_svg`), and the package
`scistudio/previewers/__init__.py` re-export surface.

Cross-module consistency (wide sample): the public docstrings of the nine canonical reference
roots — `scistudio.core.types`, `scistudio.core.meta`, `scistudio.blocks.{base,process,io,app,code}`,
`scistudio.previewers.{models,data_access}` — plus `scistudio.plot` (40 public symbols, not a
canonical root).

Generated reference: `scripts/docs/build_reference.py` + `mkdocs build --strict`, and the built
HTML under `build/mkdocs-site/`.

Judged against: `docs/contributing/docstring-style.md` (the repository standard) and ADR-052's
"nine canonical roots" contract as encoded in the builder.

## 2. Method

- Read the full previewers public surface (`models.py`, `data_access.py`, `helpers.py`,
  `__init__.py`).
- Ran `PYTHONPATH=$PWD/src python scripts/docs/build_reference.py` → exit 0; scanned the log for
  `warning|error|griffe|critical` → none. Strict build is GREEN.
- Verified public attributes/properties actually render by extracting `id="..."` anchors from the
  built HTML (PreviewTarget fields + `is_collection`, PreviewLimits/PreviewMetadata/PreviewerSpec
  fields, FrontendManifest.asset_root, PreviewRequest.storage, `OwnerKind.CORE`,
  `PreviewEnvelope.with_session`, `PreviewDataAccess.max_rows/max_bytes/series_batch_size`,
  ArrayPlane.vmin, DataFramePage.columns, SliceAxis.axis, and `Block.ui_icon`/`Block.ui_color`).
- Confirmed `PreviewDataAccess.png_data_uri` (`@internal`) does NOT leak into the reference.
- AST-scanned every docstring and PEP-224 attribute-docstring across
  `previewers/core.types/core.meta/blocks.*/plot` for internal-record jargon, skipping `@internal`
  scopes.
- Definitive jargon test: stripped tags from the nine built HTML reference pages and scanned the
  visible text for the full jargon family (`ADR-/FR-/DSN-/SC-/TRK-/BUG-/…`, `Addendum N`,
  `Tier 1/2/3`, bare `#NNN`).
- Verified external standards (MIME, `application/octet-stream`, `PNG/JPEG/SVG/PDF`, `data:` URIs)
  and Sphinx roles survive rendering (0 raw unrendered `:class:`/`:meth:` roles in HTML).
- Ran `python -m doctest` on `models.py`, `data_access.py`, `helpers.py`.

## 3. Findings (ordered by severity)

### P1 — must fix before merge

None.

- `build_reference.py` + `mkdocs build --strict` → **exit 0, no griffe/strict warnings** (GREEN).
- Every public attribute/property/ClassVar checked **renders** in the built HTML (anchors present),
  including the previously-dropped block UI metadata (`scistudio.blocks.base.Block.ui_icon`,
  `Block.ui_color`) and the `PreviewDataAccess` instance attributes assigned in `__init__`
  (`max_rows`, `max_bytes`, `series_batch_size`).
- **No internal-record jargon in any rendered public docstring.** The only `ADR-052` token in the
  rendered reference is the generator's own page chrome (see P3-2), never a symbol docstring.
- `PreviewDataAccess.png_data_uri` (`@internal`) correctly excluded from the reference.
- All doctests pass: `models.py` 17/17, `data_access.py` 1/1, `helpers.py` 2/2.

### P2 — should fix (author-facing reference gap; not blocking)

**P2-1. `sanitize_svg` is advertised as a canonical author root but is absent from the generated
reference.**
The module docstrings tell authors to import it from a canonical root:
- `src/scistudio/previewers/__init__.py:14-16` — lists `scistudio.previewers.helpers`
  (`sanitize_svg`) as a canonical author root.
- `src/scistudio/previewers/models.py:6-8` — "the others are
  `scistudio.previewers.data_access` … and `scistudio.previewers.helpers` (`sanitize_svg`)."
- `src/scistudio/previewers/helpers.py:40` — `sanitize_svg` is `@provisional(since="0.3.1")` and in
  `helpers.__all__`, i.e. public surface by the standard's own §1 definition.

But `scripts/docs/build_reference.py:60-70` `CANONICAL_ROOTS` does **not** include
`scistudio.previewers.helpers`. Evidence: `grep -rl sanitize_svg docs/user/reference/
build/mkdocs-site/*.html` → no match. A bench scientist who follows the docstring guidance
("import `sanitize_svg` from `scistudio.previewers.helpers`") will not find the symbol anywhere in
the published API reference.
Fix options: (a) add `scistudio.previewers.helpers` as a tenth rendered root, or (b) stop calling
helpers a "canonical author root" in the two module docstrings if it is intentionally outside the
nine-root freeze. Pick one so the docstrings and the reference agree. This is the same definition
gap called out in the standard verdict (§4) and is shared by all of `scistudio.plot.*` (40
`__all__` symbols, also a non-rendered public surface).

### P3 — consistency nits (optional polish)

**P3-1. Uneven `Example:` coverage between sibling result dataclasses and the rest of the surface.**
- `scistudio.core.types`: all 10 public classes carry runnable examples (highest bar).
- `scistudio.previewers.models`: all 9 author-*constructed* frozen dataclasses + the
  `PreviewerEntryPoint` protocol carry examples (enums and the simple error classes reasonably omit
  them).
- `scistudio.previewers.data_access`: **only** `PreviewDataAccess` has an example; all ten result
  dataclasses — `DataFramePage` (`data_access.py:50`), `SliceAxis` (79), `ArrayPlane` (99),
  `ArrayTile` (146), `SeriesPoints` (167), `TableXYPoints` (186), `TextChunk` (207), `ArtifactInfo`
  (223), `CompositeSlots` (243), `CollectionSample` (252) — have none.

Defensible (these are read-only return values, fully documented by attribute docstrings and by the
`Returns:` of their producing method), so I do not call it a defect — but it is uneven depth versus
core.types' bar and the standard's "almost always for classes" (`docstring-style.md` §2.2 item 4).
If kept, a one-line note in the standard ("read-only result containers documented by attribute
docstrings may omit examples") would make the asymmetry intentional rather than incidental.

**P3-2. The generated reference page chrome itself cites internal records in user-facing prose.**
The de-jargon work is complete for docstrings, but the generator's own page text — which users read
on the same pages — cites `ADR-052`:
- `scripts/docs/build_reference.py:178-179` — every per-root page intro: "… read from the
  `scistudio.stability` decorators (ADR-052 §5/§7)."
- `scripts/docs/build_reference.py:127` — the unmarked-symbol badge: "Stability: unmarked — see the
  module docstring / ADR-052 for this constant or type-alias."
- Index page (`_render_index`): "(ADR-052 §7; … `mike` … #1817)".

This is generator template text, not a docstring, so it is outside the standard's literal scope, but
it contradicts `docstring-style.md` §2.1 ("a docstring **and any prose a user reads** MUST NOT cite
an internal project record"). Recommend scrubbing the reader-facing chrome (move the ADR/issue
provenance into the HTML comment banner that already exists) for consistency with the principle the
standard enforces everywhere else.

**P3-3. `PreviewerSpecList` is in the reference but not in the package convenience re-export.**
`PreviewerSpecList` is in `models.__all__` (`models.py:890`) and renders in the reference, but it is
the one public `models` symbol not re-exported from `scistudio/previewers/__init__.py:156-178`
`__all__`, whose docstring says it re-exports "the public author surface … for convenience." Likely
intentional (niche type alias), but it is an uneven convenience set; either add it or note the
omission.

**P3-4. Informational (NOT a defect): internal docstrings consistently retain ADR/FR citations.**
`@internal` symbols keep their record citations — e.g. `build_preview_service` (`__init__.py:108`,
"FR-001/FR-002/FR-030"), `PreviewSession` (`models.py:633`, "FR-007"), the runtime-raised error
classes (`models.py:805-861`, "ADR-052 §8.1 …"), and `PreviewDataAccess.png_data_uri`
(`data_access.py:873`). This is exactly what the standard prescribes (`internal`/`_`-prefixed
members are out of scope, §2.3 scope note) and is applied consistently across modules. Recorded so a
future reader does not mistake it for a miss.

## 4. Verdict On The Standard Document (`docs/contributing/docstring-style.md`)

Adequate and usable — clear two-rule framing, a strong before/after worked example, a correct
explanation of why a `#` comment is not a renderable docstring, and the verified `ui_icon` attribute
-docstring pattern. The attribute/property rule (§2.3) provably works: every public attribute I
checked renders. One notable inaccuracy and two small gaps:

1. **Inaccurate scope claim (§1).** "Public surface … the published API reference renders these"
   equates `__all__`/`@stable`/`@provisional` membership with "rendered in the reference." The
   reference renders only the nine canonical roots, so `@provisional` public symbols outside those
   roots — `sanitize_svg` and all of `scistudio.plot.*` — are public-surface by this definition yet
   are **not** rendered. The standard should distinguish "public surface" from "rendered canonical
   roots," which would also surface P2-1.
2. **Silent on module-level constants/type-aliases.** §2.3 covers class/instance attributes and
   properties but not public module-level constants and `Literal`/`Callable`/`list[...]` aliases
   (`PREVIEWER_API_VERSION`, `PreviewProvider`, `PreviewerSpecList`, `CapabilityDirection`,
   `MetadataFidelityLevel`, `InterpreterFamily`). In practice these all carry PEP-224 attribute
   docstrings and render (verified), but the standard never tells authors to write them or that they
   render "unmarked." A short subsection would close the gap.
3. **Silent on examples for read-only result dataclasses** (drives P3-1).

## 5. Overall Recommendation

**pass-with-fixes.**

Nothing blocks merge: the strict reference build is green, every public attribute/property renders,
no rendered public docstring contains internal-record jargon, external standards and Sphinx roles
survive rendering, and all previewer doctests pass. Recommend addressing P2-1 (helpers/`plot`
reference-coverage gap) and the §1 wording of the standard as near-term follow-ups; P3 items are
optional polish.
