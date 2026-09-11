---
spec_id: adr-055-identity-seam
title: "ADR-055 Identity Seam — Composing An Edition On The Open-Source Backend"
status: Draft
feature_branch: feat/2304-identity-seam
created: 2026-09-11
input: "Owner decisions of 2026-09-11 on issue #2304 (option B). The open-source edition keeps its present behavior: scistudio serve binds all interfaces and asks for no login. Multi-user Lab deployment moves to a private enterprise edition, scistudio-enterprise, with its own launch command; it builds the standard backend through scistudio.api.app.create_app and adds its own guard, routes, MCP tools and background tasks, and nothing is loaded automatically. The open-source side guarantees a replacement guard, a startup/background lifespan hook, a self-authenticating path registry that every guard honors on the route path after root-path handling, a capability declaration read by a typed frontend accessor (all off by default, no UI), and a test-only fake guard with a reusable contract suite; everything the enterprise edition relies on is declared provisional public API under ADR-052."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 52
  - 54
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
  - adr-052-public-api-surface
  - adr-054-panels
scope:
  in:
    - "`create_app` keyword arguments for a replacement guard, lifespan hooks, a capability declaration, and an edition's routers; the no-argument call builds the backend exactly as before."
    - "One guard slot in the middleware stack, filled by the WebMCP bridge's loopback token middleware by default or by a replacement guard, with the self-authenticating bypass enforced around whichever guard is installed."
    - "The self-authenticating path registry (`scistudio.api.seam`), matched on the route path after root-path prefix handling, and the per-mount panel token exception it carries for ADR-054."
    - "The capability declaration (`identity`, `transfer`), delivered through the served page bootstrap and read by `frontend/src/lib/capabilities.ts`; no UI components."
    - "The runs-active read accessor `workflow_runs_active`."
    - "The ADR-052 declaration of the enterprise edition's dependencies: new canonical roots `scistudio.api.app` and `scistudio.api.seam`, provisional since 0.3.5, with the shared MCP registry and `AUDIENCE_EXTERNAL_TAG` republished there."
    - "A test-only fake guard and a reusable guard contract suite, parametrized over a guard case and run at the root mount and under a mount prefix."
  out:
    - "Everything inside the enterprise edition: the Hub OAuth guard, session cookies and their SameSite/XSRF rules, transfer routes and tools, Hub activity reporting, startup validation of prefix and callback, deployment assets, and the operator runbook."
    - "Multi-user login in the open-source edition; it keeps its present behavior."
    - "The capability-gated UI components (signed-in user and Logout, upload picker with transfer progress, download/save flow); tracked by #2304 until their own issue exists."
    - "ADR-054 panel routes and their registration of `/api/panels/t/`; that lands when panels resume (#2288)."
    - "Removal of the original Lab deployment spec (Spec 4) from this repository, which #2303 does; the open-source changes for the enterprise edition are collected in `adr-055-enterprise-support` (PR #2310)."
governs:
  modules:
    - scistudio.api.seam
    - scistudio.api.app
  contracts:
    - scistudio.api.app.create_app
    - scistudio.api.seam.GuardFactory
    - scistudio.api.seam.GuardContext
    - scistudio.api.seam.LifespanHook
    - scistudio.api.seam.Capabilities
    - scistudio.api.seam.IdentityCapability
    - scistudio.api.seam.register_self_authenticating_prefix
    - scistudio.api.seam.unregister_self_authenticating_prefix
    - scistudio.api.seam.self_authenticating_prefixes
    - scistudio.api.seam.is_self_authenticating_path
    - scistudio.api.seam.workflow_runs_active
  entry_points: []
  files:
    - docs/specs/adr-055-identity-seam.md
    - src/scistudio/api/seam.py
    - src/scistudio/api/app.py
    - src/scistudio/api/spa.py
    - src/scistudio/api/routes/webmcp.py
    - frontend/src/lib/capabilities.ts
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/api/test_identity_seam.py
  - tests/api/seam_contract.py
  - tests/api/fake_guard.py
  - tests/api/test_public_surface.py
  - frontend/src/lib/capabilities.test.ts
acceptance_source: adr
language_source: en
---

# ADR-055 Identity Seam — Composing An Edition On The Open-Source Backend

## 1. Change Summary

This spec comes from ADR-055 section 8 and issue #2304.

The open-source edition is a single-user program. `scistudio serve` binds every
interface, and nothing asks the user to log in; the WebMCP bridge's loopback
token is the only authentication, and it covers `/api/webmcp/*` alone. On
2026-09-11 the owner decided that this stays as it is. Multi-user Lab
deployment, with JupyterHub login and one backend per user, is provided by a
separate private package, `scistudio-enterprise`.

The owner chose how the two meet (option B). The enterprise edition has its
own launch command, for example `scistudio-enterprise serve --hub`, which the
Hub spawner runs. That command builds the standard SciStudio backend through
the open-source factory `scistudio.api.app.create_app`, then adds its own
guard, its transfer routes, its MCP tools, and its background tasks. Nothing
is discovered or loaded automatically: an earlier design had the open-source
`serve` load identity backends from an entry-point group, and option B
replaced it. The trade-off was accepted explicitly. The enterprise edition
depends on open-source internals, the factory and the shared MCP registry, so a
change to them can need a matching enterprise change. Section 3.6 makes those
dependencies visible by declaring them provisional public API.

The open-source side therefore guarantees a seam rather than a deployment:

1. **A replacement guard** (`create_app(guard=...)`). Today `app.py` always
   installs `WebMCPSessionMiddleware` with the loopback token backend, scoped to
   `/api/webmcp/*`. A replacement guard takes that slot and decides for itself
   which paths it protects. The enterprise Hub guard protects everything,
   `/ws` included.
2. **A startup and background hook** (`create_app(lifespan_hooks=...)`). The
   enterprise edition validates its prefix and OAuth callback at spawn and
   reports activity to the Hub while work is running; both live inside the
   application lifespan, with orderly teardown.
3. **A self-authenticating path registry.** An open-source module registers the
   route-path prefixes whose routes authenticate every request themselves.
   Every guard, the default one and any replacement, lets those requests
   through to the route. ADR-054's per-mount panel tokens under
   `/api/panels/t/` are the first user (Section 3.5).
4. **A capability declaration** (`create_app(capabilities=...)`). The backend
   tells the frontend at boot which enterprise capabilities are on: `identity`
   (the signed-in user and a logout URL) and `transfer`. A typed accessor
   exposes them for capability-gated UI; this spec adds no UI.
5. **A test-only fake guard and a reusable contract suite.** The suite checks
   any replacement guard, so the enterprise edition's real guard runs the same
   cases the fake guard does.

With no arguments `create_app` builds exactly the backend it built before this
spec. That is the first acceptance criterion, not a side note.

This spec supersedes one sentence of the ADR-055 Spec 1 design:
`adr-055-webmcp-bridge` FR-006 planned "one middleware, two identity
backends", with a Hub OAuth backend plugging into the bridge middleware's
`BridgeIdentityBackend` protocol. A header-checking backend cannot redirect to
a login page, set a cookie, or cover `/ws` and the application shell, so the
Hub integration replaces the whole guard instead. The bridge's loopback
backend and its protocol are unchanged.

## 2. User Scenarios & Testing

### User Story 1 - The open-source backend is unchanged (Priority: P1)

A scientist runs `scistudio serve`, `scistudio gui`, or the desktop app. The
backend behaves exactly as before this spec: no login, the bridge requires its
per-launch token, and the served page carries the same bootstrap.

**Why this priority**: The owner decision keeps the open-source status quo.
A seam that changed default behavior would contradict it.

**Independent Test**: `create_app()` at the root mount and under
`/user/alice/scistudio`: `/api/version`, `/version`, and the `/ws` handshake
answer without credentials; `/api/webmcp/tools` answers 401 without the token
and 200 with it; the served shell carries the token assignment and no
capability declaration; no lifespan hooks are registered and every capability
is off. The existing `tests/api/test_webmcp.py` and `tests/api/test_root_path.py`
pass unmodified.

**Acceptance Scenarios**:

1. **Given** `create_app()` with no arguments, **When** a client calls any
   route outside `/api/webmcp/*`, **Then** it is answered without credentials,
   as before.
2. **Given** the same app, **When** a client calls the bridge without the
   loopback token, **Then** the answer is 401; with the token it dispatches.
3. **Given** the same app, **When** the page is served, **Then** it carries no
   `window.__SCISTUDIO_CAPABILITIES__` assignment.

### User Story 2 - An edition replaces the guard (Priority: P1)

The enterprise launch command passes its Hub guard to `create_app`. Every
request the guard chooses to protect, the application shell, the API, the
bridge, and `/ws`, is refused without a session and works with one.

**Why this priority**: This is the seam the enterprise edition exists on.

**Independent Test**: The contract suite (`tests/api/seam_contract.py`) with
the fake guard, at both mounts.

**Acceptance Scenarios**:

1. **Given** a replacement guard, **When** a client without a session requests
   the API, the shell (including a deep SPA route), the bridge, or the `/ws`
   handshake, **Then** each is refused (any non-2xx, redirects not followed).
2. **Given** the same app, **When** the client signs in, **Then** each works.
3. **Given** a replacement guard, **When** a client presents a loopback token
   header, **Then** it is not a session: no loopback token was minted.

### User Story 3 - Self-authenticating routes answer for themselves (Priority: P1)

A module that authenticates its own requests, such as the panel file routes
of ADR-054, registers its prefix. Under any guard, a request under the prefix
reaches the route, which accepts or refuses it on its own terms.

**Why this priority**: Without it a panel frame's file requests, which carry
a per-mount token and no session cookie, would be refused by the Hub guard,
and panels would not load in a Lab deployment (ADR-054 SC-009).

**Independent Test**: A fixture prefix and route (panels code is not on `main`
yet). Unauthenticated requests with a good token reach the route; a bad token
gets the route's own 403 body, not the guard's refusal; a lookalike path
(`.../tx/...`) and a sibling path stay guarded; all at both mounts, and under
the default guard as well as a replacement.

**Acceptance Scenarios**:

1. **Given** a registered prefix and a replacement guard, **When** an
   unauthenticated client requests a route under it, **Then** the route
   answers.
2. **Given** the same, **When** the route rejects the request, **Then** the
   client receives the route's rejection.
3. **Given** a prefix registered as `/api/panels/t/`, **When** a request
   arrives at `/user/<name>/scistudio/api/panels/t/...`, **Then** it matches.

### User Story 4 - Startup checks and background tasks run inside the lifespan (Priority: P2)

The enterprise edition validates its configuration at spawn and reports
activity to the Hub while runs are active.

**Why this priority**: A misconfigured callback should fail at spawn, not at a
user's first login, and idle culling must not stop a running analysis.

**Independent Test**: Recording hooks show entry in order after the runtime
exists and exit in reverse; a background task started by a hook is cancelled
at shutdown; a hook that raises aborts startup, the hooks already entered are
exited, and the core teardown runs.

**Acceptance Scenarios**:

1. **Given** hooks A and B, **When** the app starts and stops, **Then** the
   order is enter A, enter B, exit B, exit A.
2. **Given** a hook whose entry raises, **When** the app starts, **Then**
   startup fails with that error and no hook after it is entered.

### User Story 5 - The frontend learns the edition's capabilities (Priority: P2)

An edition declares `identity` and `transfer`. The page it serves carries the
declaration, and frontend code reads it through one typed accessor.

**Why this priority**: The owner placed the enterprise UI in the open-source
frontend, hidden by default (UI placement option A). The components need a
way to know when to appear.

**Independent Test**: Backend tests assert the injected declaration, its
absence by default, and its script safety; `frontend/src/lib/capabilities.test.ts`
asserts the typed read, the all-off default, and that malformed or unsafe
input reads as off.

### User Story 6 - The enterprise guard runs the same contract (Priority: P2)

The enterprise repository runs the contract suite against its Hub guard and
gets the same cases the fake guard passes here.

**Why this priority**: A contract that only the fake guard ever meets proves
nothing about the deployment.

**Independent Test**: The suite is a base class parametrized over a guard case;
the fake guard's subclass in this repository is the reference use (Section 4.5).

### Edge Cases

- A replacement guard that answers with a redirect to its login page is a
  refusal; the suite does not follow redirects.
- A path that only shares the prefix's text (`/api/panels/tx`) does not match;
  matching is on segment boundaries.
- A path equal to the prefix itself matches; with no route there it is a 404.
- Unknown paths under `/api/` are 404s; the SPA fallback never serves the
  shell there. That is why a self-authenticating prefix must lie under `/api/`:
  it can only ever reach a real route or a 404, never the application shell
  without login.
- A router included on the app after `create_app` returns sits behind the SPA
  mount at `/` and is never reached; an edition passes its routers to the
  factory instead.
- `/api/webmcp/*` is outside every registered prefix unless a module registers
  one inside it; the default guard honors that too.

## 3. Requirements

### 3.1 The Factory

- **FR-001**: `create_app` MUST accept the keyword-only arguments `guard`,
  `lifespan_hooks`, `capabilities`, and `routers`, each defaulting to "none".
  Called with no arguments it MUST build the backend it built before this spec
  (US1). Malformed arguments MUST raise `TypeError` before anything is built.
- **FR-002**: `routers` MUST be included after every built-in route and before
  the SPA mount; a built-in route wins a path collision.

### 3.2 The Guard

- **FR-003**: The middleware stack MUST hold exactly one guard, in the position
  the bridge session middleware held: inside the CORS layer, so preflight and
  CORS headers on rejections stay with CORS, and inside request logging, so a
  rejection is logged with its request id.
- **FR-004**: With no `guard`, the guard MUST be the WebMCP bridge's
  `WebMCPSessionMiddleware` with the loopback token backend, scoped to
  `/api/webmcp/*`, and the per-launch token MUST be minted and injected as
  before. With a `guard`, the replacement MUST take the slot, no loopback token
  is minted, and `app.state.webmcp_session_token` is `""`.
- **FR-005**: A guard is a `GuardFactory`: called once as
  `guard(app, context)` with the inner ASGI app and a `GuardContext`, it
  returns the guard, itself an ASGI app. `GuardContext` carries the normalized
  mount prefix and `route_path(scope)`, which removes it exactly as the router
  does. Fields are added to `GuardContext`, never to the call.
- **FR-006**: The guard MUST receive only `http` and `websocket` scopes that are
  not under a self-authenticating prefix; the factory routes every other scope
  (the lifespan scope, registered prefixes) past it.

### 3.3 Self-Authenticating Prefixes

- **FR-007**: `scistudio.api.seam` MUST provide
  `register_self_authenticating_prefix(prefix) -> str`,
  `unregister_self_authenticating_prefix(prefix)`,
  `self_authenticating_prefixes() -> tuple[str, ...]`, and
  `is_self_authenticating_path(route_path) -> bool`. Registration normalizes
  the prefix (`/api/panels/t/` becomes `/api/panels/t`), is idempotent, and
  keeps registration order.
- **FR-008**: A prefix MUST lie under `/api/` and name at least one segment
  below it; each segment MUST be literal (no `.`, `..`, or wildcard
  characters). Anything else raises `ValueError`.
- **FR-009**: Matching MUST run on the route path after root-path prefix
  handling, on segment boundaries: a prefix matches itself and anything below
  it, never a path that only shares its text.
- **FR-010**: `create_app` MUST enforce the bypass around whichever guard it
  installs, so no guard has to remember it; `WebMCPSessionMiddleware` MUST
  also honor the registry when composed on its own.
- **FR-011**: A route under a registered prefix MUST authenticate every request
  it serves. The registry grants no access; it moves the check to the route.

### 3.4 Lifespan Hooks

- **FR-012**: A `LifespanHook` is called with the app at startup and returns an
  async context manager. Hooks MUST be entered in the given order after the
  core runtime exists (`app.state.runtime` is set) and exited in reverse
  before the core teardown.
- **FR-013**: A hook whose entry raises MUST abort startup; hooks already
  entered MUST be exited, hooks after it MUST NOT be entered, and the core
  teardown MUST still run.

### 3.5 Capabilities And The Per-Mount Token Exception

- **FR-014**: `Capabilities(identity=None, transfer=False)` MUST be the default.
  `IdentityCapability(user, logout_url)` MUST reject an empty user and any
  logout URL that is not an absolute path (not starting with `//`) or an
  `http(s)` URL with a host; the frontend renders it into a link, so no other
  scheme may pass.
- **FR-015**: When at least one capability is on, the served `index.html`
  MUST carry `window.__SCISTUDIO_CAPABILITIES__ = {"identity": {"user", "logoutUrl"} | null, "transfer": bool}`,
  serialized so no value can close the script element (`<`, `>`, `&`, U+2028
  and U+2029 escaped). When every capability is off, nothing is emitted.
- **FR-016**: `frontend/src/lib/capabilities.ts` MUST expose
  `getCapabilities()` and `isCapabilityEnabled(name)`, read the declaration
  once, return frozen values, read an absent declaration as all off, and read
  each malformed or unsafe field as off without throwing. It MUST NOT render
  UI.

The per-mount token exception that ADR-054 planned to record in the Lab spec
(`adr-054-panels` FR-026 and FR-047) is recorded here, because Spec 4 leaves
this repository with the enterprise edition (#2303):

- **FR-017**: ADR-054 panel files, the SDK, and the library set are served
  under `/api/panels/t/{token}/...` and authenticated by the per-mount token of
  ADR-054 FR-025, not by a session. When panels resume, the panels module MUST
  register `/api/panels/t/` through FR-007, and its routes MUST refuse a
  missing, expired, or closed-context token. Under any guard, including the
  enterprise Hub guard, those requests reach the panel routes; a panel token
  authorizes `GET` of that panel's files, the SDK, and the library set only,
  and never an API route outside the prefix, because matching is on segment
  boundaries (FR-009). ADR-054 SC-009, a prefixed session-authenticated
  deployment, is exercised by the contract suite's prefixed mount with a
  fixture prefix until the panel routes exist.

### 3.6 Declared Surface

- **FR-018**: `scistudio.api.app` (`create_app`) and `scistudio.api.seam` MUST
  be ADR-052 canonical roots, each with an `__all__` whose every symbol is
  `provisional` since 0.3.5: `create_app`; `GuardFactory`, `GuardContext`,
  `LifespanHook`, `Capabilities`, `IdentityCapability`, the four registry
  functions, `workflow_runs_active`, the shared FastMCP registry `mcp`, and
  `AUDIENCE_EXTERNAL_TAG`. The freeze snapshot and the generated reference MUST
  include both roots.
- **FR-019**: `workflow_runs_active(app)` MUST return whether any workflow run's
  task is still executing, and `False` before the runtime exists.

### 3.7 Test-Only Guard And Contract Suite

- **FR-020**: A fake guard MUST live in the test tree (`tests/api/fake_guard.py`),
  not in product code. It accepts a test cookie, protects every HTTP and
  WebSocket request otherwise, and is installed through `create_app(guard=...)`
  exactly as a real guard is. It MUST NOT consult the registry, so passing the
  suite shows the factory enforces the bypass.
- **FR-021**: The contract suite MUST be a base class parametrized over a guard
  case (`GuardCase(name, guard, authenticate)`), run at the root mount and
  under a mount prefix, and depend only on pytest, FastAPI's test client,
  Starlette, and SciStudio. Section 4.5 is its documented use by an external
  package.

### Key Entities

- **GuardContext**: the mount prefix a guard is built with; transient.
- **GuardFactory**: the callable passed as `guard`; builds the guard once.
- **LifespanHook**: the callable passed in `lifespan_hooks`; returns the async
  context manager bracketing a startup check or background task.
- **Self-authenticating prefix**: a normalized route-path prefix in a
  process-wide registry; no persistence.
- **Capabilities / IdentityCapability**: the frozen declaration an edition
  passes; kept on `app.state.capabilities` and injected into the page.
- **GuardCase** (test tree): one guard under contract test.

## 4. Implementation Plan

### 4.1 Technical Approach

`create_app` installs `GuardDispatchMiddleware` in the guard slot. It builds
the guard once from the factory and, per request, sends non-HTTP/WebSocket
scopes and registered prefixes to the inner application and everything else
through the guard. The default factory is `loopback_token_guard(token)` in
`api/routes/webmcp.py`, which builds the same `WebMCPSessionMiddleware` the
factory installed before. Enforcing the bypass in the dispatcher, rather than
asking each guard to check the registry, means a guard cannot forget it.

The lifespan reads the hooks from `app.state.lifespan_hooks`, which
`create_app` sets, and enters them with an `AsyncExitStack` inside the existing
`try`/`finally`, so the core teardown still runs on any failure. `lifespan`
itself keeps its signature.

**Capability delivery**: the served page bootstrap, not an endpoint. The SPA
bootstrap already carries the base path and the bridge token, is the first
thing the page reads, and needs no request, loading state, or authentication
of its own. The declaration is emitted only when a capability is on, so the
open-source shell is untouched. A page not served by the backend (the vite
dev server) reads as all off, which is the open-source default. An endpoint
would add a request the frontend must wait for and a route every guard must
cover.

**Two canonical roots**: `create_app` stays at the path the CLI, desktop shell,
and `uvicorn scistudio.api.app:create_app` already use, and `app.py` gets an
`__all__` naming it alone. The seam's types live in `scistudio.api.seam`,
which `app.py` imports; re-exporting `create_app` from the seam would make the
two modules import each other. `scistudio.api.seam.mcp` is the shared registry
object from `scistudio.ai.agent.mcp.server`; the provisional marker is stamped
on that object, so it reads the same through either path.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/api/seam.py` | create | Guard, hook, and capability types; the registry; `workflow_runs_active`; republished MCP registry |
| `src/scistudio/api/app.py` | modify | `create_app` arguments, guard dispatch, lifespan hooks, routers, capability hand-off; `__all__` |
| `src/scistudio/api/routes/webmcp.py` | modify | `loopback_token_guard`; the middleware honors the registry and uses the shared route-path helper |
| `src/scistudio/api/spa.py` | modify | Script-safe capability injection |
| `frontend/src/lib/capabilities.ts` | create | Typed capability accessor |
| `tests/api/seam_contract.py` | create | Reusable guard contract suite |
| `tests/api/fake_guard.py` | create | Test-only fake guard |
| `tests/api/test_identity_seam.py` | create | Contract run for the fake guard; default-unchanged, registry, hooks, capabilities, routers, surface |
| `frontend/src/lib/capabilities.test.ts` | create | Accessor tests |
| `tests/api/test_public_surface.py`, `tests/api/public_surface.snapshot.json` | modify | Freeze the two new roots |
| `scripts/docs/build_reference.py`, `mkdocs.yml`, generated reference pages | modify / regenerate | Reference for the two new roots, regenerated by the script |
| `src/scistudio/_agent_reference/public-api.md` | modify | Canonical-root table |
| `docs/adr/ADR-055.md` | modify | Section 8 amendment |

### 4.3 Implementation Sequence

1. **T-001** (US1, US2): `seam.py` guard types, `GuardDispatchMiddleware`,
   `loopback_token_guard`, the `create_app` guard slot; default-unchanged tests.
2. **T-002** (US3): the registry and its enforcement in the dispatcher and the
   bridge middleware; registry tests.
3. **T-003** (US4): lifespan hooks; order, teardown, and failure tests.
4. **T-004** (US5): capabilities, the injection, the frontend accessor.
5. **T-005** (US6): the fake guard and the contract suite at both mounts.
6. **T-006**: the declared surface: canonical roots, snapshot, regenerated
   reference, changelog, ADR-055 amendment.

### 4.4 Verification Plan

- `tests/api/test_identity_seam.py`: the fake guard's contract run (both
  mounts); default behavior unchanged (both mounts); the default guard and a
  lone bridge middleware honoring the registry; a replacement guard never
  seeing a bypassed path; registry normalization, validation, and matching;
  lifespan order, background-task cancellation, and startup failure;
  capability validation, injection, and script safety; routers ahead of the
  SPA mount; argument validation; `workflow_runs_active`; the republished MCP
  registry and markers.
- `tests/api/test_public_surface.py`: the freeze test for the new roots.
- `tests/api/test_webmcp.py`, `tests/api/test_root_path.py`,
  `tests/api/test_app.py`: unchanged and passing.
- `frontend/src/lib/capabilities.test.ts`: default, typed read, malformed and
  unsafe input, caching, frozen values.
- `gate_record check` for the tier-selected checks.

### 4.5 Running The Contract Suite From Another Package

`tests/api/seam_contract.py` is not shipped in the wheel. The enterprise
repository takes it from the SciStudio tag it builds on, for example by
fetching that one file into its own test tree, and subclasses it:

```python
import pytest
from seam_contract import GuardCase, GuardContractSuite


class TestHubGuardContract(GuardContractSuite):
    @pytest.fixture()
    def guard_case(self) -> GuardCase:
        return GuardCase(
            name="hub",
            guard=hub_guard_factory(test_settings()),
            authenticate=sign_in_through_hub_double,
        )
```

`authenticate` turns the test client into a signed-in session, for example by
completing the OAuth flow against a Hub test double or by setting a signed
cookie. The suite patches two internal hooks, the SPA directory resolver in
`scistudio.api.app` and `Path.home` as seen by `scistudio.api.runtime`, which
is why it is taken at the matching version rather than written against the
wheel.

### 4.6 Risks And Rollback

- Risk: a registered prefix wider than its routes' authentication. Mitigation:
  prefixes are confined to `/api/`, literal, and matched on segment
  boundaries; FR-011 puts authentication on the route, and registration is
  code-reviewed like any route.
- Risk: the enterprise edition depends on open-source internals. Mitigation:
  the provisional declaration (FR-018) puts each change through the freeze
  test and the changelog.
- Risk: the default path changes shape (a dispatcher now wraps the bridge
  middleware). Mitigation: the existing bridge and root-path suites pass
  unmodified, and the default-unchanged tests cover both mounts.
- Rollback: the arguments are additive and default to today's behavior;
  removing them restores the previous factory. No data or schema migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: `tests/api/test_webmcp.py` and `tests/api/test_root_path.py` pass
  without modification, and the default-unchanged tests pass at both mounts.
- **SC-002**: The fake guard passes every contract case at both mounts.
- **SC-003**: A route under a registered prefix is reached without credentials
  under the default guard and under a replacement guard, and a replacement
  guard records no bypassed path.
- **SC-004**: A failing startup hook aborts startup in 100% of test runs, with
  the entered hooks exited and the core teardown run.
- **SC-005**: With every capability off, the served page contains no
  capability assignment; with any on, the declaration parses back to the
  declared values and closes no script element.
- **SC-006**: The freeze snapshot pins both new roots, thirteen provisional
  symbols in all.

## 6. Assumptions

- The enterprise edition runs one backend per user, so `identity` is fixed for
  a backend's lifetime and can be declared at construction (source: ADR-055
  section 8 instance contract).
- The enterprise edition pins the SciStudio version it builds on and reads the
  changelog for provisional changes (source: owner decision 2026-09-11,
  option B trade-off).
- Panels register `/api/panels/t/` when ADR-054 Phase A resumes (#2288); until
  then the registry is exercised with fixture prefixes (source: owner
  sequencing update 2026-09-11 on #2304).
- The capability-gated UI components are designed once the enterprise transfer
  and logout API contracts exist; `frontend/src/lib/capabilities.ts` carries
  the tracked `TODO(#2304)` for them (source: owner UI placement decision,
  option A).
