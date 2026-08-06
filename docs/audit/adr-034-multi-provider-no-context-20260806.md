# Audit: ADR-034 Multi-Provider Agent Chat (no-context)

- Date: 2026-08-06
- Persona: audit_reviewer, `no-context` mode
- Branch / worktree: `audit/1994-adr-034-no-context` @
  `C:/Users/jiazh/Desktop/workspace/sci-wt/adr034-audit`
- Change under review: `origin/main..track/adr-034-multi-provider`
  (`origin/main` = `5c7775b3`, branch head = `16430820`)
- Judged against: `docs/specs/adr-034-multi-provider-agent-chat.md` and
  `docs/adr/ADR-034.md`, plus the repository's own tooling in
  `src/scistudio/qa/`.

Per the dispatch, I did not read the planning checklist, the dispatch-prompt
document, `.workflow/records/**`, any issue or PR text, or the branch's commit
messages. Everything below is derived from the source tree, the specs, the ADRs,
and commands I ran myself.

## 0. What I Actually Ran

Every claim marked **observed** below rests on one of these:

| Command | Result |
|---|---|
| `pytest tests/ai tests/api/test_provider_* tests/api/test_ai_pty* tests/api/routes/ai_pty tests/architecture tests/blocks/ai tests/cli/test_install.py tests/engine/test_pty_control*.py` | all pass except one pre-existing environment failure (§6.1) |
| `pytest tests -q --ignore=tests/ai --ignore=tests/architecture` (rest of suite) | 13 failures, all pre-existing platform artifacts — see §6.1 |
| Same failing subset re-run against a `git archive` of `origin/main` in a clean directory | 10 of 13 reproduce identically; the other 3 are an intermittent Windows zarr `os.rename` error |
| `npm --prefix frontend ci && npm run test -- --run` | 113 files / 1099 tests pass |
| `npm --prefix frontend run typecheck` | clean |
| `npm --prefix frontend run lint` | 0 errors, 40 pre-existing warnings |
| `ruff check src tests` / `ruff format --check` | clean |
| `mypy` over the 13 touched backend modules | clean |
| `python -m scistudio.qa.audit.full_audit` | `pass`, 0 errors across all 10 child reports |
| Custom script: rebind `providers_registry.REGISTRY` with a sixth descriptor, then import every consumer fresh (§3, SC-19) | sixth provider reached all six derived surfaces |
| Custom script: run `tests/architecture/test_no_new_cycles.py::_build_graph` against a `git archive` of `origin/main` and against the branch | main = 3 SCCs / largest 30 / 37 modules-in-cycles; branch = 4 / 20 / 30 |
| Independent `grep` for provider-key literals in `src/scistudio/**` outside the registry | §3, SC-6 |

What I did **not** and could not verify is in §5.

## 1. Summary Judgement

**Fit to merge, in my independent judgement, subject to the P2 in §4.1 being
either fixed or the spec wording corrected.** I found no P1.

This is an unusually well-executed change. The central architectural claim — that
per-CLI knowledge now lives in exactly one descriptor table and that a sixth
provider is a registry row — is **true**, and I established that by my own
experiment rather than by trusting the guard test that asserts it. The tests are
real: the ones that matter most would have failed on `origin/main` for the right
reason — the orphaned-temp-file guard, the unique-staging-path concurrency guard,
and the two "this symbol is gone" guards all describe states that only hold after
the change. The concurrency tests use `threading.Barrier` rather than hoping for
interleaving, and the one guard suite that scans source text carries its own
explicit anti-vacuity test.
Deleted tests correspond to deleted code, and each deletion is annotated in place
with where (or whether) the coverage moved.

The residual findings are small, and the honest gap is not in the code: **nothing
in this repository verifies any of the three new provider CLIs against a real
binary.** See §5.

## 2. Functional Requirements (spec §3)

I read every FR and judged the tree against it. Result: **all FRs met except
FR-027, which is met in the sense its rationale describes but not as its sentence
is written** (§4.1). Two others are met with a small caveat worth stating.

Met, verified by reading the implementation and by tests I ran:

FR-001..FR-003 (`providers_registry.py` is the single descriptor table, with a
complete adapter definition per descriptor and an `AGENT`/`TERMINAL` split),
FR-004..FR-006 (`resolve_windows_executable` takes descriptor-supplied
`well_known_dirs`; `_VALID_PROVIDERS` / `_PROVIDER_SPAWNERS` are
`REGISTRY`-derived at `src/scistudio/api/routes/ai_pty/_state.py:59-70`),
FR-007 (one `spawn_agent`, no provider branch — I confirmed by AST inspection as
well as by reading), FR-008/FR-020b (status returns one entry per agent provider
with the additive `label`), FR-009, FR-010..FR-013 (`PtyTabSpec.provider`,
`_provider_from_argv` gone, `AIBlock._build_spawn_argv` gone), FR-014 (the
`scistudio install` hint is gone and the message names provider + expected
binary), FR-015..FR-019, FR-020/FR-020a/FR-020c, FR-021 and its sub-clauses
(a/b/c/d/e/f/i), FR-022..FR-026.

Caveats on otherwise-met FRs:

- **FR-013** ("the AI Block spawn path MUST NOT create files that no component
  deletes") is met on the success path — the orphan is gone because
  `_build_spawn_argv` is gone, and
  `tests/blocks/ai/test_ai_block_skeleton.py::test_run_leaves_no_orphaned_temp_file`
  is a genuine regression guard that would have failed on `origin/main`. One
  narrow error path still leaks; see §4.4.
- **FR-020a** ("the frontend MUST treat agent provider keys as opaque strings")
  is met except for one deliberately retained `provider === "codex"` literal;
  see §4.5.

## 3. Success Criteria (spec §5) — Tested, Not Trusted

The dispatch asked me to test the §5 claims myself rather than trust the guard in
`tests/architecture/test_adr_034_provider_single_source.py`. I did. My reading of
that guard, separately, is that it is one of the better guards in this repository:
it filters docstrings out via AST, strips TS comments, names every allowlist entry
individually with a reason, and closes with
`test_the_guards_above_are_not_vacuous`, which pins that the scanners actually see
files and that each allowlist entry is still earned. But I checked the underlying
claims independently anyway.

| # | Success Criterion | Verdict | How I established it |
|---|---|---|---|
| 1 | All five providers launch a chat tab and reach a working MCP tool call | **UNVERIFIED** | requires real CLIs; see §5 |
| 2 | All five selectable as an AI Block provider and complete a block run | selectable **verified**; "complete a block run" **unverified** | enum experiment (row 19); block run needs real CLIs |
| 3 | Kimi + both Qoder channels discovered when installed only off PATH | **verified** *given the recorded directories are correct* | ran `tests/ai/test_windows_executable_resolution.py` (fake-home fixtures, no dependence on installed CLIs) |
| 4 | Both Qoder channels independently selectable; each unavailable when only the other is installed | **verified** | same file, `test_a_missing_qoder_channel_never_resolves_to_its_sibling` and `test_channels_resolve_independently_when_both_are_installed`; the descriptor data makes cross-resolution structurally impossible |
| 5 | The Qoder security-scan sidecar CLI is never offered as a provider | **verified for the not-on-PATH case only** | see §4.1 — this is the P2 |
| 6 | Per-provider knowledge exists in exactly one backend module; a repo search outside registry/tests/docs returns no spawn/status/validation logic | **verified** | my own `grep` over `src/scistudio/**/*.py`: the only executable provider-key literals outside the registry are `"claude-code"` as the AI Block default (3 sites, no branching) and two per-*install* tables in `cli/install.py` (§4.3). Nothing else; the rest are docstrings and comments |
| 7 | Frontend declares the provider type once, no hand-maintained key or label list | **verified with one exception** | `frontend/src/store/types.ts` is the sole declaration; `SetupScreen.parts/types.ts` re-exports; `usePtyWebSocket.ts` imports. Exception in §4.5 |
| 8 | Injecting into a provider-owned config preserves every unrelated entry | **verified** | read `terminal._merge_provider_mcp_config`; ran `tests/ai/test_providers_registry.py` merge tests and `tests/ai/test_provider_mcp_write_atomicity.py` |
| 9 | Engine-initiated tab records the provider actually spawned, at every link | **verified** | read all four links (`engine.py` emit → `handleBlockPty.ts` → `blockPtyHandlers.ts` → `terminalTabsSlice.ts`); each rejects rather than defaults; `tests/api/test_provider_propagation_chain.py` covers the backend hops and `TerminalTab.test.tsx` the frontend ones |
| 10-13 | Picker visibility/ordering/placeholder, zero-install notice, permission relabel | **verified** | read `ProviderPicker.tsx`, `NoProvidersNotice.tsx`, `SetupScreen.tsx`; ran the frontend suite |
| 14 | An AI Block run creates no file nobody deletes | **verified on the success path** | §4.4 for the error path |
| 15 | Concurrent writes to a provider-owned MCP config never half-written or lost | **verified** | ran `tests/ai/test_provider_mcp_write_atomicity.py`; the tests use `threading.Barrier` and assert `failures == []` with no tolerance, and one test records every `os.replace` source path to prove staging names are unique and in the target directory |
| 16 | Ratchet not raised; largest SCC shrinks; modules-in-cycles falls | **verified independently** | I ran the repo's own `_build_graph`/`_tarjan_sccs` against a `git archive` of `origin/main` and against the branch. `origin/main`: 3 SCCs, largest 30, 37 modules in cycles. Branch: 4 SCCs, largest 20, 30 modules. `MAX_PYTHON_CYCLES` is 4 in both trees — `tests/architecture/test_no_new_cycles.py` is not in the diff at all. The spec's numbers are exactly right |
| 17 | Missing-binary error names provider + binary, suggests no incapable command | **verified** | read `ai_block.validate_config`; the message contains no `scistudio install` |
| 18 | No test asserts a hardcoded two-provider set | **verified as worded**; see §4.6 for the generalisation it does not cover | my own grep plus the AST guard |
| 19 | Adding a sixth provider requires editing the registry module plus its discovery rule, and no other source file | **verified for source files**, with two named exceptions | see below |

### 3.1 The sixth-provider experiment (SC-19)

Rather than trust `tests/api/test_provider_registry_extensibility.py`, I wrote my
own script that rebinds `providers_registry.REGISTRY` to a registry containing a
sixth descriptor (`acme-cli`) *before* importing any consumer, then asks each
consumer what it derived. This reproduces what a fresh interpreter does after the
registry source file gains a row. Observed output:

```
_VALID_PROVIDERS:        (..., 'qoder-cn', 'acme-cli', 'user-terminal')
_PROVIDER_SPAWNERS keys: (..., 'qoder-cn', 'acme-cli', 'user-terminal')
status names:            [..., 'qoder-cn', 'acme-cli']
status labels:           [..., 'Qoder CLI (China)', 'Acme CLI']
AIBlock provider enum:   [..., 'qoder-cn', 'acme-cli']
engine agent_keys:       (..., 'qoder-cn', 'acme-cli')
install targets:         ('claude', 'codex', 'claude-code', ..., 'acme-cli')
```

So the claim holds for the WS whitelist, the spawner map, the status payload
(including the backend-supplied label the frontend renders), the AI Block config
enum, the engine's accepted-provider set, and the `scistudio install --target`
list. The frontend needs no edit because it renders whatever the payload
contains — I confirmed by reading `ProviderPicker.tsx`, which maps over
`providers` and reads `s.label`, and the frontend suite's own
`ProviderExtensibility.test.tsx` drives an invented key end to end.

Two honest exceptions to "no other source file":

1. A sixth provider that needs a **user-scope** MCP config would also require an
   entry in `_USER_SCOPE_JSON_CONFIG` in `src/scistudio/cli/install.py:349-351`.
   A project-scope-only provider needs nothing.
2. A sixth provider using an **MCP injection strategy that does not yet exist**
   would need a new branch in `terminal._mcp_argv`. The spec's phrasing ("plus
   its discovery rule") arguably covers this.

Neither undermines the claim; both are worth knowing.

## 4. Findings

### 4.1 P2 — FR-027's sidecar guarantee is not what the code delivers

- **File / line:** `src/scistudio/ai/agent/providers_registry.py:573-628`
  (`resolve_executable`); test at
  `tests/ai/test_windows_executable_resolution.py:149-163`.
- **Observed.** `resolve_executable` consults `which(name)` and
  `which(name + suffix)` on PATH *first*, and only then scans the descriptor's
  registered well-known directories. The sidecar-rejection test passes
  `which=_nothing_on_path`, so it proves only that discovery does not glob the
  home directory. If `~/.qodersec/bin` (or any other directory containing a
  `qodercli.exe`) is on PATH, `resolve_binary` returns it and SciStudio offers the
  stale, unauthenticated scanner copy as a chat provider.
- **Why it is wrong.** FR-027 reads: "Binary discovery MUST match exact binary
  names within registered well-known directories and MUST NOT select
  provider-named binaries found elsewhere, so vendor sidecar copies are never
  offered as chat providers." The acceptance scenario is likewise unconditional:
  "Given the Qoder security-scan sidecar CLI is present at `~/.qodersec/bin/`,
  when provider discovery runs, then neither Qoder provider resolves to it." As
  implemented the guarantee is conditional on that directory not being on PATH.
  The spec's own §1 *rationale* ("rather than globbing for `qodercli*.exe`
  anywhere under the home directory") describes exactly what was built — so this
  reads to me as an FR sentence that overshot its rationale rather than an
  implementer mistake.
- **Inferred, not observed.** Whether the Qoder security plugin actually puts
  `~/.qodersec/bin` on PATH. I have no Qoder install and could not check. If it
  never does, the practical exposure is nil and this is a documentation fix.
- **Fix options:** narrow FR-027 and its acceptance scenario to the
  no-home-globbing property that was actually delivered, **or** add an explicit
  excluded-directory field to the descriptor and skip PATH hits that resolve
  inside it. Removing the PATH lookup wholesale is not an option — Claude Code and
  Codex are normally found there.

### 4.2 P3 — the user-terminal shell resolver silently lost its fallback

- **File / line:** `src/scistudio/ai/agent/terminal.py:850`
  (`_user_shell_argv` → `resolve_windows_executable(name)`).
- **Observed.** On `origin/main`, `resolve_windows_executable` (then at
  `terminal.py:86`) scanned `_windows_user_cli_dirs()` — `~/.local/bin` and
  `~/AppData/Roaming/npm` — for *every* name it was given. The new signature
  takes those directories as a keyword argument, and `_user_shell_argv` passes
  none, so `pwsh` / `powershell` / `cmd` are now resolved from PATH only.
  Verified by `git show origin/main:src/scistudio/ai/agent/terminal.py`.
- **Why it matters (a little).** It is an unremarked behaviour change on the
  user-terminal path, in a file the spec governs, and nothing tests it — the two
  tests that touch `_user_shell_argv` (`test_windows_executable_resolution.py:285`
  and `:307`) monkeypatch it away entirely. In practice a Windows shell is
  essentially always on PATH, so I judge the real risk very low. It deserves a
  sentence in the docstring rather than a code change.

### 4.3 P3 — `cli/install.py` keeps a second per-provider table, and the guard is scoped around it

- **File / line:** `src/scistudio/cli/install.py:83` (`_LEGACY_TARGET_ALIASES`)
  and `:349-351` (`_USER_SCOPE_JSON_CONFIG`); guard scope at
  `tests/architecture/test_adr_034_provider_single_source.py:64-73`.
- **Observed.** The guard's `_SPAWN_STATUS_VALIDATION_MODULES` list deliberately
  omits `cli/install.py`, and says why in the module docstring. Success Criterion
  6 is worded "no *spawn, status, or validation* logic", so the exclusion is
  literally correct and the module holds installation facts, not spawn facts.
- **Why I am still recording it.** This is the one place where the exclusion is
  drawn by the guard's author rather than by the criterion, and it is where the
  "one registry row" promise is weakest (§3.1 exception 1). Someone reading only
  the Success Criteria would not expect two provider-keyed dicts to survive. The
  justification is stated and I judge it sound; I am flagging the shape, not
  asking for a change.

### 4.4 P3 — one temp-file leak path survives on an error edge

- **File / line:** `src/scistudio/ai/agent/terminal.py:714-746` (`spawn_agent`).
- **Observed.** For a `FLAG_FILE` provider (only `claude-code` today) the
  system-prompt temp file is written at line 723 and appended to
  `cleanup_paths`, but `cleanup_paths` is only handed to `PtyProcess` at line
  739. `_mcp_argv(descriptor, project_dir)` runs in between (line 727) and can
  raise — `_ensure_mcp_config` does `mkdir` + `write_text`, and for a
  `PROJECT_FILE` provider `_merge_provider_mcp_config` raises deliberately on a
  malformed file. If it raises, no `PtyProcess` exists, so nothing ever deletes
  the file already written under `<project>/.scistudio/.tmp/`.
- **Why it is wrong.** It is the same class of orphan FR-013 exists to remove,
  and `<project>/.scistudio/.tmp/` is the same directory. Narrow: it needs a
  `claude-code` spawn whose `.scistudio/mcp.json` write fails. Nothing tests it.
  A `try/except` that unlinks on failure would close it.

### 4.5 P3 — one provider key literal remains in the frontend

- **File / line:** `frontend/src/components/AIChat/SetupScreen.tsx:163`
  (`provider === "codex"`, the #1859 Codex trust-hooks note).
- **Observed.** It is allowlisted by exact file, exact literal, and a maximum
  occurrence count of 1, and `test_the_guards_above_are_not_vacuous` asserts the
  literal is still present so the allowlist cannot quietly become a hole.
- **Why I record it.** FR-020a is absolute ("the frontend MUST treat agent
  provider keys as opaque strings validated at runtime against the status
  payload"), and this is not that. It is a single UI note, adding a sixth provider
  still needs no edit here, and the carve-out is the tightest one I have seen in
  this repository — but the FR and the code disagree by one literal, and the spec
  does not mention retaining it.

### 4.6 P3 — the two-provider guard does not generalise, and two new tests freeze the five-provider set

- **File / line:** `tests/ai/test_providers_registry.py:104-113`
  (`test_registry_order_is_the_frozen_cross_agent_contract`) and
  `tests/blocks/ai/test_ai_block_skeleton.py:495-500`
  (`test_config_schema_provider_enum_lists_all_five_agents`); guard at
  `tests/architecture/test_adr_034_provider_single_source.py:331`.
- **Observed.** The guard fires only on a collection whose string elements are
  exactly `{"claude-code", "codex"}`. Both tests above assert equality against the
  frozen *five*-provider set and will therefore fail the moment a sixth provider
  is added — the same failure mode, one N later, that the guard exists to prevent.
  I found these with my own grep, not with the guard.
- **Why it is only P3.** Success Criterion 19 says "no other **source** file", and
  tests are not source files, so the criterion is not violated. Both tests are
  deliberate scope pins and one says so in its name. But User Story 7's promise as
  a *lived* experience is "one registry row"; in practice a sixth provider costs
  two test edits, and the guard cannot tell anyone that. Asserting against
  `agent_keys()` plus a `len(...) >= 5` floor would keep the intent without the
  freeze — note that `test_config_schema_provider_enum_is_registry_derived`, two
  tests above the offender, already does exactly that.

### 4.7 P3 — the cycle ratchet now has zero headroom, held there by an unrelated import-form change

- **File / line:** `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:59`;
  ratchet at `tests/architecture/test_no_new_cycles.py:41`.
- **Observed.** `MAX_PYTHON_CYCLES` is 4 on both `origin/main` and the branch —
  the file is not in the diff, and the spec's refusal to raise it is real, not a
  claim. The graph genuinely improved (30 → 20 largest SCC, 37 → 30 modules in
  cycles), which I computed myself. But splitting one large SCC raised the *count*
  from 3 to 5, and the count was brought back to 4 by changing
  `from ...tools_inspection import _helpers` to
  `import ...tools_inspection._helpers as _helpers` in an unrelated module.
- **Why I record it.** The branch now sits exactly at the limit with no slack, and
  a single `from pkg import sub` anywhere in the tree can push it to 5 and fail CI
  for reasons entirely unrelated to the offending change. The behaviour is
  identical at runtime and both docstrings explain the asymmetry at length, so
  this is not a hidden trick — but the ratchet is now load-bearing on an import
  *style* in one file. Not a merge blocker; worth knowing before the next
  refactor in `tools_inspection`.

### 4.8 P3 — `kimi doctor` is used as an auth-status probe

- **File / line:** `src/scistudio/ai/agent/providers_registry.py:492`
  (`auth_status_argv=("doctor",)`), consumed at
  `src/scistudio/api/routes/ai.py:197`.
- **Observed.** `_auth_status_command_logged_in` treats exit code 0 as "logged
  in". For Claude Code (`auth status --json`) and Codex (`login status`) that is a
  genuine auth query. `doctor` is conventionally a health/diagnostic command.
- **Inferred, not observed.** I have no Kimi Code install and cannot check whether
  `kimi doctor` exits non-zero when logged out. If it does not, Kimi will report
  `logged_in: true` whenever it is installed.
- **Why it is only P3.** `logged_in` is purely cosmetic in this change: it drives
  the `(not logged in)` annotation in `ProviderPicker.providerHint` and nothing
  else. `launchDisabled` keys on `available` only. A wrong annotation, not a wrong
  launch.

### 4.9 P3 — the permission picker still renders in the zero-install state

- **File / line:** `frontend/src/components/AIChat/SetupScreen.tsx:147-180`.
- **Observed.** In the `noProvidersAvailable` branch, `NoProvidersNotice` replaces
  `ProviderPicker` only. `PermissionModePicker` continues to render below it and
  its radios are fully interactive, even though no provider can be chosen and
  Launch is unconditionally disabled.
- **Why it is wrong.** User Story 4's third acceptance scenario reads: "Given no
  provider is installed, when the Setup screen renders, then the provider dropdown
  **and permission picker** are not presented as the primary affordance, so the
  user is not left clicking disabled controls." FR-021c, which is the requirement
  the implementation followed, names only the picker — so this is a scenario the
  FR under-specified rather than a requirement ignored. The zero-install test
  (`SetupScreen.test.tsx:259-278`) asserts the select is absent and does not check
  the permission picker either way.
- **Impact:** cosmetic. The user is left with two live radio buttons above a dead
  Launch button, which is a milder version of the dead end the story exists to
  close, not a reinstatement of it.

## 5. What I Could Not Verify — Stated Rather Than Guessed

**Nothing in this repository exercises any provider CLI.** Every argv snapshot,
every credential path, every install directory, and every flag spelling for
`kimi-code`, `qoder`, and `qoder-cn` is a transcription of one workstation's
observations on 2026-08-06, and every test that touches them mocks
`PtyProcess`, `resolve_binary`, or `shutil.which`. That is the correct way to
write those tests — the alternative would be a suite that only passes on the
owner's machine — but it means the following are **unverified**, not passing and
not failing:

- Success Criteria 1 and 2 (the five-provider chat smoke launch and the
  five-provider AI Block run). The spec's §4.4 designates the manual smoke launch
  as "the only check that validates the MCP injection strategies end to end". I
  cannot tell from the repository whether it was performed; that evidence, if it
  exists, lives in artifacts this audit mode forbids.
- That `~/.qoder/bin/qodercli` is the real international-channel install path.
  ADR-034 §3.3 itself records this as inferred from an earlier observation, with
  `~/.qoder` absent on the verification date. That caveat is stated plainly in
  the ADR, which I count in the change's favour.
- That Kimi Code accepts `--auto`, that both Qoder channels accept
  `--mcp-config`, and — a case I did not see called out anywhere — that all three
  new CLIs accept the `--` end-of-options separator that `spawn_agent` now
  appends before an AI Block prompt for *every* provider
  (`terminal.py:736-737`). On `origin/main` that separator was only ever sent to
  `claude` and `codex`. If a new CLI treats `--` as a literal argument, AI Block
  runs on that provider break in a way no test can catch.
- Any real-browser behaviour. The withdrawn User Story 6 measurements are
  presented as browser-measured; I did not re-measure them, and I note that the
  spec's own §4.4 is unusually candid that the surviving structural test "asserts
  the class strings … and told us nothing, because jsdom performs no layout".
- That the owner authorised amending an `agent_editable: false` ADR (§7).

## 6. Test Quality

I looked specifically for assertions that cannot fail, behaviour-pinning instead
of requirement-pinning, over-broad allowlists, and weakened or deleted assertions.

**Assertions that cannot fail:** I found none. The one suite most at risk —
`tests/architecture/test_adr_034_provider_single_source.py`, which is entirely
"assert offenders == []" — closes with `test_the_guards_above_are_not_vacuous`,
which pins that the registry has more than two agents, that every guarded module
path resolves, that the frontend scan sees more than 50 files, that the
allowlisted frontend literal is actually present, and that every backend allowlist
entry is still earned. That is the check I would have asked for.

**Deleted assertions:** every removed test corresponds to removed production code
(`_build_spawn_argv`, `_provider_from_argv`, `_BYPASS_FLAG`, `_discover_provider`,
`spawn_claude`, `spawn_codex`). I checked each. The most interesting is
`test_p1a_bootstrap_failure_propagates`, which guarded a worker-side bootstrap
step that no longer exists; the deletion is replaced in-file by a 20-line comment
block at `tests/api/test_ai_pty_audit_fixes.py:374-400` naming where each half of
the old coverage went. I agree with the reasoning: the worker no longer composes
argv, so there is nothing left to fail. The engine-side equivalent still raises
out of `_spawn`, which `tests/api/test_ai_pty_engine_spawn.py` covers.

**Behaviour-pinning vs requirement-pinning:** the tests generally pin requirements.
`test_config_schema_provider_enum_is_registry_derived` asserts equality with
`agent_keys()` and explains in its docstring why containment would be too weak.
`test_spawn_agent_uses_only_its_own_descriptors_binary` is parametrised over
`registry.agent_descriptors()` so a sixth provider is covered the moment it exists,
and it asserts `foreign_binaries` is non-empty before using it — an anti-vacuity
check inside an ordinary test. The exception is §4.6.

**Allowlists:** two exist (`_BACKEND_KEY_ALLOWLIST`, `_FRONTEND_KEY_ALLOWLIST`),
both keyed by exact file and exact literal with a stated reason, both with a
maximum-occurrence cap on the frontend side, and both cross-checked by the
anti-vacuity test so a stale entry fails rather than lingering. I could not
construct a regression they would let through other than the ones I have already
recorded.

**Nothing skipped or xfailed** was added by this change; the skips in the suite
are pre-existing (`Rscript not on PATH`, POSIX-only PTY tests, the ADR-033-era
MCP module).

### 6.1 Test-run results

The frontend suite (113 files / 1099 tests) passes clean, as do `typecheck`,
`lint`, `ruff`, `mypy`, and `full_audit`. Every backend suite named in the spec's
`tests:` list passes.

Thirteen failures appeared across the wider Python suite on my Windows machine.
**None is caused by this change**, and I established that rather than assuming it:

- Ten of the thirteen reproduce identically against a clean `git archive` of
  `origin/main` run in a separate directory —
  `tests/agent_provisioning/test_codex_config.py` (1),
  `tests/api/test_filesystem_browse.py` (1),
  `tests/api/test_mcp_transport_publish.py` (2),
  `tests/cli/test_install.py::test_claude_and_codex_share_identical_mcp_env` (1),
  `tests/desktop/test_terminal_post_rc.py` (2), and
  `tests/qa/test_gate_record_hooks.py` (3). The two config-file ones assert a raw
  Windows path is a substring of a TOML block that JSON-escapes backslashes; the
  shell ones need zsh/bash; the guard-hook ones are sensitive to running inside a
  linked worktree.
- The other three (`tests/blocks/io/test_alpha_findings.py`,
  `tests/core/test_dataobject_extended.py`,
  `tests/core/test_serialization_roundtrip.py`) are an intermittent Windows
  `os.rename` `PermissionError` on a `.zarr` directory. Re-running them in
  isolation on the branch reproduced one and passed the other two, and none of
  those modules — or anything they import — appears in the diff.

So the change is green on everything it touches, and the noise is my platform.

## 7. Governance: ADR-034, `agent_editable: false`, `phase: legacy`

The dispatch asked whether ADR-034 governs the surfaces this change touches, and
whether the way it was modified is legitimate.

**Observed.** The ADR's frontmatter is byte-identical to `origin/main` — the
entire diff to `docs/adr/ADR-034.md` is one added row in the decision table plus a
new body section 3. The governed-surface expansion is expressed as a fenced block
with the info string `yaml adr042-governance-amendment`, which
`scistudio.qa.audit._util._apply_governance_amendments` merges into the ADR's
`governs` at load time. I confirmed this is real rather than decorative by loading
the document through `scistudio.qa.audit.loaders.load_adr_frontmatter` myself: the
merged `governs.modules` gains `providers_registry`, `terminal`, `routes.ai`,
`ai_block`, and `cli.install`; `governs.contracts` gains the twelve registry and
spawn contracts; `governs.files` gains the registry module, `routes/ai.py`,
`ai_block.py`, `cli/install.py`, the SKILL.md, `handleBlockPty.ts`, and
`frontend/src/store/**`. The mechanism is precedented — `docs/adr/ADR-041.md:738`
and `docs/adr/ADR-043.md:927` use the same fence.

I also independently confirmed the *reason* the ADR body gives for not using an
addendum file. `doc_drift._check_adr_spec_alignment` builds its lookup as
`{document.frontmatter.adr: document}` over all governed ADR documents
(`src/scistudio/qa/audit/doc_drift.py:87-91`), `ADRAddendumFrontmatter` subclasses
`ADRFrontmatter` and carries the parent ADR number
(`src/scistudio/qa/schemas/frontmatter.py:126-129`), and `ADR-034-addendum1.md`
sorts before `ADR-034.md`, so the base document would overwrite the addendum in
that dict. The justification is accurate, not a rationalisation.

`full_audit` passes with zero errors, including `frontmatter_lint`, `doc_drift`,
and `closure`, so the widened surface is internally consistent with the tree.

**Unverified.** Whether the owner authorised amending an `agent_editable: false`,
`phase: legacy` ADR. I searched for tooling that enforces `agent_editable` and
found none — the field appears in `src/scistudio/qa/schemas/frontmatter.py:89` as
a schema field and in ADR frontmatter, but no audit rule reads it. So the marker
is policy, not machinery, and the only in-repo record of the authorisation is the
ADR's own section 3.1 prose, which is the change asserting its own permission. A
reviewer with owner context should confirm it; I cannot.

**P3 observation on the amendment's breadth.** The amendment adds
`frontend/src/store/**` and the module `scistudio.cli.install` to ADR-034's
governed surface, where the spec's own `governs.files` names only
`frontend/src/store/types.ts` and `frontend/src/store/terminalTabsSlice.ts`. The
glob makes ADR-034 the governing decision for every future store slice. It passes
the tooling and is presumably the cheapest way to satisfy the ADR ⊇ spec
conjunction, but it governs more than this change touches.

## 8. Spec `governs` / `planned_governs` Consistency

**Observed.** Every non-glob path in `governs.files` exists in the tree (I
enumerated and stat'd them). Every path in `tests:` exists. `planned_governs` is
empty on every surface, matching the spec's own §1 statement that
`providers_registry.py` and `NoProvidersNotice.tsx` moved out of it. `related_adrs`
is `[34]` and `status` is `Planned`. `closure` and `doc_drift` both pass, so the
declared contracts resolve against the generated symbol facts.

Two small notes, neither an error:

- Three files the change touches are **not** in `governs.files`:
  `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py`, `pyproject.toml`
  (three import-linter contracts rewritten), and — by omission —
  `tests/architecture/test_no_new_cycles.py` (correctly, since it is unchanged).
  The spec's §4.2 explicitly declares `_preview.py` "not a governed surface of
  this spec", so this is disclosed rather than hidden. The `pyproject.toml`
  import-linter edits are not mentioned in §4.2 at all, though they are a direct
  and necessary consequence of FR-012.
- `governs.contracts` lists `scistudio.ai.agent.terminal.resolve_windows_executable`,
  which in the tree is an alias assignment (`resolve_windows_executable =
  resolve_executable`, `terminal.py:111`) rather than a definition. The audits
  accept it and the file comment explains why a delegating wrapper was rejected;
  I mention it only because a governed contract that is a re-export is a slightly
  softer anchor than one that is a `def`.

## 9. Verdict

**Fit to merge**, with the following before or shortly after:

1. **Must resolve (P2, §4.1):** reconcile FR-027 and its acceptance scenario with
   what `resolve_executable` actually guarantees — either narrow the spec text to
   the no-home-globbing property, or add a descriptor-level excluded-directory
   check so a sidecar on PATH is rejected too. Leaving an unconditional "MUST NOT
   … never offered" in the spec against a conditional implementation is the kind
   of gap that gets read as delivered later.
2. **Should fix (P3, §4.4):** unlink the system-prompt temp file when
   `spawn_agent` fails between writing it and constructing `PtyProcess`.
3. **Should consider (P3, §4.6):** replace the two frozen five-provider equality
   assertions with registry-derived ones, so User Story 7 does not quietly cost
   two test edits.
4. **Record, do not necessarily change (P3, §4.2, §4.3, §4.5, §4.7, §4.8, §4.9):**
   the shell-resolver fallback loss, the second per-provider table in
   `install.py`, the one surviving frontend literal, the zero-headroom cycle
   ratchet, `kimi doctor` as an auth probe, and the permission picker still
   rendering in the zero-install state.
5. **Not a merge gate but the real risk:** §5. The three new providers have never
   been executed by anything in this repository. If the manual five-provider smoke
   launch has not been performed against real binaries, the change should not be
   considered proven regardless of how green CI is — and if it has, that fact
   belongs somewhere a future reader can find it, because §4.4's own words are
   that unit tests "cannot substitute because they mock the spawn".

I want to be plain about the overall shape: I went looking for the usual failure
modes of a large, finished-looking change — guards that assert nothing, allowlists
wider than their stated reason, deleted assertions, a ratchet quietly raised, a
Success Criterion that is true only of the test that asserts it — and I did not
find them. The ratchet was not raised, and I checked by recomputing both sides.
The extensibility claim is true, and I checked by adding a provider myself. The
concurrency fix is real, and its tests would catch a regression. The findings
above are the residue of a careful change, not evidence of a careless one.
