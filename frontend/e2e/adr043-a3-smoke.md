# ADR-043 Phase A3 — Smoke Test Evidence

Per the dispatch prompt T-024 and `.claude/rules/frontend-smoke-test.md`,
the Phase A3 UI changes need a smoke verification before report-done.

Chrome MCP and Playwright are not provisioned in this repo (the existing
e2e harness under `tests/e2e/adr-035/` is fixture-generation only), so
this smoke verification combines:

1. **Automated JSDOM smoke** — `frontend/src/__tests__/adr043-a3-smoke.test.tsx`
   exercises the three new UI surfaces end-to-end through their real
   integration points (CapabilityDropdown ambiguity + persistence, OME
   panel open / copy / hide-when-empty, LossySaveWarning drop list +
   truncation). Run via `npm test`.

2. **Manual in-app browser checklist** below — execute against a local
   `vite preview` (NOT `vite dev`; see "stale dev server hygiene" rule).
   The owner runs this when the umbrella branch lands; the agent's
   per-PR smoke evidence is the JSDOM run.

The automated smoke also passes when run in isolation:

```
$ cd frontend
$ npx vitest run src/__tests__/adr043-a3-smoke.test.tsx
 ✓ src/__tests__/adr043-a3-smoke.test.tsx (6 tests) 62ms
   Test Files  1 passed (1)
        Tests  6 passed (6)
```

---

## Manual in-app browser checklist (owner-run)

Pre-reqs:

- Backend running with ADR-043 capabilities registered. Until A1/A2 ship,
  this will only surface for the LCMS/imaging pilot capabilities already
  registered per PR #1213 (see `imaging.image.tiff.save`,
  `imaging.image.tiff.load`).
- `cd frontend && npm run build && npm run preview` (NOT `npm run dev` —
  per stale dev-server hygiene).
- Open Chrome to the printed preview URL.

### 1. Capability dropdown (FR-012)

1. Drag a `SaveImage` (or other IO save) block onto the canvas.
2. Open the bottom-panel port editor for an output port.
3. Set `extension = "tif"` (or any extension with >1 capability).
4. **Expect:** a "Capability" row appears below the port row with a
   dropdown listing every matching capability. Each option reads
   `<label> — <format_id> [<fidelity>]`. Selecting one persists the
   `capability_id` on the port row (check via `Save Workflow` →
   inspect the YAML — `capability_id` is present).
5. **Expect:** when only one capability matches, the dropdown auto-selects
   it and disables the select (the badge still renders).

### 2. OME metadata panel (FR-013)

1. Run a workflow that produces an `Image` output with populated OME (any
   `LoadImage` from imaging package; until A2 lands, use a fixture with
   `meta.ome` populated by hand).
2. Select the producing block on the canvas.
3. **Expect:** the `Preview` side panel shows an "OME metadata" button.
4. Click the button.
5. **Expect:** the panel opens, the spec-named subtrees (`images`,
   `pixels`, `channels`, `annotations`) are listed at the top, and
   clicking a leaf's `Copy` button writes the value to the system
   clipboard.
6. Click `×` to close the panel.

### 3. Lossy-save warning (FR-014)

1. Build a graph `LoadImage(.czi) → SaveImage(.png)` (until A2 lands the
   `.czi` loader is mocked, but a `.tif → .png` graph using the existing
   pilot also surfaces the warning).
2. **Expect:** the SaveImage node footer shows an amber chip:
   `⚠ Lossy save: pixels.physical_size_x, channels.0.name, ... +N more`.
3. Click `+N more`.
4. **Expect:** the chip expands to list every dropped OME field with a
   `collapse` button.
5. Change the SaveImage capability to `imaging.image.ome-tiff.save`
   (lossless).
6. **Expect:** the chip disappears.

---

## Automated smoke output (committed evidence)

The JSDOM smoke run from this branch's `feat/issue-1296/adr043-a3-frontend`
HEAD:

```
$ npx vitest run src/__tests__/adr043-a3-smoke.test.tsx \
  src/__tests__/CapabilityDropdown.test.tsx \
  src/__tests__/OMEMetadataPanel.test.tsx \
  src/__tests__/LossySaveWarning.test.tsx

 ✓ src/__tests__/LossySaveWarning.test.tsx (11 tests)
 ✓ src/__tests__/OMEMetadataPanel.test.tsx  (13 tests)
 ✓ src/__tests__/CapabilityDropdown.test.tsx (6 tests)
 ✓ src/__tests__/adr043-a3-smoke.test.tsx   (6 tests)

  Test Files  4 passed (4)
        Tests  36 passed (36)
```

Full project test run (sanity check that integration into
`PortEditorTable`, `DataPreview`, `WorkflowCanvas`, and `BlockNode` does
not regress existing tests):

```
$ npm test
  Test Files  41 passed (41)
        Tests  405 passed | 13 skipped (418)
```

TypeScript build:

```
$ npm run build
  ✓ 2086 modules transformed.
  ✓ built in 17.77s
```
