---
spec_id: adr-055-lab-deployment
title: "ADR-055 Spec 4 — Internal Lab Deployment: JupyterHub Identity, Native Hub OAuth, Per-User Instances"
status: Draft
feature_branch: docs/2263-adr-055-specs
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 4 covers ADR-055 section 8. Owner decisions recorded: (1) SciStudio implements JupyterHub OAuth natively as the single-user server — SystemdSpawner directly spawns 'scistudio serve --hub'; jupyter-server-proxy standalone is rejected because ADR-055 section 8's raw-port bypass protection requires in-product authentication anyway (loopback is not isolation between users on a shared Linux host), the proxy hop adds SSE/WebSocket/large-file buffering and timeout risk, session cookies need SameSite=None;Secure under SciStudio's own control for external-AI-host iframes, and XSRF rules should be the product's own; (2) the server side splits into three ownership blocks — deployment assets at deploy/jupyterhub/ (configs, units, runbook; not Python import surface), the identity adapter at src/scistudio/deployment/jupyterhub/ (all JupyterHub knowledge confined there), and prefix independence staying in core as adr-055-prefix-independence; (3) the verification environment is the owner's WSL2 with systemd enabled, with declared caveats."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 22
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
  - adr-055-agent-context-workspace
scope:
  in:
    - "The `scistudio serve --hub` mode: SystemdSpawner spawns SciStudio directly as the per-user single-user server."
    - "The identity adapter at `src/scistudio/deployment/jupyterhub/`: Hub OAuth client (authorize/callback/token-verification against the Hub API), SciStudio-issued session cookies, activity reporting to the Hub, and logout; all JupyterHub knowledge confined to this directory."
    - The shared session middleware backend (seam from adr-055-webmcp-bridge) wired so Hub OAuth covers the UI, all APIs, WebSocket, the WebMCP bridge, and transfer endpoints, with no localhost exemption — raw backend ports are protected by the same check.
    - "Deployment assets at `deploy/jupyterhub/`: jupyterhub_config.py, systemd unit material, reverse-proxy/TLS guidance, and an operator runbook; not importable Python surface."
    - "The per-user instance contract: one user, one backend, one bundled Python, one runtime environment shared by that user's projects; persistent workspaces; writable per-user dependency state."
    - "Prefix integration: the Hub-provided service prefix drives the root-path contract from adr-055-prefix-independence."
    - "Lifetime behavior: browser disconnection and idle detection never terminate active analyses or transfers; projects survive service restart."
    - Verification on WSL2 with systemd enabled, including two-user isolation, raw-port bypass attempts, and resource-limit statements.
  out:
    - Public SaaS, public-demo hosting, tunnels, branded domains (excluded by ADR-055 sections 2 and 10).
    - Docker/container deployment products, per-project environments, dependency locking (excluded by ADR-055 sections 8 and 10).
    - Automatic per-project environment switching on project selection (excluded by ADR-055 section 8).
    - Multi-user editing of the same project (excluded by ADR-055 section 2).
    - The prefix-independence implementation itself (adr-055-prefix-independence).
    - Production bare-metal certification beyond the WSL2 verification environment (follow-up; WSL2 caveats are declared, not waived).
governs:
  modules:
    - scistudio.cli.main
    - scistudio.api.app
    - scistudio.api.ws
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-055-lab-deployment.md
    - src/scistudio/cli/main.py
    - src/scistudio/api/app.py
    - src/scistudio/api/ws.py
  excludes: []
planned_governs:
  modules:
    - scistudio.deployment.jupyterhub
  contracts: []
  entry_points: []
  files:
    - src/scistudio/deployment/jupyterhub/**
    - deploy/jupyterhub/**
  excludes: []
tests:
  - tests/deployment/test_hub_oauth.py
  - tests/deployment/test_hub_session_middleware.py
acceptance_source: adr
language_source: en
---

# ADR-055 Spec 4 — Internal Lab Deployment: JupyterHub Identity, Native Hub OAuth, Per-User Instances

## 1. Change Summary

This spec comes from ADR-055 (section 8) and umbrella issue #2263.

A lab keeps large datasets on a Linux server; its scientists open SciStudio
from their own computers and operate on server-resident projects. JupyterHub
provides identity and per-user routing; SystemdSpawner provides per-user
systemd services; SciStudio itself is the spawned single-user server.

The owner settled the contested design point: **SciStudio implements Hub OAuth
natively; jupyter-server-proxy standalone is rejected.** The recorded reasons:

1. ADR-055 section 8 requires "protection against bypass through a raw backend
   port". On a shared Linux host, loopback is not isolation between users —
   any local user can reach another user's proxied backend port. In-product
   authentication is therefore mandatory either way; the proxy adds nothing.
2. The proxy hop adds buffering/timeout risk on exactly the paths ADR-055
   section 11 stresses: SSE, WebSocket, large transfers, long executions.
3. WebMCP pages may run inside external-AI-host iframes (cross-site), requiring
   `SameSite=None; Secure` session cookies under SciStudio's own control —
   not the Hub/proxy defaults.
4. XSRF rules should be the product's own rather than JupyterHub 4/5's
   enforced proxy-mode rules.

The server side splits into three ownership blocks (owner-directed): deployment
assets at `deploy/jupyterhub/` (not Python import surface), the identity
adapter at `src/scistudio/deployment/jupyterhub/` (the only place JupyterHub
knowledge exists), and prefix independence in core as
`adr-055-prefix-independence` (already its own spec; zero Hub dependency).

Alternatives considered and rejected, with research evidence: jupyter-server-
proxy standalone (above); jhsingle-native-proxy (removes the per-user Jupyter
server but its inner backend port stays bare — the same raw-port hole — and
the project is single-author maintained); a standard web stack (nginx
`auth_request` + Authelia + systemd socket activation over per-user unix
sockets — the cleanest isolation available, but no self-service control plane
and it rebuilds what JupyterHub already provides for this audience); Open
OnDemand (full HPC portal; Passenger cannot host ASGI; its batch-connect apps
do not protect raw ports either); Coder/Che/Onyxia/ShinyProxy (container/K8s
dependencies or scenario mismatch).

## 2. User Scenarios & Testing

### User Story 1 - A scientist logs in and reaches their own backend (Priority: P1)

A scientist opens the lab URL, authenticates through JupyterHub, is routed to
their own SciStudio instance (spawned on demand by SystemdSpawner), and works
on their own projects — no Linux desktop, no SSH, no personal CLI agent setup.

**Why this priority**: This is the deployment's core promise (ADR-055 section
8's opening paragraph).

**Independent Test**: In the WSL2 verification environment with two Hub users,
log in as each and assert: each reaches a distinct backend process owned by
their Unix account; each sees only their own known projects; a workflow run in
one instance is invisible to the other.

**Acceptance Scenarios**:

1. **Given** the deployment configured per `deploy/jupyterhub/`, **When** a
   new scientist logs in through the Hub, **Then** a per-user systemd unit
   starts `scistudio serve --hub` as their account and the Hub routes their
   browser to it under their service prefix.
2. **Given** two logged-in users, **When** both work concurrently, **Then**
   projects, workspaces, and dependency state are fully independent.

### User Story 2 - Every path requires identity, including the raw port (Priority: P1)

Unauthenticated requests to the UI, any API, the WebSocket endpoint, the
WebMCP bridge, and transfer endpoints are rejected — including requests that
bypass the Hub proxy and hit the backend's listening socket directly as
another local user.

**Why this priority**: This is ADR-055 section 8's hardest requirement and the
reason native auth exists; a proxy-only check leaves the raw-port hole open.

**Independent Test**: From the WSL2 host as a second local user (no Hub
session), attempt: the backend port directly, the WebSocket upgrade, a bridge
call, and a transfer download — all rejected; then with a valid session for
user A, attempt access to user B's instance — rejected.

**Acceptance Scenarios**:

1. **Given** a running user backend bound on loopback, **When** another local
   user curls it without credentials, **Then** every endpoint (UI, API, WS,
   bridge, transfer) rejects the request.
2. **Given** a valid Hub session for user A, **When** it is presented to user
   B's backend, **Then** the backend rejects it (identity mismatch).

### User Story 3 - The instance contract holds (Priority: P2)

Each user has one backend, one bundled Python, and one runtime environment
shared by their projects; dependency state is writable per user; workspaces and
results persist across service restarts and browser lifetimes.

**Why this priority**: ADR-055 section 8 makes this the explicit contract;
shared-environment side effects across a user's projects are intended
behavior, not defects.

**Independent Test**: As one user with two projects, install a package and
assert both projects resolve it; restart the systemd unit and assert projects
and results persist; assert the second user's environment is untouched.

**Acceptance Scenarios**:

1. **Given** one user with two projects, **When** a dependency is installed,
   **Then** both projects see it (intended sharing) and no other user is
   affected.
2. **Given** active projects, **When** the user's systemd unit restarts,
   **Then** projects, workspaces, and results persist.

### User Story 4 - Disconnection and idleness never kill work (Priority: P2)

Closing the browser or going idle leaves running analyses and transfers alone;
activity reporting keeps the Hub informed without letting idle management
terminate active work.

**Why this priority**: ADR-055 section 8 states it verbatim; culling that
kills long analyses makes the deployment unusable for its main workload.

**Independent Test**: Start a long analysis, close the browser, wait past the
Hub idle window, and assert the analysis completes and its artifacts persist;
assert activity reports reach the Hub while work runs.

**Acceptance Scenarios**:

1. **Given** a running analysis, **When** the browser closes and the Hub idle
   timeout passes, **Then** the analysis runs to completion.
2. **Given** a truly idle instance (no jobs, no transfers), **When** the
   deployment's idle policy applies, **Then** the declared culling behavior
   executes and the workspace persists for the next login.

### User Story 5 - An administrator installs once and operates with systemd (Priority: P3)

An administrator installs and configures the service once using
`deploy/jupyterhub/`: Hub config, systemd units, TLS/proxy guidance, and a
runbook; service users are provisioned or mapped by the deployment layer with
persistent workspace ownership; resource limits are administrator-configured
through systemd and verified, not merely declared.

**Why this priority**: ADR-055 section 8 assigns system-level setup to
administrators; unverifiable limits ("declaring a limit in a configuration is
not enforcement") are called out explicitly.

**Independent Test**: From a fresh WSL2 systemd environment, follow the
runbook to a working two-user deployment; set a memory limit on the user unit
and demonstrate enforcement with a workload that crosses it.

**Acceptance Scenarios**:

1. **Given** a fresh environment, **When** the runbook is followed, **Then**
   the result passes US1–US4 without undocumented steps.
2. **Given** a configured cgroup memory limit, **When** a workload exceeds it,
   **Then** the configured enforcement is observed (OOM/swap behavior as
   configured), and the verification note records the result.

### Edge Cases

- OAuth callback under the service prefix: the callback URL must be
  prefix-correct (consumes `adr-055-prefix-independence`); a wrong prefix must
  fail loudly at startup validation, not as a login loop.
- WebSocket cookie authentication in a shared parent domain: SciStudio's own
  session cookie (scoped per instance) avoids the Hub's cross-user cookie
  caveat; the spec forbids relying on Hub cookies for WS auth.
- Expired Hub token mid-session: the session middleware re-validates per its
  declared interval and forces re-authentication without losing backend state.
- Hub unavailable while instances run: existing sessions continue until their
  declared re-validation fails; new logins fail closed.
- `serve --hub` started outside a Hub spawn (missing `JUPYTERHUB_*` env):
  refuses to start with an explicit diagnostic; never falls back to
  unauthenticated serving.
- GPU placement: resource constraints are verified in the WSL2 environment
  (CUDA visible) with the WSL2-vs-bare-metal caveat recorded.

## 3. Requirements

### Functional Requirements

- **FR-001**: `scistudio serve --hub` MUST run as a Hub single-user server:
  it reads the standard `JUPYTERHUB_*` environment provided by the spawner,
  refuses to start when it is absent, and applies the Hub-provided service
  prefix through the `adr-055-prefix-independence` root-path contract.
- **FR-002**: The identity adapter (`src/scistudio/deployment/jupyterhub/`)
  MUST implement the Hub OAuth2 flow (authorize redirect, callback, code
  exchange against the Hub API, token-to-identity verification) and MUST be
  the only module importing or referencing JupyterHub concepts.
- **FR-003**: On successful OAuth, SciStudio MUST issue its own session cookie
  (`Secure`; `SameSite=None` where the iframe-hosting requirement applies,
  with the declared fallback for contexts that reject it) and MUST enforce its
  own XSRF rules; Hub cookie behavior is never relied upon for SciStudio
  endpoints.
- **FR-004**: The session middleware (seam from `adr-055-webmcp-bridge`) MUST
  cover the UI, all `/api` routes, `/ws`, `/api/webmcp/*`, and transfer
  endpoints, with no localhost exemption; identity MUST match the instance's
  owning user.
- **FR-005**: The adapter MUST report activity to the Hub and MUST report
  active jobs/transfers so idle management never terminates active work; the
  declared idle-culling behavior for truly idle instances MUST be documented
  in the runbook.
- **FR-006**: The instance contract MUST hold: one user, one backend, one
  bundled Python, one runtime environment; per-user writable dependency state;
  workspaces persistent across restarts; no per-project environments.
- **FR-007**: The backend in hub mode MUST bind loopback only; protection
  against raw-port bypass comes from FR-004 authentication, not from binding
  alone.
- **FR-008**: `deploy/jupyterhub/` MUST contain the Hub config, systemd unit
  material, proxy/TLS guidance, and an operator runbook sufficient to reach a
  working deployment from a fresh systemd-enabled Linux environment; these
  assets are not importable Python surface.
- **FR-009**: Resource limits MUST be administrator-configured through systemd
  and MUST be verified (memory at minimum; GPU placement stated with its
  verification result) in the verification environment; unverifiable limits
  are documented as unverified, never claimed.
- **FR-010**: Browser disconnection MUST NOT terminate analyses or transfers;
  persisted projects MUST survive service restart; no promise of uninterrupted
  execution through a backend crash (ADR-055 section 8).
- **FR-011**: Startup validation MUST fail loudly on prefix/callback
  misconfiguration (detectable at spawn, not at first login).

### Key Entities

- **HubIdentity**: Hub username, normalized local user, OAuth token state,
  re-validation timestamp; transient (session-scoped), no new persistence.
- **InstanceBinding**: owning user, service prefix, loopback port, systemd
  unit name; produced by the spawner configuration, consumed by startup
  validation.

## 4. Implementation Plan

### 4.1 Technical Approach

The identity adapter wraps the Hub OAuth reference flow (the Hub's
`jupyterhub.services.auth` contract is the protocol reference; the
implementation is plain HTTP against the Hub API, framework-native to
FastAPI/Starlette — estimated 150–300 lines plus middleware and tests, per
owner-accepted research). Session issuance signs its own cookie value;
verification is local (signed cookie) with periodic Hub re-validation.

The middleware plugs into the seam from `adr-055-webmcp-bridge`: one
middleware, two identity backends (loopback token for local modes, Hub OAuth
here). App construction selects the backend from the serve mode; `app.py`
gains only the selection wiring, keeping Hub knowledge inside the adapter
directory.

SystemdSpawner configuration in `deploy/jupyterhub/` sets the spawn command to
`scistudio serve --hub` and passes the standard `JUPYTERHUB_*` environment;
per-user units run under ordinary accounts with administrator cgroup limits.
The runbook covers install, user provisioning/mapping, TLS termination,
verification steps, and the WSL2-vs-bare-metal caveats.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/deployment/jupyterhub/oauth.py` | create | Hub OAuth client |
| `src/scistudio/deployment/jupyterhub/session.py` | create | Session issuance/verification, activity reporting |
| `src/scistudio/deployment/jupyterhub/middleware.py` | create | Identity backend for the shared session middleware |
| `src/scistudio/cli/main.py` | modify | `serve --hub` mode and startup validation |
| `src/scistudio/api/app.py` | modify | Identity-backend selection wiring (mode-driven) |
| `src/scistudio/api/ws.py` | modify | WS authentication through the session middleware |
| `deploy/jupyterhub/jupyterhub_config.py` | create | SystemdSpawner config spawning SciStudio |
| `deploy/jupyterhub/systemd/` | create | Unit templates and drop-ins |
| `deploy/jupyterhub/RUNBOOK.md` | create | Install/configure/verify/operate guide |
| `tests/deployment/test_hub_oauth.py` | create | OAuth flow against a Hub-API test double |
| `tests/deployment/test_hub_session_middleware.py` | create | Coverage matrix: UI/API/WS/bridge/transfer, raw-port, cross-user |

### 4.3 Implementation Sequence

1. **T-001** (foundation): identity-backend interface wiring in `app.py`
   (consumes the spec-1 seam; fails closed when unconfigured).
2. **T-002** (US2): Hub OAuth client + session issuance + middleware coverage
   matrix tests with a Hub-API double.
3. **T-003** (US1): `serve --hub` mode, spawner config, startup validation.
4. **T-004** (US3/US4): instance contract and lifetime behavior; activity
   reporting.
5. **T-005** (US5): `deploy/jupyterhub/` assets + runbook; WSL2 verification
   pass producing recorded evidence.
6. **T-006** (cross-cutting): ADR-055 section 11 Lab identity and Lab lifetime
   rows; resource-limit verification records.

### 4.4 Verification Plan

- Unit/integration tests with a Hub-API test double: full OAuth flow, session
  lifecycle, middleware coverage matrix, identity mismatch, raw-port attempts.
- WSL2 (systemd enabled) end-to-end: two Hub users, isolation, restart
  persistence, disconnect resilience, idle policy, memory-limit enforcement,
  GPU statement; results recorded with the WSL2 caveat (NAT/localhost
  forwarding and cgroup behavior differ from bare metal; both are declared in
  the runbook, not waived).
- Existing suites pass unchanged (local/desktop modes unaffected: hub mode is
  additive).
- `gate_record check` tier-selected checks for the diff.

### 4.5 Risks And Rollback

- Risk: Hub OAuth details (cookie domains, XSRF, token expiry) are easy to get
  subtly wrong. Mitigation: fail-closed defaults, the coverage-matrix test
  suite, and the runbook verification steps; the surface is confined to one
  directory for auditability.
- Risk: `SameSite=None` cookies require secure contexts end-to-end; a lab
  without TLS breaks iframe embedding. Mitigation: the runbook makes TLS a
  hard requirement for external-AI-host use and states the degraded behavior
  otherwise.
- Risk: WSL2 verification diverges from production bare metal. Mitigation:
  caveats recorded per check; bare-metal certification is explicit follow-up
  scope, not silently claimed.
- Rollback: hub mode is additive (`--hub` flag, new directory, new deploy
  assets); removing it restores current behavior. No migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: Two independent Hub users reach separate backends with fully
  independent projects, workspaces, and dependency state, verified end-to-end
  in WSL2.
- **SC-002**: 100% of the endpoint coverage matrix (UI, API, WS, bridge,
  transfer) rejects unauthenticated, cross-user, and raw-port-bypass requests.
- **SC-003**: A browser-disconnected analysis completes and persists; a
  restarted unit restores projects with zero loss.
- **SC-004**: A configured memory limit demonstrably constrains a
  limit-crossing workload in the verification environment (result recorded).
- **SC-005**: The runbook reaches a working deployment from a fresh
  systemd-enabled environment with zero undocumented steps.

## 6. Assumptions

- JupyterHub with SystemdSpawner is the deployment layer; administrators meet
  its requirements (Linux systemd host, root Hub component) (source: ADR-055
  section 8).
- The Hub provides the standard `JUPYTERHUB_*` spawn environment and per-user
  service prefixes (source: JupyterHub spawner contract).
- TLS terminates in front of the Hub; secure contexts are available for the
  iframe/cookie requirements (source: ADR-055 section 11 host-verification
  note).
- Independent use is the collaboration model; shared datasets arrive via
  filesystem permissions (source: ADR-055 section 2).
- WSL2 with systemd enabled is the accepted verification environment, with
  caveats recorded (source: owner session, 2026-09-05).
