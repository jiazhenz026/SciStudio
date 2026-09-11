---
spec_id: adr-055-enterprise-support
title: "ADR-055 Spec 4 — Open-Source Changes For The Enterprise Lab Deployment"
status: Draft
feature_branch: docs/2303-enterprise-support-spec
created: 2026-09-11
input: "Owner-directed live session (2026-09-11). The owner moved multi-user server deployment (the original ADR-055 Spec 4, adr-055-lab-deployment) into a separate, paid enterprise edition kept in a private repository, and asked for an open-source-side Spec 4 that collects every change the public repository makes for that edition: the identity seam, the enterprise UI in the open-source frontend, the stdio MCP adapter for AI apps without WebMCP, PyPI publishing, panel token registration, and server-mode handling of the in-app AI chat. Owner decisions recorded: the open-source edition keeps the status quo (serve binds all interfaces, no login); the enterprise package has its own launch command and composes onto create_app (option B); enterprise UI lives in the open-source frontend behind capability flags (option A); AI apps without WebMCP use a local stdio MCP adapter over the existing /api/webmcp HTTP bridge (option B), authenticating to a lab server with a JupyterHub API token (option A); the in-app AI chat is off by default in server mode and an administrator may enable it (option C), while the plain in-app terminal stays available (owner, same session); the open-source wheel is published to PyPI and GitHub Releases for every OTA build."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 54
  - 52
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
  - adr-055-agent-context-workspace
  - adr-055-local-background-runtime
  - adr-054-panels
scope:
  in:
    - "The contract the open-source edition offers the enterprise package: a replaceable guard, a startup/background hook, a self-authenticating path registry, a capability declaration, a reusable guard contract suite, and ADR-052 provisional status for all of them. The detailed contract belongs to the identity-seam spec delivered by issue #2304; this spec records what it must cover and how the other changes here use it."
    - "Capability-gated enterprise UI in the open-source frontend: signed-in user and logout, laptop-to-server upload and download, an update-available notice, and hiding the in-app AI chat."
    - "Backend refusal of AI-agent PTY sessions when the `ai_chat_disabled` capability is set, so the API matches the UI. The plain in-app terminal (`user-terminal`) is never gated."
    - "A local stdio MCP adapter over the existing WebMCP HTTP bridge for AI apps that support local MCP servers but not WebMCP (issue #2308), including its local and server credentials."
    - "A per-user loopback token file so the adapter can authenticate to a local backend without the page."
    - "Publishing the open-source wheel to PyPI and GitHub Releases for every OTA build (issue #2307) so servers can install it."
    - "ADR-054 panels registering their per-mount token prefix through the seam when panel work resumes (issue #2288)."
    - "Removal of the old `docs/specs/adr-055-lab-deployment.md` from this repository after PR #2292 merges (issue #2303)."
  out:
    - "Everything implemented only in the private enterprise repository: the JupyterHub OAuth guard, session cookie and XSRF rules, Hub API token validation, raw-port protection, activity reporting, transfer endpoints and transfer MCP tools, update and restart handling on the server, deployment assets, runbook, and resource limits."
    - "Login screens or account management in the open-source edition. Users sign in at the Hub; the open-source frontend only displays the identity it is given."
    - "Remote MCP reachable from vendor clouds, public hosting, and tunnels (ADR-055 §2 and §10)."
    - "Any change to the default open-source behavior: `scistudio serve` still binds all interfaces without a login."
    - "The ADR-055 amendment and the detailed identity-seam spec, which the #2304 PR delivers."
governs:
  modules:
    - scistudio.api.app
    - scistudio.api.spa
    - scistudio.api.routes.webmcp
    - scistudio.api.routes.ai_pty
    - scistudio.cli.main
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-055-enterprise-support.md
    - src/scistudio/api/app.py
    - src/scistudio/api/spa.py
    - src/scistudio/api/routes/webmcp.py
    - src/scistudio/api/routes/ai_pty/_state.py
    - src/scistudio/api/routes/ai_pty/websocket.py
    - src/scistudio/cli/main.py
    - frontend/src/components/BottomPanel.tsx
    - frontend/src/lib/api/data.ts
    - frontend/src/lib/capabilities.ts
    - frontend/src/components/Enterprise/**
    - frontend/src/components/Toolbar.tsx
    - frontend/src/components/ProjectTree.parts/ContextMenu.tsx
    - src/scistudio/api/seam.py
    - src/scistudio/api/routes/ai_pty/engine.py
    - src/scistudio/api/routes/ai_pty/internal_routes.py
    - README.md
  excludes: []
planned_governs:
  modules:
    - scistudio.cli.webmcp_adapter
  contracts: []
  entry_points: []
  files:
    - src/scistudio/cli/webmcp_adapter.py
  excludes: []
tests:
  - tests/cli/test_webmcp_adapter.py
  - tests/api/test_enterprise_capabilities.py
  - tests/api/test_ai_pty_capability.py
  - frontend/src/components/Enterprise/EnterpriseChrome.test.tsx
  - frontend/src/components/Enterprise/TransferControls.test.tsx
  - frontend/src/components/Enterprise/AiChatGate.test.tsx
  - frontend/src/lib/capabilities.test.ts
acceptance_source: manual
language_source: en
---

# ADR-055 Spec 4 — Open-Source Changes For The Enterprise Lab Deployment

## 1. Change Summary

This spec came from a manual owner request in the live session of 2026-09-11,
tracked by issue #2303. It governs the open-source side of ADR-055 §8.

ADR-055 §8 originally put a multi-user Lab deployment inside this repository:
JupyterHub login, one SciStudio backend per scientist, laptop-to-server file
transfer, and an administrator runbook. The owner has since moved that
deployment into a separate, paid **enterprise edition**, kept in a private
repository and shipped as its own Python package (`scistudio-enterprise`). The
open-source edition keeps the status quo: one scientist on their own computer,
and `scistudio serve` keeps binding every interface with no login.

The enterprise package does not fork this repository. It has its own launch
command, which builds the ordinary SciStudio backend with `create_app` and then
adds its own guard, routes, MCP tools and background work. That arrangement
needs a small number of changes here, and this spec is the single list of them.
Every item below is **planned**; none is implemented by this document.

| Change | Why the enterprise edition needs it | Tracked by |
|---|---|---|
| Identity seam: replaceable guard, startup/background hook, self-authenticating path registry, capability declaration, contract suite | The enterprise guard and background work attach to the backend without patching it | #2304 (in progress; it also carries the ADR-055 amendment and the detailed seam spec) |
| Capability-gated enterprise UI | Signed-in user, logout, upload/download, and the update notice appear only on an enterprise backend | #2322 |
| `ai_chat_disabled` gating, UI and backend | The in-app AI chat is off by default on a lab server; the terminal stays | this spec, implemented with the UI work |
| Stdio MCP adapter over `/api/webmcp/*` | AI apps without WebMCP, such as Claude, reach SciStudio locally and on a lab server | #2308 |
| Local loopback token file | The adapter authenticates to a local backend without the page | #2308 |
| PyPI and GitHub Releases for every OTA build | Servers install `scistudio` with pip, and the enterprise package declares a compatible range | #2307 (in progress) |
| Panel token prefix registration | ADR-054 panel files pass any guard through the seam | #2288, when panels resume |
| Removal of the old Lab spec | The enterprise-side spec now lives in the private repository | #2303 |

The open-source frontend carries the enterprise UI itself, hidden by default;
there is no separate enterprise frontend bundle. The code is public but inert:
it renders only when the backend declares the matching capability.

## 2. User Scenarios & Testing

### User Story 1 - The open-source edition is unchanged without the enterprise package (Priority: P1)

A scientist who installs only `scistudio`, as a desktop app or with pip, sees
exactly today's behavior: no login, no enterprise controls, the in-app AI chat
available, and `scistudio serve` binding every interface.

**Why this priority**: The owner's first decision is that the open-source
edition keeps the status quo. Every other story is additive, and a regression
here breaks every current user.

**Independent Test**: Run the existing API, frontend and desktop suites with no
replacement guard, no hook and no capabilities passed, and assert unchanged
routes, headers, bootstrap output and UI. Snapshot the default capability
declaration and assert that no capability is declared: every enterprise control is hidden and the AI chat is available.

**Acceptance Scenarios**:

1. **Given** a backend built by `create_app()` with no arguments, **When** the
   SPA boots, **Then** no enterprise control is rendered and the AI chat tab
   is present.
2. **Given** the same backend, **When** `/api/ai/*` is called, **Then** it
   behaves exactly as before this spec.

### User Story 2 - The enterprise package builds a lab backend through the seam (Priority: P2)

The enterprise launch command builds the backend through `create_app`, passing
its guard, its startup and background hook, and its capabilities, and never
needs to patch open-source code.

**Why this priority**: Every enterprise feature depends on it, and it is the
only surface the private package is allowed to depend on.

**Independent Test**: The #2304 contract suite runs against the test-only fake
guard in this repository: every guarded route refuses without the test cookie,
self-authenticating prefixes skip the guard, the hook starts and stops with the
lifespan, and capabilities reach the frontend. The enterprise repository runs
the same suite against its real guard.

**Acceptance Scenarios**:

1. **Given** a replacement guard, **When** a request without credentials hits
   `/api/*`, `/ws` or `/api/webmcp/*`, **Then** the guard rejects it.
2. **Given** a registered self-authenticating prefix, **When** a request under
   it arrives, **Then** the guard lets the owning route authenticate it, also
   under a root-path prefix.

### User Story 3 - A lab user sees who they are signed in as and can log out (Priority: P3)

On an enterprise backend the frontend shows the signed-in user's name and a
Logout action. Logout calls the backend's own logout endpoint, which ends the
SciStudio session first, and then follows the address that endpoint returns.

**Why this priority**: A shared server needs visible identity. Without it a
user cannot tell which account a shared browser is using, or leave it.

**Independent Test**: Boot the SPA with an `identity` capability carrying a
user name and a logout URL, and assert both render. Assert that Logout sends a
same-origin `POST` to the URL, which must resolve under the service prefix,
and then navigates to the location it returns. Boot without the capability
and assert nothing renders.

**Acceptance Scenarios**:

1. **Given** `identity = {user: "alice", logout_url: "..."}`, **When** the app
   renders, **Then** "alice" and Logout are visible.
2. **Given** no `identity` capability, **When** the app renders, **Then**
   neither appears.

### User Story 4 - A lab user moves files between the laptop and the server (Priority: P4)

On an enterprise backend with `transfer` on, the user picks a file on the
laptop and uploads it into the project with visible progress, and downloads a
project file or result to the laptop.

**Why this priority**: The backend and the data live on the server while the
browser and the user's files are on the laptop. The enterprise edition
implements the download endpoint; the controls live here.

**Independent Test**: With `transfer` on, upload a large file through the
picker and assert it lands through the existing `POST /api/data/upload` staged
upload, with progress events and a working cancel. Trigger a download and
assert the browser is sent to the capability's download template with `{path}`
replaced by the file's URL-encoded project-relative path, under the service
prefix. With `transfer` off, assert no control renders.

**Acceptance Scenarios**:

1. **Given** `transfer` on, **When** the user picks a 200 MB file, **Then** it
   uploads through the staged upload with progress and can be cancelled.
2. **Given** `transfer` on, **When** the user downloads an output, **Then** the
   browser requests the capability-supplied URL and the file saves locally.

### User Story 5 - An AI app without WebMCP uses SciStudio through the stdio adapter (Priority: P5)

A scientist configures Claude Desktop, Claude Code, Codex or Cursor to launch
the SciStudio adapter. The app then sees the same tools a WebMCP host sees,
including the Spec 2 workspace and execution tools, against a local backend or
a lab server.

**Why this priority**: WebMCP host support is uneven; Claude's apps do not
expose it yet. The vendors' cloud connectors cannot reach `localhost` or an
internal lab server.

**Independent Test**: Start a backend. Launch the adapter over stdio against it
and assert that `tools/list` matches `GET /api/webmcp/tools`, including the
`audience:external` tools, and that `tools/call` round-trips through
`POST /api/webmcp/call` with the Spec 1 result contract. Switch the backend's
project and assert a stale call returns an error and a `tools/list_changed`
notification follows. Repeat against a guarded backend with a bearer
credential.

**Acceptance Scenarios**:

1. **Given** a local backend, **When** the adapter starts with no credential
   configured, **Then** it reads the per-user loopback token file and
   `tools/list` succeeds.
2. **Given** a lab URL and a configured JupyterHub API token, **When** the
   adapter calls a tool, **Then** it sends the token and the call succeeds.
   The enterprise guard is the one that validates the token.
3. **Given** the backend switches projects, **When** a mutation call carries
   the old snapshot, **Then** the adapter reports the stale-context error and
   sends `notifications/tools/list_changed`.

### User Story 6 - The in-app AI chat is off on a lab server unless the admin enables it; the terminal stays (Priority: P6)

On an enterprise backend the AI Chat surface is hidden and the backend refuses
to start AI-agent sessions, unless the administrator enabled the AI chat, which omits `ai_chat_disabled`. The
in-app Terminal is unaffected. On the server it opens a shell as the user's
own Unix account, like JupyterLab's terminal.

**Why this priority**: ADR-055 §8 expects Lab users to run their AI on the
laptop and not configure personal CLI agents on the server. Users still need a
shell next to their server-side data.

The terminal and the AI chat share the `/api/ai` PTY routes. The gate
therefore checks the provider kind, not the route. The gate is a default and
an administrator policy, not a security boundary: from the terminal, a user
can run any CLI they install in their own account. The terminal grants no new
privilege, because workflow blocks already run arbitrary code as that user.

**Independent Test**:

- With `ai_chat_disabled` set, assert that the bottom panel has no AI Chat surface and
  that spawning any agent-kind provider through `/api/ai` is refused with a
  clear error. That covers the chat WebSocket, an AI Block tab, and a Bring
  In My Work session.
- With `ai_chat_disabled` set, assert that a `user-terminal` session still starts.
- With `ai_chat_disabled` absent, assert today's behavior.

**Acceptance Scenarios**:

1. **Given** `ai_chat_disabled` set, **When** a client requests an agent-kind provider
   session directly, **Then** it is refused and no process is spawned.
2. **Given** `ai_chat_disabled` set, **When** the user opens the Terminal, **Then** a
   shell starts as today.
3. **Given** `ai_chat_disabled` absent, **When** the user opens the AI chat, **Then** it
   works as it does today.

### User Story 7 - A lab user chooses when to restart into a new version (Priority: P7)

After the administrator installs a new version, a user's running backend
declares that an update is available. The user sees a notice and restarts when
it suits them, with a warning if runs are active.

**Why this priority**: The owner chose user-chosen updates. The open-source
side renders the notice and never restarts on its own.

**Independent Test**: Boot with an `update` capability naming a status route
and a restart route, and serve a status of
`{running_version, installed_version, update_available, runs_active}`.
Assert that:

- the status is polled every 60 seconds and on window focus;
- the notice renders only while `update_available` is true, and never takes
  focus;
- the warning appears when runs are active;
- Restart sends `POST` to the restart route, and follows the returned
  location, only after confirmation.

**Acceptance Scenarios**:

1. **Given** an update with runs active, **When** the user clicks Restart,
   **Then** a warning names the active runs before anything happens.
2. **Given** no `update` capability, **When** the app renders, **Then** no
   notice appears.
3. **Given** an `update` capability whose status says no update is
   available, **When** the app renders, **Then** no notice appears until a
   later poll says otherwise.

### User Story 8 - A server installs SciStudio from PyPI (Priority: P8)

An administrator installs `scistudio`, and then the enterprise package, with
pip; the wheel carries the built frontend.

**Why this priority**: Until now the desktop installers were the only
distribution, so a server had no official install path.

**Independent Test**: This is issue #2307's verification: the published wheel
contains the SPA, installs cleanly, and serves the GUI at `/`. Its version
`0.3.4a<N>` matches OTA build `N`.

**Acceptance Scenarios**:

1. **Given** OTA build N is published, **When** the admin runs
   `pip install scistudio==0.3.4aN`, **Then** it installs the same code with
   the SPA included.

### User Story 9 - Panel files pass any guard through the seam (Priority: P9)

When ADR-054 panel work resumes, panels register `/api/panels/t/` as a
self-authenticating prefix. Their per-mount token URLs then work on a guarded
enterprise backend without any Lab-specific middleware in this repository.

**Why this priority**: Panels are paused; the seam must still be shaped so
resuming them needs no guard changes.

**Independent Test**: This is ADR-054 SC-009, run against the fake guard. A
panel's entry, module imports, fonts, SDK and library files load under a
prefixed, guarded backend, and are refused after the context closes.

**Acceptance Scenarios**:

1. **Given** a guarded backend and an open panel context, **When** the frame
   loads its files, **Then** they load by token without a session cookie.

### Edge Cases

- A capability payload from a newer enterprise package names a capability the
  frontend does not know: the frontend ignores it and renders nothing for it.
- `identity` present but no logout URL: the user name renders without a
  Logout action.
- `transfer.inline_max_bytes` exceeded by a picked file: the UI uses the
  staged upload, never inline transfer.
- The adapter starts before the backend: it retries for a bounded time, then
  exits with a clear configuration error.
- The adapter's credential is rejected: it reports an authentication error
  naming the base URL. It never prints the credential.
- The loopback token file is missing, stale, or not readable only by the
  current user: the adapter refuses to use it and says why.
- `ai_chat_disabled` toggles while a session is open: the next session creation follows
  the new value, and an open session is not killed by the UI.
- A tutorial replay tab adopted under the `user-terminal` provider while
  `ai_chat_disabled` is set: it is still a terminal-kind session and is not refused.
  The frontend files it by `source`, as it does today, so it lands under the
  hidden AI Chat surface and cannot be seen. That gap, and Bring In My Work
  answering the refusal with HTTP 500 after writing its brief, are tracked in
  #2337.
- An update notice arrives while the user is typing in the editor: the notice
  never steals focus or restarts anything.
- The update status route fails, or answers something other than the status
  shape: the notice keeps its last answer and restarts nothing.
- A workflow with an AI Block runs while `ai_chat_disabled` is set: the
  block's tab is refused before anything is spawned, and the block reports
  the refusal as its error.
- A capability URL is declared with the service prefix already on it: it still
  resolves once, because the frontend's prefix join is idempotent. Editions
  declare route paths without the prefix.

## 3. Requirements

### Functional Requirements

- **FR-001**: With no enterprise arguments passed to `create_app`, the backend,
  bootstrap output, frontend and CLI MUST behave exactly as before this spec.
  No capability is declared by default and absence means off, so the enterprise controls stay hidden and the AI chat stays available.
- **FR-002**: The identity seam MUST cover everything the enterprise package
  needs: a replaceable guard, a startup/background hook inside the lifespan, a
  self-authenticating path registry matched after root-path handling, a
  capability declaration delivered to the frontend at boot, and a reusable
  guard contract suite with a test-only fake guard. Its detailed contract is
  the identity-seam spec of issue #2304.
- **FR-003**: The capability declaration MUST be a typed, versioned object with
  at least `identity`, `transfer`, `ai_chat_disabled` and `update` (Key Entities). The
  frontend MUST ignore unknown capabilities and treat a missing capability as
  off.
  - Every URL a capability carries MUST be a backend route path without the
    service prefix: a leading `/`, not `//`, no scheme, no whitespace,
    invisible or control characters, no backslashes, and no `.` or `..`
    segment, encoded or not. The backend refuses anything else when the
    edition builds the declaration, and the frontend reads it as off.
  - The frontend MUST resolve each URL under the service prefix exactly as it
    resolves its API calls, and MUST read a malformed capability as off.
- **FR-004**: When `identity` is present, the frontend MUST show the user name.
  If `logout_url` is given, it MUST also show a Logout action. `logout_url` is
  optional.
  - Logout sends a same-origin `POST` to `logout_url`, which answers
    `{"location": ...}`, and then navigates to that location. Only an `http`
    or `https` location is followed.
  - `logout_url` names the backend's own logout endpoint, which ends the
    backend session before any identity-provider logout. A plain GET
    navigation would let other sites force a logout.

  The open-source edition MUST NOT add login screens or account management.
- **FR-005**: When `transfer` is present, the frontend MUST offer a
  user-picked upload into the project through the existing
  `POST /api/data/upload` staged upload, with progress and cancel, whatever
  the file's size. It MUST also offer a download action: a `GET` on the
  capability's `download_url_template`, whose single `{path}` marker is
  replaced by the chosen file's URL-encoded project-relative path, resolved
  under the service prefix. The open-source edition MUST NOT implement the
  download endpoint.
- **FR-006**: When `ai_chat_disabled` is set, the frontend MUST hide the AI Chat surface
  in `BottomPanel` and the backend MUST refuse, with a clear error and no
  spawned process, any `/api/ai` PTY session whose provider is agent-kind in
  the provider registry. That covers every spawn path: the chat WebSocket, AI
  Block tabs, and Bring In My Work sessions. `GET /api/ai/status` MUST then
  run no agent binary, and report each agent provider as disabled. Terminal-kind sessions (`user-terminal`) MUST NOT be
  gated in any mode. When `ai_chat_disabled` is absent, behavior MUST be unchanged. Specs
  and docs MUST describe the gate as a default and an administrator policy,
  not as a security boundary.
- **FR-007**: When `update` is present, the frontend MUST poll `GET status_url`
  every 60 seconds and whenever the window regains focus. The route answers
  `{running_version, installed_version, update_available, runs_active}`.
  While `update_available` is true, the frontend MUST show a non-blocking
  notice with the running and installed versions, and the notice MUST NOT
  take focus. Restart MUST require explicit confirmation and MUST warn when
  runs are active. It then sends `POST restart_url` with
  `{"confirm_active_runs": <bool>}`. The flag is `true` only after the user
  has seen and accepted the runs-active warning, and `false` otherwise, so a
  backend can enforce the warning itself. The route answers
  `{"location": ...}`, and the frontend navigates there. A `409` answer means
  runs became active after the status read, and its body names them. The
  frontend then shows the warning with those names, requires confirmation
  again, and retries with `true`. The frontend MUST NOT restart or reload on its
  own.
- **FR-008**: The stdio MCP adapter (issue #2308) MUST serve MCP over stdio
  and forward `tools/list` to `GET /api/webmcp/tools` and `tools/call` to
  `POST /api/webmcp/call` on a configurable, prefix-aware base URL. It MUST
  preserve the Spec 1 result contract (`isError`, structured content,
  non-text content). It MUST carry the catalogue's project snapshot, report
  `409 stale_project_context` as an error, and emit
  `notifications/tools/list_changed` after re-fetching. It MUST NOT keep a
  tool registry of its own.
- **FR-009**: The adapter MUST accept a configured bearer credential, sent on
  every bridge request, for guarded backends. The enterprise edition supplies
  and validates a JupyterHub API token here. With no credential configured
  and a loopback base URL, it MUST read the per-user loopback token file of
  FR-010.
- **FR-010**: With the default guard, the backend MUST write its per-launch
  loopback token to a file readable only by the current OS user, in the
  per-user SciStudio state directory. It MUST remove the file on shutdown and
  MUST NOT write it when a replacement guard is installed.
- **FR-011**: The adapter MUST log only operation identifiers and outcomes
  (Spec 1 FR-007), never arguments or credentials. It MUST provide a command
  that prints ready-to-paste configuration for Claude Desktop, Claude Code and
  Codex.
- **FR-012**: The open-source wheel, with the built frontend, MUST be
  published to PyPI and GitHub Releases for every OTA build, as version
  `<base>a<N>` for OTA build `N` on the alpha channel (issue #2307). README
  MUST document `pip install scistudio` for servers.
- **FR-013**: When ADR-054 panel work resumes, panels MUST register
  `/api/panels/t/` through the seam's self-authenticating registry, and no
  Lab-specific middleware may be added to this repository (issue #2288).
- **FR-014**: Every open-source surface the enterprise package depends on MUST
  carry ADR-052 `provisional` status. A breaking change to it requires a
  changelog entry and a deprecation path.
- **FR-015**: Enterprise UI MUST live in the open-source frontend and render
  only from capabilities. No separate enterprise frontend bundle or runtime
  script injection is introduced.
- **FR-016**: `docs/specs/adr-055-lab-deployment.md` MUST be removed from this
  repository once PR #2292 has merged (issue #2303). References to it MUST
  point to this spec or to the identity-seam spec.

### Key Entities

- **CapabilitySet**: the declaration of FR-003, delivered at boot. Every URL
  in it is a backend route path without the service prefix.
  - `version` (integer; `1` for this shape).
  - `identity`: `{user, logout_url?}` or absent.
  - `transfer`: `{inline_max_bytes, download_url_template}` or absent. The
    template carries exactly one `{path}` marker. `inline_max_bytes` is
    the largest file the edition moves inline; the UI's own upload is always
    staged.
  - `ai_chat_disabled`: `true`, or absent (false). When true it gates agent-kind providers only,
    never the terminal.
  - `update`: `{status_url, restart_url}` or absent. The shape is dynamic,
    because update availability and active runs change while the backend
    runs. `GET status_url` answers an **UpdateStatus**,
    `{running_version, installed_version, update_available, runs_active}`,
    which the frontend polls and never stores. `POST restart_url` takes
    `{"confirm_active_runs": <bool>}` and answers `{location}`, or `409`
    naming the active runs when they are unconfirmed. This replaces the
    earlier static shape
    `{running_version, installed_version, runs_active, restart_url}`
    (umbrella #2321).

  It is produced by `create_app` from the caller's arguments and read by the
  frontend; it has no persistence.
- **AdapterConfig**: base URL, optional bearer credential, and log level. It is
  supplied by the AI app's MCP server configuration and holds no project
  identity: the project comes from the backend's catalogue snapshot.
- **LoopbackTokenFile**: the per-launch token, the backend's PID, and its
  port. It lives in the per-user state directory with owner-only permissions,
  and its lifetime is that of the backend.

## 4. Implementation Plan

### 4.1 Technical Approach

The work splits along the issues in the Change Summary.

- **Seam (#2304).** The seam lands first, because the UI, the `ai_chat_disabled`
  gating and the adapter's guarded mode all consume it.
- **Capability-gated UI.** One small `frontend/src/components/Enterprise/`
  area holds the identity chrome, the transfer controls and the update notice.
  `BottomPanel` consults `ai_chat_disabled`. Everything reads the capability accessor
  that #2304 adds, and nothing renders when a capability is absent. T-002 and
  T-003 ship together in #2322. The identity chrome, the Upload button and the
  update notice sit in the toolbar, outside its scrolling area. "Download to
  this computer" is an item in the project tree's context menu.
- **Agent-session refusal.** The `ai_chat_disabled` backend check sits in the
  provider dispatch of `scistudio.api.routes.ai_pty`, and in each spawn path
  before it: the chat WebSocket and the pre-spawned AI Block and Bring In My
  Work tabs. The application lifespan hands the capability to those paths. It
  keys on the registry's provider kind, so agent providers are refused and
  `user-terminal` passes, and the UI hides only the AI Chat surface.
- **Adapter (#2308).** A new CLI subcommand speaks MCP over stdio. Its HTTP
  side is a thin client of the existing bridge routes, and it reuses the
  Spec 1 adapter contract. The loopback token file is written by the default
  guard's setup in `create_app`.
- **Publishing (#2307).** A publish workflow is triggered from the OTA publish
  script; it is independent of the rest.
- **Panels (#2288).** Panel registration waits for ADR-054 to resume.

Enterprise-only behavior — the Hub guard, cookie and XSRF rules, Hub token
validation, transfer endpoints and tools, activity reporting, and restart
handling — stays in the private repository.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/api/app.py` | modify | Seam parameters (#2304); loopback token file on the default guard (FR-010) |
| `src/scistudio/api/spa.py` | modify | Capability delivery at boot, if the seam spec chooses bootstrap injection |
| `src/scistudio/api/routes/webmcp.py` | modify | Guard generalization (#2304); the bridge routes the adapter calls |
| `src/scistudio/api/routes/ai_pty/_state.py`, `websocket.py` | modify | `ai_chat_disabled` refusal of agent-kind providers only (FR-006) |
| `src/scistudio/cli/main.py` | modify | Register the adapter subcommand |
| `src/scistudio/cli/webmcp_adapter.py` | create | Stdio MCP adapter (FR-008 to FR-011) |
| `frontend/src/components/Enterprise/**` | create | Identity chrome, transfer controls, update notice |
| `frontend/src/components/BottomPanel.tsx` | modify | Hide the AI chat tab when `ai_chat_disabled` is set |
| `frontend/src/lib/api/data.ts` | modify | Upload progress and cancel hooks for the transfer picker |
| `frontend/src/lib/capabilities.ts` | modify | The full capability shape, route-path validation, and the download route builder |
| `frontend/src/components/Toolbar.tsx`, `frontend/src/components/ProjectTree.parts/ContextMenu.tsx` | modify | Place the identity chrome, Upload and the update notice; add "Download to this computer" |
| `src/scistudio/api/seam.py` | modify | `TransferCapability`, `UpdateCapability`, `ai_chat_disabled`, optional `logout_url`, route-path validation, and the versioned declaration |
| `src/scistudio/api/routes/ai_pty/engine.py`, `internal_routes.py` | modify | Refuse agent-kind providers in the AI Block and Bring In My Work spawn paths; register `/api/ai/pty/internal/` as self-authenticating |
| `tests/api/test_ai_pty_internal_guard.py`, `frontend/src/components/Enterprise/TransferControls.test.tsx`, `frontend/src/components/Enterprise/AiChatGate.test.tsx` | create | Worker callbacks under a replacement guard; transfer controls; the AI Chat gate |
| `README.md` | modify | Server install via pip (#2307) |
| `docs/specs/adr-055-lab-deployment.md` | delete | After #2292 merges (#2303) |
| `tests/cli/test_webmcp_adapter.py`, `tests/api/test_enterprise_capabilities.py`, `tests/api/test_ai_pty_capability.py`, `frontend/src/components/Enterprise/EnterpriseChrome.test.tsx` | create | Coverage for stories 1 and 3 to 6 |

### 4.3 Implementation Sequence

| Task | Title | Story | Issue | Depends on | Verification |
|---|---|---|---|---|---|
| T-001 | Identity seam, fake guard, contract suite, provisional API | US1, US2 | #2304 | — | seam suite; default-unchanged regression |
| T-002 | Capability-gated identity chrome, update notice, and `ai_chat_disabled` UI plus backend refusal | US3, US6, US7 | new UI issue | T-001 | `EnterpriseChrome.test.tsx`, `test_ai_pty_capability.py` |
| T-003 | Transfer controls (upload picker, progress, download action) | US4 | new UI issue | T-001; the enterprise transfer contract | frontend transfer tests |
| T-004 | Stdio MCP adapter and loopback token file | US5 | #2308 | T-001 for guarded mode | `test_webmcp_adapter.py` |
| T-005 | PyPI and GitHub Releases publishing | US8 | #2307 | — | #2307 workflow checks |
| T-006 | Panel prefix registration | US9 | #2288 | T-001; ADR-054 resumed | ADR-054 SC-009 |
| T-007 | Remove the old Lab spec and repoint references | — | #2303 | #2292 merged | full audit |

### 4.4 Verification Plan

- Default-unchanged regression across the API, frontend and desktop suites
  (US1).
- The #2304 contract suite against the fake guard, including root-path
  variants (US2, US9).
- Frontend tests for each capability present and absent (US3, US4, US6, US7).
- Backend tests that, with `ai_chat_disabled` set, agent providers spawn no process
  and `user-terminal` still spawns.
- Adapter tests: catalogue parity with the bridge, result-contract fixtures,
  stale-context handling, bearer credential, token-file permission refusal,
  and a scan confirming no credential appears in logs.
- `gate_record check` on each PR; full audit for the spec and README changes.

### 4.5 Risks And Rollback

- **The enterprise edition depends on open-source internals.** Mitigated by
  FR-014 (provisional status with deprecation) and by the enterprise
  repository running the contract suite against each open-source version it
  declares compatible.
- **Enterprise UI code is public.** The owner accepted this (option A). It is
  inert without capabilities, and security never relies on hiding UI; FR-006
  refuses on the backend.
- **Loopback token file exposure.** It is owner-only, per launch, removed on
  shutdown, and never written in enterprise mode.
- **PyPI versions are immutable.** The #2307 publish trigger skips existing
  versions, notice-only builds and backfills.
- **Rollback.** Every change is additive behind the default-off capabilities
  and the absent-argument defaults. Reverting a PR restores the prior
  behavior with no data migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: With no enterprise arguments, 100% of the existing API,
  frontend and desktop tests pass unchanged, and the default capability
  snapshot shows every enterprise capability off.
- **SC-002**: The contract suite passes against the fake guard, and the
  enterprise repository reports the same suite passing against its real
  guard.
- **SC-003**: For each capability, tests cover both presence and absence,
  with zero enterprise controls rendered when absent.
- **SC-004**: With `ai_chat_disabled` set, direct agent-provider session requests spawn
  zero processes, while 100% of `user-terminal` session requests still start.
- **SC-005**: An AI app using the adapter lists exactly the tools
  `GET /api/webmcp/tools` returns, with a successful round trip against a
  local backend and against a guarded backend.
- **SC-006**: Every OTA build published after #2307 merges has a matching
  PyPI version within one workflow run.

## 6. Assumptions

- The enterprise package composes onto `create_app` and runs the contract
  suite; it never patches open-source code. (source: owner)
- JupyterHub API tokens are the lab credential for the adapter, validated by
  the enterprise guard. (source: owner)
- The in-app AI chat is off by default on a lab server, and an administrator
  may enable it. The plain terminal stays available. (source: owner)
- The Terminal and the AI chat share the `/api/ai` PTY routes and differ by
  the registry's provider kind. (source: existing-system)
- Uploads reuse `POST /api/data/upload` unchanged; the enterprise edition
  adds the download endpoint. (source: owner; existing-system)
- The identity-seam spec from #2304 is the detailed contract, and this spec
  defers to it wherever they overlap. (source: spec)
- A loopback backend's per-user state directory is writable only by its
  owner on every supported OS. (source: inferred; verified by T-004)
