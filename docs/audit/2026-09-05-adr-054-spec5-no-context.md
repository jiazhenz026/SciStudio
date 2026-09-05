---
title: "Audit — ADR-054 spec 5 agent enablement (no-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
related_specs:
  - adr-054-agent-enablement
  - adr-054-panel-contract
  - adr-054-explore-session
  - embedded-coding-agent-spec
language_source: en
---

# Audit — ADR-054 spec 5 agent enablement (no-context)

Audit mode: **no-context** (agent `S5-E1`, `audit_reviewer` persona).
Subject: the agent-enablement surface as it stands in the working tree at
`0a27ff64d8fdb27df015b00c4f0514776b91449b` — `src/scistudio/ai/agent/mcp/**`,
`src/scistudio/api/routes/ai.py`, `src/scistudio/api/runtime/_projects.py`,
`src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`,
`src/scistudio/agent_provisioning/**`, `tests/ai/**`,
`tests/agent_provisioning/**` — read against `docs/adr/ADR-054.md` §8 and
`docs/specs/adr-054-agent-enablement.md`.
Audit branch: `audit/2254-no-context`.
Gate ledger: `.workflow/records/2254-audit-2254-no-context.json`.

I read no issue, no PR, no commit message, no checklist, no follow-up register
and no `.workflow/records/**` for the work under audit. Every statement below
comes from a file in the repository or from a command I ran myself.

**Verdict: pass-with-fixes.**

The two structural claims this spec rests on are real and are enforced by tests
with teeth rather than asserted. FR-024 — session tools are thin over the
session API — is checked over the whole package's import graph *and* its
attribute graph, which is the only way to enforce it given that
`ExploreSession` exposes `queue`, `kernel` and `bridge` publicly; I re-walked
both by hand and found nothing past the API. The tool-count problem ADR-054
§8.4 names is genuinely solved: one declaration in
`tests/mcp_tool_expectations.py`, a total derived from the name set rather than
written beside it, and five sites importing it. The panel reference document
describes what the panel code actually does — I spot-checked the asset suffix
allowlist, the required declaration fields, the tier order, the API version
constant, the `host_action` set and the emit statement whitelist against
`scistudio/panels/**`, `scistudio/core/panels.py` and
`scistudio/explore/session.py`, and each matched. No document under
`_agent_reference/**` or `_skills/**` teaches the retired ES-module form. The
new skill is 99 lines with zero code fences.

What is wrong is smaller. One behaviour regression against the spec's own
wording that I reproduced end to end (P2); one provisioning test that still
enumerates five task skills out of seven, so the guarantee its own docstring
states is unenforced for two of them (P2); one documentation-layering gap where
`public-api.md` now declares public roots the generated API reference does not
cover (P2); and three P3/P4 items about a mechanism the spec describes
differently from how it was built, an observability affordance that is computed
but never surfaced, and a guard that stops one attribute short.

---

## 1. Checks run, and what they said

```
$ PYTHONPATH=./src python -m pytest tests/ai tests/agent_provisioning -q --no-cov
807 passed, 47 skipped, 1 warning in 86.68s
```

```
$ PYTHONPATH=./src python -m pytest tests/architecture -q --no-cov
564 passed, 1 skipped in 7.86s
```

Skips worth naming, from the first run:

- `tests/ai/test_mcp_server_skeleton.py` — 37 skips, whole module, `pytest.mark.skip`
  ("ADR-033-era MCPServer shape permanently superseded by FastMCP"). See F-6.
- `tests/ai/test_mcp_tools_panels.py:425` — 1 skip, "no browser available: this
  test opens the scaffolded harness in the chromium the frontend e2e toolchain
  installs." This is the test behind **SC-003** ("a scaffolded panel's harness
  renders the document over stub data and captures an emission in a browser").
  SC-003 is therefore **not measured in this environment**; it is measured only
  where `npx playwright install chromium` has run. The rest of the harness
  contract (that it is generated from the contract module, that it carries every
  message name, that it supplies stub data per declared type) is asserted
  without a browser and passes.
- The remaining skips are `Rscript not on PATH`, POSIX-only terminal tests, and
  one provider capability skip — all unrelated to this surface.

```
$ PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-pr
no gate ledger found; run init first
```

I then initialised this audit branch's own ledger
(`--task-kind docs --persona audit_reviewer --branch audit/2254-no-context
--issue 2254 --include 'docs/audit/**'`), which reported Tier 3 (lightweight).
The `check` result after the report lands is recorded in §5.

Targeted commands appear inline with the findings they support.

---

## 2. Findings

### F-1 (P2) — The context tool can report a workflow the person is no longer editing

**FR-003**: *"The context tool the agent already has for the active workflow
MUST report the focus: **its existing fields unchanged**, plus the mode and the
mode's identifiers."*

The existing field is `workflow_id`, and before this change
`get_active_workflow_context` read it from `ctx.active_workflow_id` — the
runtime field ADR-040 Addendum 5 defines. It now reads it from the *focus*:

`src/scistudio/ai/agent/mcp/tools_workflow/read.py:382-384`

```python
focus = effective_focus(ctx)
stale = focus_is_stale(focus, getattr(ctx, "project_dir", None))
workflow_id = focus.workflow_id
```

and `effective_focus` backfills from the runtime **only when the focus carries
no workflow id at all** (`src/scistudio/ai/agent/mcp/_focus.py`):

```python
if focus.workflow_id is None and isinstance(workflow_id, str) and workflow_id:
    return replace(focus, workflow_id=workflow_id)
return focus
```

The route always applies the posted workflow id and applies the focus only when
the key was present (`src/scistudio/api/routes/ai.py:144-147`), and
`ApiRuntime.set_active_workflow_id` deliberately leaves the focus alone
(`src/scistudio/api/runtime/_projects.py:706-722`). So a caller that posts a
workflow id without a focus — which the code documents as an existing, supported
caller ("the pre-ADR-054 half of the channel — the store's own active-workflow
sync") and which `frontend/src/lib/api/ai.ts::postActiveWorkflowContext` still
is — advances the runtime's active workflow while the focus keeps the old one,
and the tool answers with the old one.

Reproduced end to end against the real app:

```
$ PYTHONPATH=./src python repro_focus.py
runtime.active_workflow_id        = other
tool result .workflow_id          = calibration
tool result .workflow_name        = calibration
tool result .mode                 = explore
VERDICT: MISMATCH
```

(The script POSTs `/api/ai/active-context` twice against a `TestClient` over
`create_app()`: first `{"workflow_id": "calibration", "focus": {...explore...}}`,
then `{"workflow_id": "other"}` with no `focus` key, then calls the tool.)

The existing test for this path,
`tests/ai/test_workspace_focus.py:333 test_a_workflow_only_report_leaves_the_focus_alone`,
asserts `runtime.active_workflow_id == "other"` and that the stored focus is
untouched — both true — but never asks the tool what it reports afterwards, so
the divergence is invisible to the suite.

**How bad in practice.** The shipped frontend keeps the two in step by accident
of design: `frontend/src/store/index.ts` calls `syncActiveWorkflowId(state.workflowId)`
and `reportWorkspaceFocus(state)` from the same subscriber, and
`workspaceFocusKey` includes `workflow_id`, so a workflow change always
re-reports the focus. The window is therefore transient in the desktop app.
It is not transient for any other client of the route, and the contract is
what the spec wrote down.

**Suggested fix.** Prefer the runtime's `active_workflow_id` when it is set,
and fall back to the focus's copy — the reverse of today's precedence — or
have `set_active_workflow_id` rewrite `focus.workflow_id` in place while
leaving the mode and its identifiers alone. Either way, extend
`test_a_workflow_only_report_leaves_the_focus_alone` to assert the *tool's*
answer, not only the runtime's state.

---

### F-2 (P2) — The provisioning cross-discoverability test still enumerates five task skills

`tests/agent_provisioning/test_claude_agents_md.py:74`

```python
def test_template_indexes_all_five_task_skills(tmp_project_dir: Path) -> None:
    """The AGENTS.md template must reference all 5 task skills.

    Cross-discoverability rule: the project-level AGENTS.md is the
    agent's entry point on each turn; if a task skill is not indexed
    here, the agent will not know to load it.
    """
```

The bundle has seven. The template itself is correct — it names all seven and
says "the seven task skills sit beside it" — but the test that guards the rule
its own docstring states checks only five:

```
$ PYTHONPATH=./src python -c "...compare the three lists..."
skills._SKILL_NAMES = ('scistudio', 'scistudio-build-workflow', 'scistudio-write-block',
                       'scistudio-debug-run', 'scistudio-inspect-data', 'scistudio-project-qa',
                       'scistudio-write-plot', 'scistudio-write-panel')
template names      = ['scistudio-build-workflow', 'scistudio-debug-run', 'scistudio-inspect-data',
                       'scistudio-project-qa', 'scistudio-write-block', 'scistudio-write-panel',
                       'scistudio-write-plot']
test asserts        = ['scistudio-build-workflow', 'scistudio-write-block', 'scistudio-debug-run',
                       'scistudio-inspect-data', 'scistudio-project-qa']
NOT asserted        = ['scistudio-write-panel', 'scistudio-write-plot']
```

`scistudio-write-plot` could be deleted from the template today and no test would
notice; `scistudio-write-panel` is in the same position from the moment it
landed. FR-009 names four places the skill count moves — orchestration, the
skill list, the template's prose, and "the provisioning test that counts written
files" — and all four did move (`skills.py::_SKILL_NAMES`,
`_orchestrate.py::_expected_skill_paths`, the template's "seven", and
`tests/agent_provisioning/test_skills.py` / `test_orchestrate.py` at 16 files).
This fifth site is not in FR-009's list and was not moved.

**This is the count problem the MCP side solved and the skill side did not.**
The tool set has exactly one declaration (`tests/mcp_tool_expectations.py`) with
the total *derived* from it. The skill name list exists in four hand-maintained
copies that happen to agree —
`src/scistudio/agent_provisioning/skills.py:65`,
`src/scistudio/agent_provisioning/_orchestrate.py:217` (a second literal list
rather than an import of the first),
`tests/agent_provisioning/test_skills.py:9` (a third), and the template's prose
count — plus this fifth that does not.

**Suggested fix.** Parametrise `test_template_indexes_all_five_task_skills` over
`scistudio.agent_provisioning.skills._SKILL_NAMES` and rename it, and have
`_orchestrate._expected_skill_paths` build from `_SKILL_NAMES` rather than
restate it.

---

### F-3 (P2) — `public-api.md` declares public roots the generated API reference does not cover

**FR-012**: *"`public-api.md` MUST name the three notebook helpers at the
top-level package and the explore subsystem's public symbols."* It does, in a
new section (`src/scistudio/_agent_reference/public-api.md:43-64`) that names
`scistudio.input` / `scistudio.load` / `scistudio.output` / `scistudio.blocks`,
plus 28 symbols under `scistudio.explore` and 6 under
`scistudio.explore.fingerprint`. Every one of them exists — I imported and
checked:

```
$ PYTHONPATH=./src python -c "import scistudio, scistudio.explore as e; ..."
top-level helpers: ['input', 'load', 'output', 'blocks']
missing from scistudio.explore: []
fp missing: []
```

But **ADR-054 §8.2** states the layering this spec is implementing: *"The
contract documents under `.scistudio/agent-reference/` carry the shapes and
rules. The generated `user-guide/api-reference/` carries exact signatures."*
And both `_agent_reference/README.md:18` and `public-api.md` send the agent
there for signatures.

The generated reference covers ten roots and none of the new ones:

```
$ ls src/scistudio/_user_guide/api-reference/
index.md  scistudio.blocks.app.md  scistudio.blocks.base.md  scistudio.blocks.code.md
scistudio.blocks.io.md  scistudio.blocks.process.md  scistudio.core.meta.md
scistudio.core.types.md  scistudio.panels.data_access.md  scistudio.panels.models.md
scistudio.tutorials.md
```

`scripts/docs/build_reference.py:73` — `CANONICAL_ROOTS`, "the ten canonical
public roots" — has no `scistudio`, no `scistudio.explore`, no
`scistudio.explore.fingerprint`. The same list is hand-copied in
`tests/api/test_public_surface.py:53` (ten entries) and
`tests/api/test_stability_decorators.py:29` (nine — it is already missing
`scistudio.tutorials`), so the newly-declared roots also get no public-surface
snapshot and no `@stable`/`@provisional` enforcement.

An agent that follows the layering ADR-054 §8.2 defines — reference names the
symbol, generated page gives the signature — dead-ends on every symbol this
spec added to the reference.

The ADR-052 canonical-roots machinery is outside this spec's scope and its
triplication is pre-existing; what is in scope is that `public-api.md` grew
public roots and nothing downstream of it did.

**Suggested fix.** Add `scistudio`, `scistudio.explore` and
`scistudio.explore.fingerprint` to `CANONICAL_ROOTS` (all three copies), or
state in `public-api.md` that these symbols are documented in that page alone
and not in the generated reference. Silence is the defect, not either answer.

---

### F-4 (P3) — The harness is generated from a mirror of the host contract, not from the host contract

The spec says this twice, as a risk mitigation and as an assumption:

- §4.5: *"The harness is generated from the same contract module the host
  uses, and the panel-contract spec's contract test runs the built-in panels
  through it."*
- A-005: *"The harness is generated from the same contract module the frame
  host uses, so that it cannot drift silently. Source: inferred."*

What was built is a Python **mirror** of the host's TypeScript module.
`src/scistudio/ai/agent/mcp/tools_panels/_contract.py` is candid about it:

> **The host's copy is the frontend's, and the two are held together by a
> test.** The host half of this contract is TypeScript
> (`frontend/src/panels/panelMessages.ts` …); a Python scaffold cannot import
> it … That test is the reason this module is a mirror rather than a fork.

I checked what that buys and what it does not.

*What holds.* The harness genuinely is generated from `_contract.py` rather
than hand-written against it — `test_harness_is_generated_from_the_contract_module`
monkeypatches sentinel message names into the module and asserts they appear in
the regenerated harness *and* the regenerated panel document. And the mirror
genuinely is held to the TypeScript —
`test_contract_module_mirrors_the_host_contract` parses
`HOST_TO_PANEL_TYPES`, `PANEL_TO_HOST_TYPES`, `PANEL_HOST_ACTIONS`,
`PANEL_REQUEST_TYPES` and the marker out of the `.ts` source and compares. Both
run and pass in this checkout:

```
$ PYTHONPATH=./src python -m pytest tests/ai/test_mcp_tools_panels.py -q \
      -k "contract_module or harness_is_generated or mirrors"
3 passed, 27 deselected in 1.78s
```

*What does not hold.* Two gaps, both small:

1. The parity test is `@pytest.mark.skipif(not HOST_CONTRACT.is_file())` — it
   silently does nothing wherever the frontend source is absent. In this repo
   it runs; in a wheel-only or sdist-only test environment it does not, and
   the mirror is then unguarded.
2. It compares the four name lists but not `PANEL_REQUEST_RESULT_TYPES`, the
   request→reply *pairing* the harness's router is driven by. A host that
   changed which reply answers which request, without renaming either, would
   not be caught.

The finding is against the **spec text**, which was not updated to describe the
mechanism that was built. The mechanism is defensible and the code explains
itself; the document asserts something stronger than what exists, and A-005 is
marked "inferred", which is exactly the kind of assumption that should have
been corrected once the answer was known.

**Suggested fix.** Rewrite §4.5's mitigation and A-005 to say "generated from a
Python mirror of the host contract module, held to it by
`test_contract_module_mirrors_the_host_contract`", and add
`PANEL_REQUEST_RESULT_TYPES` to that test.

---

### F-5 (P3) — A session tool cannot tell the agent it acted on a private copy of the notebook

`src/scistudio/ai/agent/mcp/tools_explore/_service.py` is careful about the one
thing that matters here — that the service must be *the person's*:

> A service built here in that process would be a *second* `SessionService`
> over the same notebook files — two `NotebookStore` documents over one file,
> and a cell the agent appends reaching the person only when their own session
> next reloads, which is the opposite of what FR-024 promises.

and when it cannot get the person's service it builds a detached one and says
so — to the log:

```python
if announce:
    logger.warning("session tools: %s", origin.detail)
```

The module's docstring claims more than that: *"`resolve_session_service`
reports the origin to any caller that asks."* No tool asks.
`session_for()` calls `session_service()`, which discards the origin, and
`grep -n "detached\|ORIGIN_\|resolve_session_service"` over
`tools_explore/tools.py`, `_models.py` and `__init__.py` returns nothing. No
result model carries the origin: `OpenExploreSessionResult`,
`AppendCellResult`, `RunCellResult` and the rest look identical whether the
tool acted on the person's session or on a copy nobody is looking at.

The agent — the only consumer that can act on the difference — is told
nothing. A person diagnosing "the agent said it appended a cell and my notebook
never changed" has to find a WARNING in a log. The reachable path is a runtime
that has the accessor but whose call raises (handled at
`resolve_session_service`, logged, falls through to detached) while a GUI window
is open on the same project.

**Suggested fix.** Add one boolean to the session result models —
`session_service_detached`, with the `ServiceOrigin.detail` string beside it
when true — and set it from `resolve_session_service()` rather than
`session_service()`.

---

### F-6 (P3) — The FR-024 attribute guard stops one attribute short of the notebook file

`tests/ai/test_mcp_tools_explore.py:917` is the right idea, and its own comment
says why it has to exist:

> `ExploreSession` exposes `queue`, `kernel` and `bridge` publicly, so FR-024
> is only enforceable if the call graph is checked as well as the import graph.

`FORBIDDEN_ATTRIBUTES` covers `queue`, `kernel`, `bridge`, their private
counterparts, `_store`, `_document`, the four kernel lifecycle methods,
`interrupt`, `stripped_notebook`, `note_branch_commit` and
`note_explore_commit`. FR-024 forbids reaching "the kernel, **the notebook
file**, or the queue". The public method that writes the notebook file —
`ExploreSession.write()` (`src/scistudio/explore/session.py:1402`) — is not in
the set, and neither is `notebook_path`, the public property that hands out the
file's location. No current module uses either; the guard simply would not
catch the next one that did.

For completeness on the same rule, I walked it by hand rather than trusting the
test. The only `scistudio.explore` reach in the whole package is
`session.document` at `tools_explore/tools.py:706` and `:808`, passed into
`scistudio.explore.packaging`. That is not a shortcut: it is byte-for-byte the
call `api/routes/explore.py:1423-1426` and `:1475-1481` make —
`check_packaging(session.document, marks=session.cell_marks(),
bindings=session.binding_types(), observations=session.observations)` — which is
how that module is designed to be called. Nothing in `tools_explore/**` imports
`scistudio.explore.kernel`, `kernel_bridge`, `queue`, `notebook` or
`notebook_api` at any depth or in any scope.

**Suggested fix.** Add `write` and `notebook_path` to `FORBIDDEN_ATTRIBUTES`.

---

### F-7 (P4) — `ARCHITECTURE.md`'s tool table is stale, disclosed, and now staler

```
$ grep -n "35 tools" docs/architecture/ARCHITECTURE.md
1324:The production MCP surface contains 35 tools:
```

The registry holds 47. This is a *disclosed* deferral, and disclosed well:
spec §4.5 and A-006 put the guarded document's update in the documentation
spec's batch, and `tests/ai/test_tool_catalogs.py` excludes it with a
`TODO(#2236)` and a paragraph saying to delete the paragraph when #2236 lands.
Worth recording only because the count was already wrong before this work (36
tools existed pre-spec-5, the table said 35), so #2236 has two drifts to fix,
not one.

---

### F-8 (P4) — The spec's affected-files table names a count site that cannot be moved

Spec §4.2 lists `tests/ai/test_mcp_server_skeleton.py` | modify | "Count
assertions (FR-025)". The file is skipped in its entirety:

```python
pytestmark = pytest.mark.skip(
    reason=("ADR-033-era MCPServer shape permanently superseded by FastMCP …"),
)
```

and still carries `def test_total_tool_count_is_25()` asserting 9/5/7/4. It
never runs (37 skips in the run above), so nothing is broken. The spec named a
site the work could not usefully move; the table should say so or drop the row,
so that the next person adding a tool does not go looking for a count assertion
that is not live.

---

### F-9 (P4) — Prose tool counts restated beside the derived one

`tests/mcp_tool_expectations.py` derives the total (`EXPECTED_TOOL_COUNT =
len(EXPECTED_TOOL_NAMES)`) and then restates it in prose in its own docstring:
"The registry holds 47 tools in eight groups." The base skill restates it twice
(`src/scistudio/_skills/scistudio/SKILL.md:126` and `:144`). No test reads any
of the three, so all three can drift while the assertions stay green. The
catalog test guarantees the *names* inside the splice markers, which is the
part that matters, so this is a nit — but it is the same class of restatement
the module was written to remove.

---

## 3. Cross-spec observation (not a finding against this spec)

`frontend/src/explore/workspaceFocus.ts:106` exports
`resetWorkspaceFocusReporter()`, documented as *"For tests, and for a project
switch."* `grep -rn "resetWorkspaceFocusReporter" frontend/src` returns the
definition and its own test file, and nothing else — it is never called on a
project switch.

Combined with FR-002's restoration, this leaves one path where the agent is
told a mode the person is not in: switch from project A to project B while the
derived focus key is unchanged (canvas with the same `workflowId`, or both
null). `reportWorkspaceFocus` suppresses the report as a duplicate,
`open_project` restores B's persisted focus from
`<project>/.scistudio/active_workflow.json`
(`src/scistudio/api/runtime/_projects.py:493`, `:635-671`), and if B's last
persisted focus was `explore` over a notebook that still exists, the context
tool answers `mode=explore` and the session tools act on that notebook — which
the person closed, in a session they are not in. Nothing here is stale by
FR-004's definition, because the file exists.

`frontend/src/explore/**` belongs to the explore-frontend spec, so I am
recording this rather than filing it against spec 5. The cheap fix is to call
`resetWorkspaceFocusReporter()` on project switch, which is what the function's
own docstring already says it is for.

---

## 4. What I checked and found clean

Recorded so a later reader knows what was covered, not only what failed.

**The hard requirement (FR-001 to FR-005).**
Every one of the six focus-consuming session tools calls
`resolve_session_path(session_path or None)` before it touches anything
(`tools_explore/tools.py` lines 425, 473, 527, 618, 694, 779);
`open_explore_session` correctly does not, and FR-019's "MUST NOT change the
focus" holds by construction — the AI layer cannot write the runtime's focus.
`resolve_session_path` refuses on canvas, on pause, on never-reported, and on a
stale explore focus, and the refusal names `open_explore_session` with its
arguments so the agent can recover in one call. Staleness is decided by
`focus_is_stale`, which returns true for a deleted notebook, for a path that
escapes the project (via the same `_safe_under` every other agent-supplied path
goes through), and for a focus with no project open. `WorkspaceFocus.from_mapping`
is tolerant in both directions and an unrecognised mode degrades to "never
reported" rather than taking the tool offline. The two hand-maintained field
lists (`_focus.FOCUS_FIELDS` and `_projects._FOCUS_FIELDS`, duplicated
deliberately so `api.runtime` need not import the MCP package) are asserted
equal by `test_the_two_layers_agree_on_the_focus_record`.
`tests/ai/test_workspace_focus.py` carries 30 tests covering each of US1's five
acceptance scenarios including the restart.

**FR-024, thinness.** Covered under F-6 above. Clean apart from the guard gap.

**FR-006 to FR-008, skills.** `scistudio-write-panel/SKILL.md` is 99 lines with
zero code fences (`grep -c '^```'` → 0), states the five-step flow in ADR
order, and points at `panel-contract.md` and the example tools rather than
carrying contracts. `scistudio-write-block` gains the packaged-notebook shape
with the condition for choosing it ("when the computation is not yet
understood") *and* the counter-advice not to default into it, and routes to the
panel skill in a dedicated section and again in its anti-patterns. The base
skill states the focus rule, says plainly that it is advice and the tools'
refusal is the guarantee, and says to *ask* when the focus is explore and the
request reads like a workflow edit.

**FR-010/FR-011, the retired form.** A search over `_agent_reference/**` and
`_skills/**` for `ES module`, `export default`, `dynamicPreviewer`,
`panelModuleLoader` and the old asset route returns exactly two lines, both in
`scistudio-write-panel/SKILL.md:88-89` naming the form as a retired
anti-pattern. **SC-008 holds.**

**The panel reference against the panel code.** `panel-contract.md`'s asset
suffix list matches `scistudio/panels/assets.py:_ALLOWED_ASSET_SUFFIXES`
exactly; its six required declaration fields match
`core/panels.py:REQUIRED_DECLARATION_FIELDS` exactly and in order; its tier
order matches `PANEL_TIER_ORDER`; `api_version` `"1"` is
`core/panels.PANEL_API_VERSION`, the one constant; the three `host_action`
values match `PANEL_HOST_ACTIONS`; the emit statement whitelist matches
`admit_snippet`'s contract as `ExploreSession.emit_snippet` calls it; and the
claim "a displaying panel sends no `emit` … the harness will tell you" is
implemented at `tools_panels/_scaffold.py:707-709`.

**Counts and catalogs (FR-025, FR-026).** One declaration; total derived; a
module-level assertion catching a name claimed by two groups; per-group counts
*and* per-group membership asserted against the live registry; every registered
tool asserted present in both unguarded catalogs, plus a separate assertion
that the base skill's static fallback is complete *between its splice markers*
because Codex reads that block verbatim; and an assertion that no tool ships
without a `category:` tag. Five sites import the declaration
(`test_mcp_fastmcp`, `test_finish_ai_block_skeleton`, `test_tool_catalogs`,
`tests/cli/test_mcp_bridge`, `tests/contracts/test_runtime_import_contract`,
`tests/integration/test_phase2_mcp_end_to_end`).

**FR-017 / FR-027, the corpus.** `_user_guide/examples/` carries
`panel-series-view` (`capability: displaying`), `panel-region-picker`
(`capability: producing`) and `notebook-find-peaks` (`find_peaks.ipynb` +
`block.py` + README). Both listing paths reach them —
`list_panel_examples` scans the corpus directory and filters on `panel.json`
with an optional `capability` argument, and `list_block_examples` reaches the
same directories through `_CORPUS_EXAMPLES` under categories `panel` and
`notebook`. `pyproject.toml:178` ships `_user_guide/**/*` in the wheel.

**Spec-governed paths.** All 29 files and globs in the spec's `governs.files`
exist, including `frontend/src/explore/workspaceFocus.ts`, which the table
marks as spec 4's to write.

**Deferrals.** The two TODOs I found in this surface —
`runtime.py:169` (a standalone bridge reports no focus) and
`test_tool_catalogs.py:47` (the guarded architecture table) — both carry the
tracked form AGENTS.md §3.6 requires: what is deferred, why, the scope
decision, and a followup reference.

**Generated docs.** Nothing under `_agent_reference/**` is generated; the
generated tree is `_user_guide/api-reference/`, which is untouched by this work
(and see F-3 for the consequence).

---

## 5. Recommendation

**pass-with-fixes.**

The design's load-bearing claims are implemented and enforced, not asserted.
Fix before merge:

1. **F-1** — the context tool's `workflow_id` can be older than the runtime's,
   against FR-003's own wording. One-line precedence change plus one assertion
   added to an existing test.
2. **F-2** — `test_template_indexes_all_five_task_skills` leaves two of seven
   task skills unguarded. Parametrise over `_SKILL_NAMES`.
3. **F-3** — decide whether the new public roots belong in the generated API
   reference, and say so either way.

Fix or track:

4. **F-4** — correct §4.5 and A-005 to describe the mirror-plus-parity-test
   that was actually built, and add `PANEL_REQUEST_RESULT_TYPES` to the parity
   test.
5. **F-5** — surface the detached-service origin in the session tool results.
6. **F-6** — add `write` and `notebook_path` to `FORBIDDEN_ATTRIBUTES`.

F-7 through F-9 are housekeeping; F-7 is already tracked by #2236, which should
be told that the count was wrong before this work as well.

The cross-spec observation in §3 belongs to the explore-frontend spec and
should reach whoever owns it, because it is the one path I found by which the
agent can be told a mode the person is not in without any focus being stale.
