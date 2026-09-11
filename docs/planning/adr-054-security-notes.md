---
title: "ADR-054 Phase A Read And Security Implementation"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: [48, 54, 55]
related_specs: [adr-054-panels, adr-055-identity-seam, adr-055-prefix-independence]
language_source: en
---

# ADR-054 Phase A Read And Security Implementation

Implementation slice A3 under #2293 and manager umbrella #2353. The current
sidebar entry is preserved in A; MiniApps/All Previewers navigation belongs to D.
The governing design is ADR-054 and its existing panel spec, coordinated with
ADR-055 identity and prefix contracts; this slice introduces no Lab middleware.

## Read Contract And Budgets

`PreviewDataAccess` preserves complete legacy series reads by default. Optional
`max_points` selects uniformly spaced source indices including both endpoints
when the budget exceeds one point. The cap is 16384 points and the configured
byte budget divided by 16 bytes per x/y float64 pair. Bounded reads cap
Parquet batches at the smaller of 4096 rows, the legacy batch hint and the byte
budget divided by 16. Panel series calls default
to 4096 points. Invalid/nonfinite rows are counted over the full source using
bounded Parquet batches and omitted from plotted values. The method is named
`uniform-index` rather than claiming peak preservation.

Text windows use UTF-8 byte offsets and consume at most the lower of the requested
length, text budget (default 5000 bytes), and byte budget (default 8 MiB). A split
trailing code point remains for the next window. A requested window too short to
hold the next code point fails rather than looping forever or corrupting text.
`next_offset` is null at EOF. Collection pages cap at 100 items by default; cursors
carry version, inventory count and offset, and malformed/stale counts are refused.
The context service must bind cursor use to its authorized frozen inventory.
Legacy partial collection samples remain accepted without paginated options.

Internal `panel_array_plane`, `panel_array_tile`, `panel_table_xy`, and `panel_series_points` return
`NumericRead`: a dtype-preserving ndarray, `metadata`, `to_bytes()` and `to_json()`.
Metadata carries returned `dtype`/`shape`, source array shape/dtype, axes and slice
axes where applicable, and `sampled`, `truncated`, `complete`. JSON replaces only
nonfinite floats with null; binary retains IEEE nonfinite values and original
numeric dtype in little-endian, contiguous row-major bytes. Series are Nx2 x/y
float64 pairs. A plane is at most 256 by 256 by default (also byte-budget bounded),
and full-plane extrema are scanned separately in bounded tiles; an unsampled
extreme must still affect vmin/vmax. Tiles are sliced directly from storage and
cap at 256 by 256 by default. Oversized tile byte requests fail before reading.

`artifact_file(ref)` resolves a regular file without reading its payload and has
no inline-size cap. The caller must authorize the reference first and expose only
a context-bound token URL. The artifact grant implementation belongs to A1.

## Security And Enterprise Composition

`RefuseOpaqueOriginMiddleware` rejects all HTTP POST/PUT/PATCH/DELETE carrying any
`Origin: null` header, including duplicate-header cases, before CORS and the
identity guard run. Ordinary same-origin and absent-Origin requests retain their
behavior. It does not change WebSockets, GET, HEAD or OPTIONS.

Startup refuses wildcard and null entries anywhere in `SCISTUDIO_CORS_ORIGINS`
and names the setting in its error. `PanelCORSMiddleware` delegates only the
literal `/api/panels/t/` subtree (after root-path removal) to A1's token routes.
Those routes authenticate GET/OPTIONS themselves before returning noncredentialed
CORS headers; this avoids global CORS rejecting opaque-origin module preflights
before token validation. Sibling/lookalike paths retain normal explicit CORS.

The agreed A1 installation API is `routes.panels.install_panels(app)` and async
`panels_lifespan(app)`. The installer belongs beside the existing preview routes;
the lifespan belongs inside the existing AsyncExitStack, before edition hooks,
so panel cleanup follows edition cleanup and precedes core teardown. Integration
must preserve enterprise PR #2336's lifecycle and capability changes hunk by hunk.

## Public Surface And Verification

Public additions affect `PreviewDataAccess.series_points`, `text_chunk`,
`collection_sample`, `artifact_file`, and result dataclasses `SeriesPoints`,
`TextChunk`, `CollectionSample`. New fields are appended to preserve positional
construction. The panel transport methods are marked internal. Manager owns the
ADR-052 snapshot and generated reference refresh after integration; no generated
files or owner-controlled architecture documents are edited here.

Tests cover storage-index assertions, full-plane extrema missed by the sample,
nonfinite JSON/binary parity, big-endian conversion, named-axis transposition,
empty/scalar/vector arrays, byte limits, decimation and legacy defaults, UTF-8
pagination, collection cursor boundaries, large artifact access, and root/prefixed
security with the default and test-only replacement guard plus edition routes.
Real JupyterHub behavior is not claimed by the fake-guard contract.

## Local Evidence

- Targeted read/security suite: 50 tests passed with `pytest --no-cov`; this is
  focused regression evidence, not a claim to the repository-wide coverage floor.
- App/identity/root-path plus initial read/security tests: 210 tests passed.
- Ruff check/format and `git diff --check`: passed on the changed Python files.
- Gate-selected full checks and A1 installer/lifespan integration are pending;
  final PR validation and CI belong to the manager's integrated candidate.
