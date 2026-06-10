# Port-compat conformance fixture (#1548 / DSN-9)

`portCompat.ts` (and `computeEffectivePorts.ts`) hand-mirror the backend
`scistudio.blocks.base.ports.validate_connection` and the ADR-028 type
hierarchy. Audit finding **DSN-9** (#1513 / PR #1514) flagged that the two
independent implementations of subtype-walking + port-override logic had
**no shared test fixture**, so they could silently drift.

## What pins the behaviour

- **Oracle:** `portcompat.oracle.json` — a committed golden snapshot of
  the backend contract. Each case is a pair of source/target
  accepted-type lists plus the `expected_compatible` verdict produced by
  the **real** backend `validate_connection`. It also carries the
  `type_hierarchy` (name -> base_type) the frontend needs to walk
  subtype chains.

- **Frontend consumer:** `../portCompat.conformance.test.ts` (vitest)
  runs `arePortTypesCompatible` against every oracle case and fails if
  the frontend disagrees with the backend snapshot.

## Where the oracle comes from

`generate_portcompat_oracle.py` is the single source of truth. It imports
the canonical backend `validate_connection` directly from `<repo>/src`
(no install needed), builds a deterministic type hierarchy from the core
`TypeRegistry.scan_builtins` plus a few synthetic subtypes that exercise
multi-level subtype walking (standing in for plugin types like
`Image -> Array`, `PeakTable -> DataFrame`), and writes the JSON.

Optional monorepo / entry-point plugin types are intentionally **not**
pulled in — they require extra third-party deps (e.g. `ome_types`) and
would make the oracle non-deterministic across environments.

## Regenerating after a backend change

```bash
python3 frontend/src/utils/__fixtures__/generate_portcompat_oracle.py
cd frontend && npx vitest run src/utils/portCompat.conformance.test.ts
```

If `validate_connection` or the core type hierarchy changes, regenerate
the JSON and re-run the conformance test. A drift between
`portCompat.ts` and the backend now surfaces as a failing vitest case
instead of a silent runtime mismatch.
