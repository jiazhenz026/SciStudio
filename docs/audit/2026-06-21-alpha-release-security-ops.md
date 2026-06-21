# A6 Security/Ops Alpha Release Audit

Audit identity:

- Agent: A6-security-ops
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1733
- Umbrella PR: #1734 `[DO NOT MERGE]`
- Branch/worktree: `track/alpha-release-audit-20260621` in `/Users/jiazhenz/SciStudio-alpha-audit-20260621`
- Audited baseline: `HEAD=410e12530a1d3420e912fa666c3f756550537ce0`; dispatch baseline `origin/main=1948ab2c18fafeb54c82c77646a2f00665e16332`
- Scope: core runtime security and operational readiness across `src/scistudio/api/**`, `src/scistudio/desktop/**`, `src/scistudio/ai/**`, `src/scistudio/engine/**`, `src/scistudio/core/**`, `src/scistudio/cli/**`, relevant tests, and security/governance/operational docs.

## Findings

### P0 - Alpha Release Block

#### P0-1 - Default CLI launches an unauthenticated control-plane API on all interfaces

Recommendation: block alpha until default interactive/local modes bind to loopback only, or until a real authentication/host-guard story is in place and owner-risk-accepted.

Evidence:

- The alpha rubric classifies a default-scenario security issue that can expose secrets, execute unintended commands, or write outside intended project boundaries as P0 (`docs/audit/2026-06-21-alpha-release-criteria.md:61-70`).
- `scistudio serve` defaults to `host="0.0.0.0"` and passes that directly to `uvicorn.run` (`src/scistudio/cli/main.py:352-362`).
- Non-bundled `scistudio gui` also binds `server_host = "0.0.0.0"` while advertising `localhost` to the browser (`src/scistudio/cli/main.py:373-425`).
- The CLI tests codify these defaults: `tests/cli/test_cli.py:119-128` asserts `serve` uses `0.0.0.0`; `tests/cli/test_cli.py:173-181` asserts non-bundled `gui` uses `0.0.0.0`; bundled mode alone is loopback-bound (`tests/cli/test_cli.py:210-223`).
- The FastAPI app installs CORS but no API-wide authentication or trusted-host guard (`src/scistudio/api/app.py:240-258`). CORS is not an authentication boundary for direct LAN clients or non-browser clients.
- The exposed app registers core mutation and process-capable routers, including filesystem, projects, AI, AI PTY, runs, and git (`src/scistudio/api/app.py:261-285`).
- Exposed mutation/process examples include git commit (`src/scistudio/api/routes/git.py:320-326`), git restore (`src/scistudio/api/routes/git.py:375-380`), native OS dialog launch (`src/scistudio/api/routes/filesystem.py:620-658`), and user-launched AI PTY WebSocket spawning (`src/scistudio/api/routes/ai_pty/websocket.py:34-67`, `src/scistudio/api/routes/ai_pty/websocket.py:108-129`).
- A targeted search for host/auth controls found only CORS and the PTY internal IPC token. The token protects worker-to-engine internal PTY routes (`src/scistudio/api/routes/ai_pty/internal_routes.py:29-49`, `src/scistudio/api/routes/ai_pty/internal_routes.py:56-68`), not the public REST/WebSocket control plane.

Impact:

In the default CLI path, another process on the same network can reach the local SciStudio API. That API can inspect project data, mutate project files, run git operations, launch native dialogs, and open PTY-backed AI agent sessions. This is beyond "alpha instability"; it is a default operational exposure of the local control plane.

Required fix:

- Make `serve` and non-bundled `gui` loopback by default.
- Require an explicit `--host 0.0.0.0` or equivalent unsafe opt-in for LAN binding.
- Add a regression test asserting default loopback behavior.
- If LAN serving is intended for alpha, add an auth/token gate and document the threat model before release.

#### P0-2 - macOS native-dialog endpoint interpolates request data into AppleScript, enabling command injection

Recommendation: block alpha until macOS dialog script construction escapes AppleScript strings or avoids string interpolation.

Evidence:

- The request model accepts `default_filename` directly from the API body (`src/scistudio/api/routes/filesystem.py:322-330`).
- The macOS implementation interpolates `initial_dir` and `default_filename` into AppleScript double-quoted strings without escaping (`src/scistudio/api/routes/filesystem.py:517-535`), then executes the script through `osascript -e` (`src/scistudio/api/routes/filesystem.py:544-550`).
- The route passes request-controlled `body.default_filename` to the macOS implementation (`src/scistudio/api/routes/filesystem.py:620-658`).
- The Windows path has a dedicated escaping helper for comparable request-controlled values (`src/scistudio/api/routes/filesystem.py:350-378`), which highlights the missing macOS equivalent.
- Existing native-dialog tests cover happy path, missing platform commands, and timeout behavior, but do not assert AppleScript escaping for macOS (`tests/api/test_filesystem.py:102-258`; `tests/api/test_filesystem_dialog.py:62-109`).

Non-destructive repro result:

```text
PYTHONPATH=src python - <<'PY'
from scistudio.api.routes import filesystem as fs

captured = {}
class FakeCompleted:
    stdout = ''
    stderr = ''
    returncode = 0

def fake_run(cmd, **kwargs):
    captured['cmd'] = cmd
    return FakeCompleted()

old_run = fs.subprocess.run
fs.subprocess.run = fake_run
try:
    fs._native_dialog_macos('save_file', '/tmp', 'safe" & do shell script "echo injected" & "')
finally:
    fs.subprocess.run = old_run
print(captured['cmd'][0:2])
print(captured['cmd'][2])
PY

['osascript', '-e']
choose file name with prompt "Save As" default name "safe" & do shell script "echo injected" & "" default location POSIX file "/tmp"
```

Impact:

On macOS, an API caller can turn a filename string into AppleScript code. Combined with P0-1, this becomes unauthenticated local-network command execution in default non-bundled CLI modes. Even after loopback binding is fixed, the endpoint remains unsafe for any local client path that can reach it.

Required fix:

- Add AppleScript string escaping for every interpolated value, or pass values through a safer mechanism.
- Add tests for quote, backslash, newline, and AppleScript operator injection in `default_filename` and `initial_dir`.

### P1 - Pass Only With Must Fix

#### P1-1 - MCP `inspect_data` / `preview_data` can read arbitrary paths outside the active project

Recommendation: must fix before alpha or owner-risk-accept explicitly. MCP inspection tools should reject storage references outside the active project root unless a narrowly documented external-artifact policy exists.

Evidence:

- The MCP path-hardening helper says user-supplied paths must resolve under `ctx.project_dir` and reject traversal (`src/scistudio/ai/agent/mcp/_context.py:119-145`, `src/scistudio/ai/agent/mcp/_context.py:148-194`).
- `inspect_data` constructs `Path(sref.path)` directly and stats it without `_resolve_project_path` / `_safe_under` (`src/scistudio/ai/agent/mcp/tools_inspection/read.py:103-124`).
- `preview_data` constructs `Path(sref.path)` directly, checks existence, and dispatches to preview readers without project confinement (`src/scistudio/ai/agent/mcp/tools_inspection/read.py:166-226`).
- Text preview reads the first 4096 bytes of the supplied path (`src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:209-217`); artifact preview can inline image bytes when under the cap (`src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:220-229`).
- The cap constants limit size, not path scope (`src/scistudio/ai/agent/mcp/tools_inspection/_helpers.py:16-23`).
- Existing inspection tests exercise arbitrary `tmp_path` references and caps, but do not assert outside-project rejection (`tests/ai/test_mcp_tools_inspection.py:95-190`).

Non-destructive repro result:

```text
PYTHONPATH=src python - <<'PY'
import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from scistudio.ai.agent.mcp import _context, tools_inspection

@dataclass
class StubRuntime:
    block_registry: Any = field(default_factory=object)
    type_registry: Any = field(default_factory=object)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None
    active_workflow_id: str | None = None
    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    project = root / 'project'
    project.mkdir()
    outside = root / 'outside-secret.txt'
    outside.write_text('SECRET_OUTSIDE_PROJECT', encoding='utf-8')
    _context.set_context(StubRuntime(_project_dir=project))
    try:
        result = asyncio.run(tools_inspection.preview_data(
            ref={'backend': 'filesystem', 'path': str(outside), 'metadata': {'type_chain': ['DataObject', 'Text']}},
            fmt='text',
        ))
        print('preview_status=allowed')
        print('preview_content=' + result.payload.get('content', ''))
    finally:
        _context.set_context(None)
PY

preview_status=allowed
preview_content=SECRET_OUTSIDE_PROJECT
```

Impact:

The embedded agent can inspect or preview local files outside the active project if it receives or fabricates a `StorageReference` with an absolute path. This violates project isolation expectations and creates a local secret/data leakage path.

Required fix:

- Resolve MCP inspection paths through `_resolve_project_path` or an equivalent storage-reference validator.
- Add tests proving `inspect_data`, `preview_data`, and preview dispatch reject outside-project paths and symlink escapes.
- If SciStudio intentionally supports external absolute artifact refs, define that policy and gate it by reference provenance, not arbitrary MCP caller input.

#### P1-2 - Default branch has 18 open Dependabot alerts, including one high severity alert

Recommendation: must triage before alpha. Close, dismiss with reason, or owner-risk-accept the alerts in release evidence.

Evidence:

The observed GitHub push warning was classified from repository metadata with:

```text
gh api 'repos/zjzcpj/SciStudio/dependabot/alerts?state=open' --paginate --jq '.[] | [.number, .state, .security_advisory.severity, .dependency.package.ecosystem, .dependency.package.name, .security_advisory.ghsa_id] | @tsv'
```

Result: 18 open alerts on `main`.

- High: 1 (`npm vite`, GHSA-fx2h-pf6j-xcff, alert #30)
- Medium: 14 (`npm vite` alert #31, plus `npm dompurify` alerts #38, #25, #23, #22, #21, #14, #13, #12, #11, #10, #9, #8, #7)
- Low: 3 (`npm dompurify` alerts #26, #24, #20)

Impact:

This is release/security evidence on the protected default branch. Package and extension completeness is out of scope, but a high-severity frontend dependency alert on the default branch should not be silently ignored for an internal alpha release.

Required fix:

- Resolve or explicitly dismiss/risk-accept all open alerts before release signoff.
- At minimum, resolve or risk-accept the high-severity `vite` alert and record the decision in release evidence.

### P2 - Pass, Good To Fix Before Broader Testing

#### P2-1 - MCP `get_block_logs` accepts unsanitized path components

Evidence:

- `get_block_logs` builds `log_root = project_dir / "logs" / run_id` and stream paths from `block_id` without validating path components (`src/scistudio/ai/agent/mcp/tools_inspection/read.py:335-360`).
- The read helper then tails existing files up to 16 KiB (`src/scistudio/ai/agent/mcp/tools_inspection/read.py:364-380`).
- Existing tests cover missing logs and happy path only (`tests/ai/test_mcp_tools_inspection.py:267-286`).

Impact:

The fixed `.stdout` / `.stderr` suffix limits exploitability, but `../` segments in `run_id` or `block_id` can redirect log reads outside `project/logs` if a matching suffixed file exists. This is a smaller variant of the MCP path confinement issue.

Recommended fix:

- Treat `run_id` and `block_id` as identifiers, not paths. Reject separators and traversal tokens.
- Add tests for `../`, absolute-path, and symlink traversal attempts.

#### P2-2 - Explicit `output_dir` can write runtime artifacts outside the project root

Evidence:

- `_derive_output_dir` honors `config["output_dir"]` directly, creates the directory, and returns it without project confinement (`src/scistudio/engine/runners/local.py:106-112`).
- The project-scoped default path is used only when explicit `output_dir` is absent (`src/scistudio/engine/runners/local.py:114-128`).
- The worker receives this `output_dir` and auto-flushes outputs through it (`src/scistudio/engine/runners/local.py:280-285`; `src/scistudio/engine/runners/worker.py:467-473`).
- Tests assert the project-scoped default and temp fallback, but not explicit outside-project rejection (`tests/engine/test_local_runner.py:431-454`).
- Workflow path portability currently preserves outside-project absolute paths rather than rejecting them (`tests/workflow/test_path_portability.py:41-53`, `tests/workflow/test_path_portability.py:109-117`).

Impact:

This may be intended for user-selected export/output directories, but core runtime auto-flush artifacts and project isolation are currently governed by arbitrary block config. That should either be explicitly allowed and documented or confined for internal alpha.

Recommended fix:

- Decide whether explicit `output_dir` is a project-internal runtime path or a user-selected external export path.
- If runtime-internal, confine to the project root.
- If external output is intended, require explicit user action/provenance and document the isolation exception.

#### P2-3 - Arrow/Parquet writes are direct-to-final-path while adjacent storage paths have atomic helpers

Evidence:

- `ArrowBackend.write` writes directly with `pq.write_table(table, ref.path)` (`src/scistudio/core/storage/arrow_backend.py:38-50`).
- Filesystem storage uses a temp file plus `os.replace` (`src/scistudio/core/storage/filesystem.py:50-78`).
- Composite storage stages all slots and swaps via `atomic_replace_dir` (`src/scistudio/core/storage/composite_store.py:70-90`).
- Shared `atomic_path` exists for third-party writers that need a filesystem path (`src/scistudio/utils/atomic_io.py:161-177`).

Impact:

For new unique artifact paths, a crash usually leaves an orphan partial file that may never be referenced. For overwrite or direct storage use, a crash/interruption during Parquet write can leave a partial final file. This is not enough to block alpha on its own, but it is an artifact integrity gap worth fixing before broader testing.

Recommended fix:

- Route Arrow/Parquet writes through `atomic_path(..., suffix=".parquet")`.
- Add a failure-injection test proving pre-existing Parquet content survives a failed write.

### P3 - Good To Fix

No P3-only findings were identified in this pass.

## Positive Controls Observed

- Project tree browsing rejects `..` and verifies resolved paths stay under the project root (`src/scistudio/api/routes/filesystem.py:122-176`).
- Universal browse/stat/reveal paths are confined to home or system temp via realpath/commonpath (`src/scistudio/api/routes/filesystem.py:41-65`), and reveal uses argv lists rather than a shell (`src/scistudio/api/routes/filesystem.py:291-307`).
- Project file GET/PUT share a project-root sandbox, extension allowlist, UTF-8/size checks, and same-directory temp-plus-rename writes (`src/scistudio/api/routes/projects.py:184-227`, `src/scistudio/api/routes/projects.py:230-270`, `src/scistudio/api/routes/projects.py:286-391`).
- Uploads stream in 1 MiB chunks with a 2 GB cap and cleanup on failure (`src/scistudio/api/routes/data.py:50-83`).
- Preview resource saves require absolute destinations and reuse the safe-path allowlist (`src/scistudio/api/routes/data.py:250-280`).
- App shutdown stops the workflow watcher, cancels active run tasks, terminates registered subprocesses, stops MCP, clears MCP context, and releases metadata-store state (`src/scistudio/api/app.py:175-221`).
- MCP lifecycle uses a project-local socket and stops/rebinds on project changes (`src/scistudio/api/mcp_lifecycle.py:24-77`).
- PTY `project_dir` validation requires absolute existing directories and confines to the active project when MCP context is present (`src/scistudio/api/routes/ai_pty/validation.py:14-58`).
- PTY spawn uses argv lists, a cleaned child environment, `start_new_session=True`, and process-tree cleanup (`src/scistudio/ai/agent/terminal.py:129-144`, `src/scistudio/ai/agent/terminal.py:239-252`, `src/scistudio/ai/agent/terminal.py:391-459`).
- Local block subprocesses use `asyncio.create_subprocess_exec`, not a shell, and run with project-root cwd when available (`src/scistudio/engine/runners/local.py:288-335`).
- Process registry validates PID identity before shutdown termination, reducing PID-reuse kill risk (`src/scistudio/engine/runners/process_handle.py:112-127`, `src/scistudio/engine/runners/process_handle.py:155-179`).

## Command Evidence

Targeted tests:

```text
PYTHONPATH=src pytest tests/api/test_filesystem.py tests/api/test_file_endpoints.py tests/api/routes/ai_pty/test_validation.py tests/api/routes/ai_pty/test_engine.py tests/ai/test_mcp_tools_disk_integration.py tests/ai/test_mcp_tools_inspection.py tests/engine/test_local_runner.py tests/engine/test_process_handle.py tests/core/test_storage.py tests/core/test_lineage_store_integrity.py -q
```

Result: test bodies passed, but the command exited non-zero because the repository coverage gate (`fail-under=70`) is not meaningful for this targeted subset.

```text
PYTHONPATH=src pytest tests/api/test_filesystem.py tests/api/test_file_endpoints.py tests/api/routes/ai_pty/test_validation.py tests/api/routes/ai_pty/test_engine.py tests/ai/test_mcp_tools_disk_integration.py tests/ai/test_mcp_tools_inspection.py tests/engine/test_local_runner.py tests/engine/test_process_handle.py tests/core/test_storage.py tests/core/test_lineage_store_integrity.py -q --no-cov
```

Result: all targeted tests passed; 4 Windows-only tests were skipped.

Targeted security repros:

- MCP outside-project preview repro: `preview_status=allowed`, `preview_content=SECRET_OUTSIDE_PROJECT`.
- macOS AppleScript injection repro: captured `osascript -e` payload contained `do shell script "echo injected"` from `default_filename`.

Repository/security metadata:

```text
git rev-parse HEAD
410e12530a1d3420e912fa666c3f756550537ce0

git rev-parse origin/main
1948ab2c18fafeb54c82c77646a2f00665e16332

gh repo view --json nameWithOwner,defaultBranchRef,url
{"defaultBranchRef":{"name":"main"},"nameWithOwner":"zjzcpj/SciStudio","url":"https://github.com/zjzcpj/SciStudio"}
```

Dependabot alert query classified the observed push warning as 18 open alerts on `main`: 1 high, 14 medium, 3 low.

Search/read commands used:

- `rg --files` over scoped source and test directories.
- `rg` scans for subprocess/PTY/process/env/log/path/storage/security patterns across scoped source/tests/docs.
- Targeted `nl -ba ... | sed -n ...` reads for all cited files and lines.

## Recommendation

Block.

The default all-interface unauthenticated API exposure and macOS native-dialog command injection meet the alpha rubric's P0 criteria. The MCP outside-project read path and open default-branch Dependabot alerts are additional must-fix or explicit owner-risk-acceptance items before any internal alpha release signoff.
