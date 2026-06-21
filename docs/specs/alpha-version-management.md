---
spec_id: alpha-version-management
title: "Alpha Version Management: Single Source, Local Build Counter, Dual-Track Format"
status: Planned
feature_branch: guided/live-round5-20260621
created: 2026-06-21
input: "Issue #1742 — stable automated version management for alpha. Display a.b.c-alpha|beta-build<NNNN>, auto-increment by build, local build counter, PEP 440-compliant Python side. Owner-directed guided session 2026-06-21; bundled with logging (#1741) into one PR."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - alpha-observability-logging
scope:
  in:
    - A single source of truth for the base version and release channel.
    - A version deriver producing PEP 440 (Python), SemVer (npm/electron), and a human display string from base + channel + build.
    - A local persistent build counter that auto-increments per build and resets to zero on channel change.
    - A version CLI (scripts/version.py) with show / bump / set-channel / sync.
    - Runtime exposure of the version via CLI --version and a /version API field, plus FastAPI app version.
    - Synchronizing all manifests (pyproject, __init__, package.json x2) from the single source, eliminating the current drift.
  out:
    - GitHub releases / tag automation (local build only for now, per owner).
    - Per-plugin version unification (packages/* keep independent versions).
    - Auto-update feeds / channel switching UI.
governs:
  modules:
    - scistudio.version
  contracts:
    - scistudio.version.get_version
  entry_points: []
  files:
    - docs/specs/alpha-version-management.md
    - src/scistudio/_version.py
    - src/scistudio/version.py
    - src/scistudio/__init__.py
    - src/scistudio/api/app.py
    - src/scistudio/cli/main.py
    - scripts/version.py
    - pyproject.toml
    - desktop/package.json
    - frontend/package.json
    - .gitignore
  excludes: []
tests:
  - tests/test_version.py
acceptance_source: issue
language_source: en
---

# Alpha Version Management: Single Source, Local Build Counter, Dual-Track Format

## 1. Change Summary

From issue #1742. The version number has **no single source of truth and has
already drifted**: `pyproject.toml` says `0.2.1`, `src/scistudio/__init__.py` says
`0.1.0-dev`, `api/app.py` hardcodes `0.1.0`, and both `package.json` files say
`0.1.0`. There is no build-number concept, no bump tooling wired (setuptools-scm
is present but unconfigured; commitizen only lints commits), and no runtime way to
read the version (`--version`, `/version` both absent).

This spec defines a **single-source, dual-track** version system for alpha. One
source of truth holds the base `a.b.c` and the channel (`alpha`/`beta`/`stable`);
a **local persistent build counter** auto-increments per build and **resets to
zero on channel change**. A deriver produces three formats from `base + channel +
build`: a human **display** string `a.b.c-alpha-build<NNNN>`, a **PEP 440** string
`a.b.ca<N>` for Python packaging, and a **SemVer** string for npm/electron. A
`scripts/version.py` CLI shows / bumps / switches channel / syncs all manifests,
eliminating drift. The version is exposed at runtime via `scistudio --version` and
a `/version` field so bug reports can state the exact build.

## 2. User Scenarios & Testing

### User Story 1 - Deterministic, drift-free version everywhere (Priority: P1)

A developer runs `python scripts/version.py sync`; afterwards pyproject, the
package `__version__`, and both `package.json` files report the same version,
derived from the single source.

**Why this priority**: Drift is the core defect; a single source that syncs all
manifests is the minimum viable fix.

**Independent Test**: Change base/channel in the source, run `sync`, assert every
manifest matches the derived value for its track.

**Acceptance Scenarios**:
1. **Given** the single source, **When** `get_version()` is called, **Then** it
   returns consistent base, channel, build, PEP 440, SemVer, and display values.
2. **Given** `sync`, **When** it runs, **Then** pyproject (PEP 440) and both
   package.json (SemVer) are rewritten to match the derived version.

### User Story 2 - Build number auto-increments locally, resets on channel (Priority: P1)

Each local build bumps the build number; switching alpha→beta resets it to zero.

**Why this priority**: This is the owner's explicit versioning requirement.

**Independent Test**: `bump` twice → build 1 then 2; `set-channel beta` → build 0.

**Acceptance Scenarios**:
1. **Given** channel alpha at build N, **When** `bump` runs, **Then** the local
   counter becomes N+1 and the derived build reflects it.
2. **Given** channel alpha, **When** `set-channel beta` runs, **Then** the beta
   build number starts at 0.

### User Story 3 - Read the version at runtime for bug reports (Priority: P2)

A tester runs `scistudio --version` or the app reads `/version` to include the
exact build in a report.

**Why this priority**: Useful for support, but depends on US1/US2.

**Independent Test**: `scistudio --version` prints the display string; `/version`
returns the structured version.

**Acceptance Scenarios**:
1. **Given** the CLI, **When** `--version` is passed, **Then** the display string
   is printed and the process exits 0.
2. **Given** the API, **When** `/version` is requested, **Then** a JSON body with
   base/channel/build/pep440/semver/display is returned.

### Edge Cases

- No local counter file (fresh checkout / installed wheel) → build defaults to 0,
  or `SCISTUDIO_BUILD_NUMBER` env override if set.
- PEP 440 compliance: display `0.2.1-alpha-build0007` is NOT valid PEP 440; the
  Python track MUST emit `0.2.1a7`. npm/electron use the SemVer display form.
- `set-channel stable` → no pre-release suffix (`a.b.c`).

## 3. Requirements

### Functional Requirements

- **FR-001**: A single source (`src/scistudio/_version.py`) MUST define the base
  `a.b.c` and the channel (`alpha`/`beta`/`stable`); no other file may hardcode an
  independent version after sync.
- **FR-002**: `scistudio.version.get_version()` MUST derive base, channel, build,
  and the PEP 440 / SemVer / display strings from base + channel + build.
- **FR-003**: The build number MUST come from a local persistent counter, with an
  `SCISTUDIO_BUILD_NUMBER` env override, defaulting to 0 when neither is present.
- **FR-004**: PEP 440 mapping MUST be: alpha→`a.b.ca<N>`, beta→`a.b.cb<N>`,
  stable→`a.b.c`. The display form MUST be `a.b.c-<channel>-build<NNNN>` for
  prereleases and `a.b.c` for stable. SemVer MUST equal the display form.
- **FR-005**: `scripts/version.py` MUST support `show`, `bump` (counter+1),
  `set-channel <c>` (reset counter to 0 for the new channel), and `sync` (rewrite
  all manifests from the derived version).
- **FR-006**: `bump` MUST increment the current channel's counter; channel change
  MUST start the new channel's counter at 0.
- **FR-007**: `sync` MUST rewrite `pyproject.toml` (PEP 440), the commitizen
  version, both `package.json` files (SemVer), keeping `scistudio.__version__`
  derived at runtime.
- **FR-008**: `scistudio --version` MUST print the display string and exit 0.
- **FR-009**: The API MUST expose the structured version at `/version`, and the
  FastAPI app `version` MUST equal the derived PEP 440 value.
- **FR-010**: The local counter file MUST be gitignored so builds do not pollute
  history.

### Key Entities

- **VersionInfo**: `{base, channel, build, pep440, semver, display}`.
- **BuildCounter**: gitignored JSON `{ "<channel>": <int> }`.

## 4. Implementation Plan

### 4.1 Technical Approach

`src/scistudio/_version.py` holds `BASE_VERSION` and `CHANNEL`. A new
`scistudio.version` module derives `VersionInfo` from base + channel + build,
reading the build from `SCISTUDIO_BUILD_NUMBER` or the local counter file
(`.build-counter.json`, gitignored), defaulting to 0. `scistudio.__init__` exposes
`__version__` from the deriver (PEP 440), replacing the hardcoded `0.1.0-dev`.
`scripts/version.py` provides the CLI. The API exposes `/version` (in the
diagnostics router from #1741) and sets the FastAPI `version`. The CLI adds a
`--version` callback.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/_version.py` | create | Single source: base + channel |
| `src/scistudio/version.py` | create | Deriver: VersionInfo + format helpers |
| `src/scistudio/__init__.py` | modify | `__version__` derived (was hardcoded) |
| `scripts/version.py` | create | show / bump / set-channel / sync |
| `src/scistudio/api/app.py` | modify | FastAPI `version` from deriver |
| `src/scistudio/cli/main.py` | modify | `--version` callback |
| `pyproject.toml` | modify | Sync version + commitizen version to base |
| `desktop/package.json` | modify | Sync SemVer |
| `frontend/package.json` | modify | Sync SemVer |
| `.gitignore` | modify | Ignore `.build-counter.json` |

### 4.3 Implementation Sequence

1. `_version.py` + `version.py` deriver + `__init__` wiring + tests.
2. `scripts/version.py` CLI (show/bump/set-channel/sync).
3. Runtime exposure: `--version`, `/version`, FastAPI version.
4. Sync all manifests + gitignore the counter.

### 4.4 Verification Plan

- Unit tests: deriver formats (alpha/beta/stable, build numbers), PEP 440 vs
  display vs SemVer, counter increment + channel reset, env override.
- Manual: `python scripts/version.py show|bump|set-channel|sync`; `scistudio
  --version`; `GET /version`.
- `gate_record check --mode pre-pr`.

### 4.5 Risks And Rollback

- **PEP 440 validity**: deriver unit-tested against `packaging.version.Version`.
- **Manifest rewrite correctness**: `sync` is idempotent and tested.
- **Base version choice**: base set to the current highest (`0.2.1`) to avoid a
  version regression; owner may adjust.
- **Rollback**: additive; manifests can be hand-reset; counter is local-only.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: `get_version()` returns a PEP 440 string accepted by
  `packaging.version.Version` for alpha, beta, and stable channels.
- **SC-002**: After `sync`, pyproject and both package.json report the derived
  version for their track with no drift.
- **SC-003**: `bump` increments the build; `set-channel` resets it to 0.
- **SC-004**: `scistudio --version` prints the display string; `/version` returns
  the structured version.

## 6. Assumptions

- Owner-approved single combined PR with logging (#1741) (source: owner).
- Local build counter is the build-number source (no GitHub release) (source: owner).
- Build number resets to zero on channel change (source: owner).
- Base version starts at the current highest committed value `0.2.1` (source: inferred).
