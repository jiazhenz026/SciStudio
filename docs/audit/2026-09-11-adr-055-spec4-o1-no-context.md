# Audit: ADR-055 Identity Seam And Enterprise Capabilities (no-context)

- Date: 2026-09-11
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2322-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2322-no-context`
- Base commit audited: `79cfe2b7d` (tip of `origin/feat/2322-enterprise-ui`)
- Surfaces under audit: `src/scistudio/api/seam.py`, `src/scistudio/api/spa.py`,
  `src/scistudio/api/app.py`, `frontend/src/lib/capabilities.ts`,
  `frontend/src/components/Enterprise/**` and its hosts (`Toolbar.tsx`,
  `BottomPanel.tsx`, `ProjectTree.parts/ContextMenu.tsx`,
  `frontend/src/lib/api/data.ts`), `src/scistudio/api/routes/ai_pty/**`, the
  seam's project-access helpers and the internals they wrap
  (`src/scistudio/ai/agent/mcp/tools_workspace.py`,
  `src/scistudio/api/runtime/_file_writes.py`, `src/scistudio/api/routes/data.py`),
  and their tests.
- Judged against: `docs/specs/adr-055-identity-seam.md`,
  `docs/specs/adr-055-enterprise-support.md`, `docs/adr/ADR-055.md`,
  `docs/adr/ADR-052.md`, `CHANGELOG.md`, and the generated reference pages
  for `scistudio.api.app` and `scistudio.api.seam`.
- Context used: repository files, `git diff origin/main...HEAD -- <paths>`,
  and commands run for this audit. No issue, PR, checklist, dispatch prompt,
  commit message or manager summary was read.

## 1. Change Summary

This report is the only file this change adds, with its gate ledger. It is a
no-context audit of the identity seam as an edition consumes it behind a
replacement guard: the capability declaration and its UI, the AI PTY routes
and their `ai_chat_disabled` gate, the self-authenticating registry, and the
project-access helpers.

**Recommendation: block.** One P1 lets an unauthenticated client open a shell
on a guarded backend. It follows from the registry matching the bare prefix
while a parameterized route claims that same path. Five P2 findings concern
URL confinement, the author blacklist, the check-then-write composition, the
`ai_chat_disabled` refusal on the Bring In My Work route, and the upload
listener's documented semantics. Everything else checked agrees: signatures,
the public-surface snapshot, the generated reference, the changelog, and
script safety of the capability declaration. The tests pass (Section 5).

## 2. Findings

### P1-1 — `/api/ai/pty/internal` itself is an unauthenticated PTY WebSocket, and it bypasses every guard

`internal_routes.py:64` registers `/api/ai/pty/internal/` as a
self-authenticating prefix. `is_self_authenticating_path` matches a path equal
to the prefix as well as paths below it (`seam.py:317`; identity-seam spec
edge cases: "A path equal to the prefix itself matches; with no route there it
is a 404"). But there is a route there. `WS /api/ai/pty/{tab_id}`
(`websocket.py:35`) accepts `tab_id = "internal"`, and that handler performs
no authentication of its own. With a replacement guard installed,
`GuardDispatchMiddleware` (`seam.py:201`) sends
`/api/ai/pty/internal?provider=user-terminal&project_dir=...` straight to the
route, which spawns a shell.

Evidence (throwaway probe, not committed): with `create_app(guard=FakeCookieGuard)`
and `_spawn` replaced by a recorder, an ordinary `/api/ai/pty/tab-1` WebSocket
is refused by the guard, but `/api/ai/pty/internal` with no cookie receives
`{"type": "stdout", "data": "READY\n"}` and the recorder logs
`['user-terminal']`. The same happens under `/user/alice/scistudio`.

Impact in the enterprise deployment:

- Anyone who can reach the user's server URL through the Hub proxy gets a
  shell running as that user. They need only an existing directory for
  `project_dir`; `_validate_project_dir` confines it to the active project,
  whose path is guessable.
- When the administrator has left the AI chat enabled, the same request with
  an agent provider and `dangerous=true` starts that agent CLI with
  permissions bypassed.

Contract breaks:

- Identity-seam FR-011 and FR-022: "Every route under the prefix MUST check the
  engine IPC token on every request".
- The spec's edge-case premise that the bare prefix leads to a 404.
- `internal_routes.py:60` ("A route added under this prefix MUST check the IPC
  token") is honored by the two POST routes only.

Test gap: `test_ai_pty_internal_guard.py` checks `/api/ai/pty/tab-1`,
`/api/ai/pty/internalx/notify` and `/api/ai/status`, never the bare prefix.
It also enumerates only routes whose path *starts with* the prefix plus `/`,
so a parameterized sibling route that matches the prefix is invisible to it.

Options, for the owner to choose:

- stop matching the prefix itself, so only descendants bypass;
- move the internal routes to a path no parameterized route can claim;
- refuse `tab_id` values that collide with registered prefixes.

Whichever is chosen, add a regression that asks the app's router which route
serves each registered prefix and a path below it, under the fake guard.

### P2-1 — Capability URLs may carry dot segments that leave the service prefix

`_validate_route_path` (`seam.py:334`) and `isRoutePath`
(`capabilities.ts:91`) accept `.` and `..` segments, including
percent-encoded ones. Accepted, per the probe:

- `/api/../../hub/logout`
- `/%2e%2e/%2e%2e/hub/logout`
- `/./api/x`

`apiUrl` prefixes them, and WHATWG URL parsing then resolves the dot segments
(Node probe: `/user/a/scistudio/../../hub/api/x` → `/user/hub/api/x`;
`.../api/%2e%2e/%2e%2e/%2e%2e/hub/logout` → `/user/hub/logout`). So a logout or
restart `POST` with same-origin credentials, the status poll, or a download
can land outside the user's service prefix, on the Hub or another user's
server.

The docs promise otherwise:

- identity-seam FR-014 says every URL MUST be "a backend route path without
  the service prefix";
- Spec 4 FR-003 says the frontend MUST resolve each URL under the service
  prefix;
- the self-authenticating registry already rejects `.` and `..` segments
  (FR-008), so the two route-path rules in one module disagree.

`NOT_ROUTE_PATHS` in `test_enterprise_capabilities.py` and
`capabilities.test.ts` has no dot-segment case. The values come from edition
code, so this is misconfiguration exposure rather than attacker input.

### P2-2 — On Windows, an NTFS stream suffix passes the author blacklist for a new workflow YAML

`check_author_path(root, "workflows/new.yaml::$DATA")` returns the path
instead of refusing with `protected_workflow_yaml`. Writing to the returned
path creates `workflows/new.yaml` (probe: directory listing `['new.yaml']`).
`confine_to_project` accepts the same suffix, so `write_project_file` would
write it.

An existing file is still caught: `workflows/existing.yaml::$DATA` is
refused, because `realpath` canonicalizes existing files. So is a trailing dot
or space on the name. The gap is in `_blacklist_refusal`
(`tools_workspace.py:395`), which predates this branch. It is now a public
provisional contract (identity-seam FR-025, "MUST apply the author tools' own
confinement and Spec 2 blacklist"). It is Windows-only: lab servers are
typically Linux, but the desktop edition's own author tools share the
function.

### P2-3 — `check_author_path` and `write_project_file` resolve the same `rel_path` differently

`_resolve_author_path` runs `os.path.expanduser` (`tools_workspace.py:435`).
`write_project_file` joins `root / rel_path.strip()` literally
(`seam.py:689`). The seam documents the composition "call
`check_author_path` first for an agent's write" (FR-026, `seam.py:670`), so
the check can validate one file while the write changes another.

Probe, with the home directory at `<project>/a/b`: `~/../data/x.csv` is
checked as `<project>/a/data/x.csv` and passes, but the write target is
`<project>/data/x.csv`, a `protected_data_dir` path. The precondition is
contrived. Still, any project entry whose name starts with `~` resolves
differently in the two helpers, and nothing in the spec, the docstrings or
the tests states which interpretation an edition gets.

### P2-4 — Bring In My Work under `ai_chat_disabled` writes a brief, then answers 500

`POST /api/work-import/sessions` writes the session brief into the project
(`work_import.py:286`) and spawns last. With `ai_chat_disabled` set,
`_open_prespawned_tab` raises `AgentSessionsDisabledError`. That class is a
`RuntimeError` (`_state.py:130`), and the route maps every non-cap
`RuntimeError` to **500** (`work_import.py:303-306`).

That is the failure shape the route's own comment says it was changed to
avoid: "a bare 500 ... plus a brief on disk for a session that never started"
(`work_import.py:239-256`). Spec 4 FR-006 asks for "a clear error". This
refusal is a policy outcome, not a server fault.

`test_ai_pty_capability.py` covers the helper (`open_work_import_tab`) but not
the HTTP route, so neither the status nor the leftover brief is tested.
`work_import.py` is not in Spec 4's `governs.files`. Related UX note: the
toolbar's Bring In My Work entry stays visible while the AI Chat tab is
hidden.

### P2-5 — The upload listener's `started` event fires only after the whole body has arrived

Identity-seam FR-027 and the `add_upload_listener` docstring say `started`
fires "when the staged upload begins, so an edition can count uploads in
flight as activity", with a size that may be 0 when unknown.

`upload_data` takes `UploadFile = File(...)`, so FastAPI parses the entire
multipart body before the handler runs. `started` comes after the network
transfer. Probe: a 3 MiB upload reports `('started', 3145728)`, the full body.
For a large upload from a laptop, the long part is invisible to listeners, so
a Hub activity reporter relying on it can see an idle backend mid-upload.

`test_upload_listeners_hear_an_upload_start_and_complete` accepts
`sizes["started"] in (0, len(body))`, so it cannot detect this. Either the
docs should say what `started` means, or the route has to stream the body
itself.

### P3 findings

- **P3-1 — The backend and frontend route-path rules differ on non-ASCII
  whitespace.** Python `str.isspace` and JS `/\s/u` disagree:
  - `/api/x\ufeff` is accepted by the backend and read as off by the frontend,
    so a capability that `create_app` accepted silently disappears;
  - `\x85` behaves the other way round;
  - C1 controls (`\x80`) pass both.

  FR-016 says the frontend applies "the backend's route-path rule".
- **P3-2 — The base-path bootstrap is not script-safe.**
  `_templated_index_response` serializes `window.__SCISTUDIO_BASE_PATH__` with
  plain `json.dumps` (`spa.py:183`). A root path containing `</script>`
  closes the element (probe). The value is operator configuration and
  predates this branch. `_script_safe_json`, already used for capabilities,
  could cover all three assignments.
- **P3-3 — `write_project_file` has an undocumented keyword.** It accepts
  `changed_by="edition"` (`seam.py:663`), which is not in the signature of
  FR-026 or in the changelog entry for the provisional name.
- **P3-4 — An embedded NUL is not refused.** `check_author_path(root,
  "a\x00b")` returns a path. The later write raises `ValueError`, which a tool
  surfaces as a withheld generic error over the bridge rather than a
  `ToolRefusal`.
- **P3-5 — Status probes still run agent binaries.** With `ai_chat_disabled`
  set, `GET /api/ai/status` still runs `<cli> --version` and auth-status
  commands (`ai.py:226`, `ai.py:275`). FR-006 scopes the gate to PTY
  sessions, so this is consistent. A reader of "no spawned process" in US6
  may still expect otherwise; one sentence in the spec would settle it.
- **P3-6 — Regenerating the reference adds one blank line.** Running
  `scripts/docs/build_reference.py --generate-only` on Windows appends one
  trailing blank line to all 26 generated pages, including pages this branch
  never touched. The content is otherwise identical, so there is no sign of
  hand-editing. This is a generator artifact, not a branch finding. The
  regenerated pages were reverted.

## 3. What Agrees

- **Surface.** `seam.__all__` has 19 names and `app.__all__` has
  `create_app`: twenty symbols, nineteen stability-marked. That matches
  identity-seam FR-018 and SC-006, and `tests/api/test_public_surface.py`
  passes.
- **Generated reference.** The pages for `scistudio.api.app` and
  `scistudio.api.seam` regenerate identically, apart from P3-6.
- **Changelog.** The provisional break (`transfer=True` now raises
  `TypeError`) is in the changelog, and so are the five project-access names.
- **Script safety.** The capability declaration escapes `<`, `>`, `&`,
  U+2028 and U+2029 (`spa.py:122`), and it is emitted only when a capability
  is on. Both are tested.
- **Off-origin forms.** `//host`, `/\host`, schemes, whitespace and control
  characters are refused on both sides, and tested.
- **`ai_chat_disabled` gating.** It is checked in the WebSocket route before
  any join or spawn, in the pre-spawned body, and again in `_spawn` as a
  backstop. It keys on registry kind. The Terminal is its own bottom tab,
  outside the hidden AI Chat surface (`BottomPanel.tsx:126`), and a tutorial
  replay is still joined.
- **Worker callbacks.** Both POST routes under the internal prefix check the
  IPC token first.
- **Confinement.** Traversal (`..\\..\\x`), UNC paths and absolute paths
  elsewhere are refused. A drive-relative `C:x` stays inside the project.
- **Downloads.** The download path comes from project-relative tree paths
  and is encoded with `encodeURIComponent`.
- **Default behavior.** `create_app()` with no arguments injects no
  declaration and keeps the loopback token.

## 4. Docs Versus Code

- **Docs claiming behavior the code lacks:**
  - FR-022 and the `internal_routes.py` comment, that every route under the
    prefix checks the token (P1-1);
  - FR-014 and Spec 4 FR-003, that URLs resolve under the service prefix
    (P2-1);
  - FR-027, that `started` counts uploads in flight (P2-5).
- **Code behavior the governing docs do not cover:**
  - the bare prefix is routable (P1-1);
  - `expanduser` in the check but not in the write (P2-3);
  - the work-import status for a policy refusal (P2-4);
  - the `changed_by` keyword (P3-3).
- **Documented contracts without tests:**
  - the bare-prefix route under a replacement guard (P1-1);
  - dot-segment URLs (P2-1);
  - the Bring In My Work HTTP route under `ai_chat_disabled` (P2-4);
  - the timing of `started` (P2-5).

## 5. Checks Run

- `pytest` on the backend suites below, with `PYTHONPATH=src` and
  `--no-cov`: **352 passed**.
  - `tests/api/test_identity_seam.py`
  - `tests/api/test_enterprise_capabilities.py`
  - `tests/api/test_ai_pty_capability.py`
  - `tests/api/test_ai_pty_internal_guard.py`
  - `tests/api/test_seam_project_access.py`
  - `tests/api/test_public_surface.py`
  - `tests/api/test_webmcp.py`
  - `tests/api/test_root_path.py`
- `npx vitest run src/lib/capabilities.test.ts src/components/Enterprise
  src/components/BottomPanel.test.tsx`: **134 passed**, in 5 files.
- `scripts/docs/build_reference.py --generate-only`: output matches apart
  from P3-6, and was reverted.
- Throwaway probes outside the repository, not committed: the bare-prefix
  WebSocket at both mounts, Windows path quirks, the `~` mismatch, dot-segment
  URLs, base-path script safety, and listener timing.
- Sentrux: N/A, because the MCP server is not available in this session.
