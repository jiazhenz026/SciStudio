# Audit: ADR-054 Panel Contract (no-context)

- Date: 2026-09-03
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2229-panel-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/w5-audit-nc`
- Subject: the tree as it stands, judged against
  `docs/specs/adr-054-panel-contract.md` (FR-001..FR-051, SC-001..SC-016),
  `docs/adr/ADR-054.md`, `docs/adr/ADR-048.md` + addendum 1,
  `docs/adr/ADR-051.md` + addenda, and the repository's own tooling.

Per the dispatch I read no issue, PR, checklist, dispatch prompt, gate ledger,
or commit message, and ran no `git log` / `git show` / `git diff`. I confirmed
by filename-level grep only (never by reading) that `docs/planning/**` contains
material; §2.1 reports the consequence without quoting it. Everything below is
derived from the source tree, the governing documents, and commands I ran.

---

## 0. What I Actually Ran

| Command | Result |
|---|---|
| `pytest tests/panels tests/architecture tests/adr052_contract -q --no-cov -p no:randomly` | **1316 collected, 11 skipped, 0 failed**, exit 0 (skips are symlink-needs-elevation ×3, an empty entry-point parameter set, and 5 sanctioned `.xlsx`/R exceptions) |
| `pytest tests/blocks --ignore=tests/blocks/io tests/engine tests/tutorials -q --no-cov -p no:randomly` | **all passed**, 12 skipped (Fiji/Rscript/Octave/POSIX opt-ins), exit 0 |
| `pytest tests/api -q --no-cov -p no:randomly` | **all passed**, exit 0, 8 skipped (symlink elevation ×2, POSIX-only semantics ×4, macOS-only ×2 — none in the panel routes) |
| `pytest tests/blocks/io -q --no-cov` | 40 failures, **all** `ModuleNotFoundError: No module named 'openpyxl'` (verified: `python -c "import openpyxl"` fails; `grep -oE "ModuleNotFoundError: No module named '[a-z]+'" \| sort \| uniq -c` → `40 openpyxl`). Ambient-environment gap, unrelated to the panel surfaces. Discounted. |
| `npm ci` (node_modules was absent), `npm test` | **2274 passed / 1 failed (194 files)**. The single failure is `src/__tests__/eslint-config.test.ts > loads the project flat config without parser errors` — `Error: Test timed out in 5000ms`, actual 11374ms. A machine-speed timeout in a config-loading test, unrelated to panels. |
| `npm run typecheck` | clean |
| `npm run lint` | **0 errors**, 42 warnings (pre-existing `no-console` / unused-directive style) |
| `ruff check src tests` | `All checks passed!` |
| `ruff format --check src tests` | `899 files already formatted` |
| `lint-imports` | **13 contracts kept, 0 broken** — including `Panels must not depend on engine, blocks, workflow, ai, or api` |
| `scripts/audit/generate_facts.py --write` then `--check` | exit 0 (the file is `.gitignore`d line 30, so a fresh worktree has none until generated) |
| `python -m scistudio.qa.audit.full_audit --format markdown` | status `pass`, 0 error findings; all 9 child reports pass |
| Sentrux | **not installed**: no `sentrux` on PATH, `ModuleNotFoundError: No module named 'sentrux'`, `pip show sentrux` → not found. Only `.sentrux/rules.toml` exists. Not run. |
| Bespoke adversarial probes | §3.1 (emission sandbox), §3.2 (provider path confinement) — both executed against the real code |

### 0.1 A crash worth recording

The single combined command the dispatch names —
`pytest tests/panels tests/api tests/architecture tests/adr052_contract tests/tutorials tests/blocks tests/engine -q --no-cov -p no:randomly` —
**did not complete on this machine**. It progressed to `[ 27%]` and the shell
reported `EXIT=127` with no pytest summary line, no traceback and no failure
report. Re-running the same directories in four smaller invocations completed
cleanly, so this reads as a resource/process-level abort rather than a test
defect; I record it because "the suite is green" and "the suite ran" are
different claims and only the second one needed checking.

---

## 1. Verdict

**pass-with-fixes**, with one finding I would want closed before merge.

The mechanism is, on inspection, the thing the spec asked for. There is one
version constant in Python, one loader, one confinement check, one asset route,
four tier roots, eleven built-in panel directories, and neither retired loader
module survives. The frame boundary, the per-mount token, the `event.source`
identity check, the handshake, the bounded waits, the structural capability
gate, and the copy-on-write editing path are all real and all tested. §5 lists
what I verified holds, in detail, because a clean bill of health asserted
without evidence is worth nothing.

What I found is: one path-confinement defect the module's own docstring claims
does not exist (§3.2, **P1**); a version-constant duplication that SC-001
forbids and no test couples (§2.2, **P2**); an entire user-facing half of Story
3 that has no implementation (§2.3, **P2**); a normative-reference chain that
terminates outside the governed surface (§2.1, **P2**); and a set of smaller
document/code disagreements (§4).

---

## 2. Findings — P1 and P2

### 2.1 (P2 — agreement) 191 normative citations in shipped code resolve only into `docs/planning/**`, which the spec's own `governs.excludes` excludes

**Evidence.** `grep -rloE '\bD-0[0-9]{2}(\.[0-9])?\b' src/scistudio frontend/src`
returns **51 files** and **191 occurrences** of decision identifiers `D-001`
… `D-020` (plus `D-016.2`, `D-016.3`). They appear in
`src/scistudio/core/panels.py:4`, `src/scistudio/api/routes/panels.py:1`,
`src/scistudio/panels/assets.py:3`, `src/scistudio/panels/descriptor.py:1`,
`src/scistudio/panels/compat.py`, `frontend/src/panels/panelCapability.ts:20`,
`frontend/src/panels/panelMessages.ts:11`, all eleven
`src/scistudio/panels/builtin/*/index.html`, and the tutorial panel document.

`grep -rlE '\bD-0[0-9]{2}\b' docs/` returns exactly two files, both under
`docs/planning/`. `docs/specs/adr-054-panel-contract.md` and
`docs/adr/ADR-054.md` contain **zero** `D-0NN` definitions. And that spec's own
frontmatter (`docs/specs/adr-054-panel-contract.md:107-108`) lists
`docs/planning/**` under `governs.excludes`.

**Why it matters, concretely.** This is not a stylistic complaint about
citation hygiene. `frontend/src/panels/panelCapability.ts:18-35` uses D-011 and
D-017 to *narrow a MUST NOT in the governing spec*. FR-011 reads:

> A displaying panel MUST NOT be granted any outbound message type.

The implementation grants a displaying mount six of the seven panel-to-host
types (`PANEL_PROTOCOL_TYPES`, `panelCapability.ts:47-54`) and withholds only
`emit`. That may well be the right reading — the module argues it persuasively
— but the argument rests on D-011 and D-017, which exist only in a document the
spec declares ungoverned. A reader a year from now (Story 5's reader, the one
§9 exists for) follows the citation and finds nothing normative.

**Class**: defect in the agreement between documents and code.
**Fix**: fold the D-0NN decisions that narrow or interpret an FR into the spec
or an ADR addendum, or restate FR-011 to match what was built.

---

### 2.2 (P2 — code + test) Twelve hard-coded panel API version literals, and the test that "pins" them spells the version a thirteenth time

**Evidence.** SC-001: *"Exactly one panel API version constant exists in the
tree … Measured by searching the tree for both."* `src/scistudio/core/panels.py:56`
states the rule in the strongest possible terms: *"a second definition anywhere
in the tree — the frontend included — is a defect against SC-001."*

Searching the tree:

```
src/scistudio/panels/builtin/core.array.basic/index.html:148:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.artifact.basic/index.html:115:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.base.fallback/index.html:136:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.collection.basic/index.html:125:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.composite.basic/index.html:122:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.dataframe.basic/index.html:160:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.interactive.data_router/index.html:132:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.interactive.pair_editor/index.html:119:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.plot.basic/index.html:144:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.series.basic/index.html:116:  var PANEL_API_VERSION = "1";
src/scistudio/panels/builtin/core.text.basic/index.html:122:  var PANEL_API_VERSION = "1";
src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html:152:  var PANEL_API_VERSION = "1";
```

Twelve definitions, each answering the FR-009 handshake with
`post("ready", { api_version: PANEL_API_VERSION })`. I accept that FR-034 and
A-004 forbid the obvious fix (a shared runtime import), so **the duplication is
forced**. That is exactly why the coupling has to be pinned by a test — and it
is not:

```python
# tests/panels/test_builtin_panels.py:28
EXPECTED_API_VERSION = "1"
...
# tests/panels/test_builtin_panels.py:456
assert f'PANEL_API_VERSION = "{EXPECTED_API_VERSION}"' in document
```

`EXPECTED_API_VERSION` is a **literal in the test**, not an import of
`scistudio.core.panels.PANEL_API_VERSION`. Compare
`tests/panels/test_panel_capability_gate.py:26`, which does import the real
constant. So: change `PANEL_API_VERSION` in `core/panels.py` to `"2"`, and this
test still passes, `pytest tests/panels` still passes — while every one of the
eleven built-in panels now fails `isAcceptedApiVersion` at
`frontend/src/panels/panelFrame.ts:713` and the whole preview surface falls to
the fallback path. **This is a test that passes for the wrong reason**, guarding
the one property that most needs guarding.

**Class**: defect in a test (the literal), and in agreement (SC-001 vs FR-034;
no document records the exception SC-001 must have).
**Fix**: import `PANEL_API_VERSION` into the test and derive the assertion from
it; record in the spec that FR-034 forces per-document version literals and
that the coupling is defended by test rather than by construction.

---

### 2.3 (P2 — code) FR-028 / FR-029 / Story 3 acceptance scenario 2: there is no revert, and no editing UI at all

FR-028: *"When an edited panel fails to load, the host MUST report the failure
explicitly and **offer to revert**."* FR-029: *"Reverting MUST delete the
shadowing copy."* Story 3 acceptance scenario 2 repeats it. SC-004 measures a
person editing the built-in table panel.

**Evidence.**

- The backend is complete: `DELETE /api/panels/{panel_id}/override`
  (`src/scistudio/api/routes/panels.py:591`), `revert_panel_override`
  (`src/scistudio/panels/editing.py:360`), and
  `GET`/`PUT /api/panels/{panel_id}/source` all exist and are tested
  (`tests/api/test_panel_source_routes.py`, `tests/panels/test_panel_editing.py`).
- The frontend has **no client for any of them**. `grep -rn "api/panels" frontend/src`
  returns `/api/panels`, `/api/panels/reload`, `/api/panels/choices*` and
  `/api/panels/assets/*` — and nothing else. `frontend/src/lib/api/data.ts:179-211`
  exposes `listPanels`, `reloadPanels`, `listPanelChoices`, `setPanelChoice`,
  `clearPanelChoice`. There is no `readPanelSource`, no `savePanelSource`, no
  `revertPanelOverride`.
- `grep -rni "revert" frontend/src` returns four hits, all in
  `AIChat/TerminalView.tsx`, `CodeEditor.parts/useConflictDecorations.ts` and
  `store/gitSlice.ts`. None is a panel.
- `frontend/src/panels/PanelErrorSurface.tsx:138-156` renders a headline, the
  reason code, the message and the panel name. **No control of any kind.**

So the host's error surface reports the failure (FR-014 ✓) and never offers the
revert FR-028 requires, because nothing in the frontend can call the endpoint.
`PanelHost` unconditionally renders `renderFallback(failure)`
(`PanelHost.tsx:448-452`) — which is FR-014's behaviour applied to the FR-028
case as well.

**A second, sharper half of the same gap.** FR-028 says the host *"MUST NOT
silently fall back to the panel that was shadowed, because a silent fallback
reads as an edit that was never saved."* FR-032 explicitly contemplates panel
files written by the agent rather than through the endpoint. An agent write that
leaves `panel.json` invalid is refused at discovery
(`src/scistudio/panels/discovery.py:201-205` turns it into a diagnostic and
`continue`s), so the project copy vanishes from `discovery.panels` and the
shadowed core panel resolves in its place. That is precisely the silent fallback
FR-028 forbids, and nothing distinguishes it. The same happens through the
endpoint if a saved declaration renames `entry`: `save_panel_source`
(`editing.py:325-329`) writes the document at the **old**
`panel.manifest.entry` while persisting the **new** declaration, after which
`read_panel_declaration` (`core/panels.py:531-538`) refuses the directory for
naming an entry it does not contain.

**Class**: defect in the code (missing implementation), and in the agreement —
the spec's §4.2 affected-files table lists the frontend surfaces this would live
in, and T-010/T-011 are in §4.3.

---

## 3. Findings — security (the four adversarial passes)

### 3.1 (P2 — code) `str.format` attribute traversal bypasses `_refuse_dunder_reach` in the emission sandbox

*Pass: "executes code that arrives over a WebSocket."*

`src/scistudio/engine/scheduler/_dispatch.py:650` hands whatever arrived on
`interactive_complete` to `settle_interactive_response`, which `exec()`s it
(`src/scistudio/blocks/base/interactive.py:441`) with `__builtins__ = {}` and
one bound name. The stated mitigation
(`interactive.py:322-345`, `_refuse_dunder_reach`) walks the AST and refuses any
`ast.Name`, `ast.Attribute`, `ast.keyword`, `ast.arg`, `ast.FunctionDef`,
`ast.ClassDef`, `ast.alias`, `ast.Global` or `ast.Nonlocal` whose name starts
with `__`, because *"the documented way out of a no-builtins namespace is a
dunder walk."*

**It does not inspect string constants.** `str.format` performs attribute and
subscript traversal driven by the *runtime string*, which is an `ast.Constant`.
Executed against the real function:

```
[refused] scistudio.output(a=().__class__)
          → "emitted code reaches '__class__'"
[ALLOWED] scistudio.output(a="{0.__class__}".format(()))
          → {'a': "<class 'tuple'>"}
[ALLOWED] scistudio.output(a="{0.__class__.__base__.__subclasses__}".format(()))
          → {'a': '<built-in method __subclasses__ of type object at 0x...>'}
[ALLOWED] scistudio.output(a="{0.output.__globals__}".format(scistudio)[:200])
          → {'a': "{'__name__': 'scistudio.blocks.base.interactive', '__doc__': ...}"}
[ALLOWED] scistudio.output(a="{0.output.__globals__[__name__]}".format(scistudio))
          → {'a': 'scistudio.blocks.base.interactive'}
```

**I could not turn this into code execution, and I tried.** `str.format`
returns strings, so no live object escapes that way. I also probed the frame
route — a suspended generator's `gi_frame` is reachable (non-dunder), but its
`f_back` is `None` and its `f_builtins` is the empty dict the sandbox supplied
(verified: `{'frame': <frame at 0x..., file '<panel emission>'>, 'back': None,
'builtins_keys': {}}`). `import os` fails with `ImportError: __import__ not
found`. So the containment holds against RCE.

What it does not hold against is **read access, as text, to module globals and
the type graph, exfiltrated through `scistudio.output(...)`** — which becomes
`config[INTERACTIVE_RESPONSE_KEY]` and is persisted into the workflow. The
panel is precisely the component the frame boundary exists to keep out of the
Python process, so a documented mitigation with an undocumented hole is worth
closing.

**Class**: defect in the code (incomplete mitigation), and in the docstring,
which asserts the mitigation without its limit.
**Fix**: refuse `__` inside `ast.Constant` string values as well, or drop
`str`'s `format`/`format_map` from reach.

**Related, and untracked.** `interactive.py:396-406` documents that an emission
that never terminates *"would wedge the whole engine rather than one block"* and
that nothing can interrupt it. That is deferred work recorded in a docstring
with **no `TODO(#NNN)`** citing an issue. `AGENTS.md` §3.6 requires deferred
work to be visible with a tracked reference; the plot panel's TODO
(`core.plot.basic/index.html:30`, `TODO(#2212)`) is the form this one is
missing.

---

### 3.2 (P1 — code) A panel declaration's `provider` escapes its tier root and executes arbitrary Python from any readable path, at discovery time

*Pass: "writes files from HTTP requests" / "serves files by id" — this is the
import path, which turned out to be the one that is not confined.*

FR-047: *"the provider MUST be resolved from the tier the panel was discovered
in."* `src/scistudio/panels/providers.py:11-18` states it as a security
property:

> **The reference is resolved from the tier the panel was discovered in.** A
> user-library panel never resolves its provider out of the open project's
> directory, and vice versa.

`src/scistudio/panels/editing.py:22-29` states the repository's own discipline
for this class of bug — *"the surface this repository has already been bitten on
three times (#2038, #2037, #2039) … A path that escapes is refused, not
clamped"* — and the write path honours it (`confined_panel_directory`,
`_confined_file`, `_confined_existing_directory`, all `relative_to`-checked).

**The import path performs no such check.**

```python
# src/scistudio/panels/providers.py:112
candidate = root.joinpath(*module_name.split("."))
```

`module_name` is everything before the `:` in the declaration's `provider`
field, validated only as a non-empty string
(`src/scistudio/core/panels.py:482-490`). `pathlib.joinpath` **resets on an
absolute segment**, so a leading `.` in the dotted name yields an empty first
component followed by an absolute one:

| `provider` module part | `root.joinpath(*parts)` |
|---|---|
| `../evil` | `C:\evil` (POSIX: `/evil`) |
| `sub/../../evil` | `C:\evil` |
| `./tmp/evil` | `C:\tmp\evil` |

The result is never compared back to `root`, and
`resolve_declared_provider:161-174` then runs
`spec_from_file_location(...)` + **`exec_module(module)`** on it.

**Executed against the real code** (user-library tier root under a temp dir,
payload planted at the drive root, i.e. only reachable by escaping):

```
module_name -> ./scistudio_audit_tmp/evil
dropin_module_path -> C:\scistudio_audit_tmp\evil.py
provider: <function go at 0x...> | error:
MARKER WRITTEN OUTSIDE TIER ROOT: True
   content: executed outside the tier root
```

(Artifacts removed afterwards; `C:/scistudio_audit_tmp` no longer exists.)

**Reachability.** `discover_tier` resolves providers by default
(`discovery.py:177`, `220`), and `resolve_providers=False` is passed **nowhere
in `src/`** — only by `tests/panels/test_panel_registration.py:348`. So this
fires whenever the registry is built: opening a project, `POST /api/panels/reload`,
`PUT /api/panels/choices/{type}`, and every `save_panel_source` /
`revert_panel_override`, all of which call `runtime.refresh_all_registries()`.
FR-046 makes a project register a panel by *containing a directory*, and Story 2
acceptance scenario 4 contemplates a project arriving from a colleague.

This does widen the existing drop-in surface rather than duplicating it:
`scistudio.core.dropins._importable_entries` (`core/dropins.py:817-857`)
enumerates entries *under* a root and is confined by construction; this takes a
caller-supplied name and joins it.

**Why no test caught it.** `tests/panels/test_panel_registration.py:315` is
named `test_a_drop_in_provider_resolves_from_the_tier_the_panel_was_found_in`
and its docstring quotes FR-047 verbatim — *"a user-library panel never resolves
its provider out of the project's directory"* — but its body only writes
`renderer.py` into two roots and asserts each bare name `renderer` binds to its
own root (lines 322-333). It never asks whether a reference can leave a root.
**The test's name and docstring promise more than its body checks.**

**Class**: defect in the code (missing confinement), compounded by a defect in
the test (a name that overstates its body) and in the docstring (asserts a
property that does not hold).
**Fix**: resolve the candidate and require `relative_to(root.resolve())` before
`exec_module`, exactly as `editing.confined_panel_directory` does; and refuse a
`provider` module part that is not a dotted sequence of identifiers.

---

### 3.3 (P3 — code) A panel document is served as `text/html` from the application's own origin with no sandbox header

*Pass: "mounts third-party documents in a frame."*

The entire security argument for FR-008 is stated at
`frontend/src/panels/panelFrame.ts:16-19` and
`src/scistudio/api/routes/panels.py:26-31`: without `allow-same-origin` the
framed document runs at an opaque origin and cannot *"walk into the parent
document, read the application's storage, and call the API with the person's
credentials."*

That boundary is created by **one attribute on one code path**
(`panelFrame.ts:145`, `element.setAttribute("sandbox", PANEL_FRAME_SANDBOX)`).
The document itself is served by `serve_panel_asset`
(`api/routes/panels.py:184-202`) at `/api/panels/assets/{panel_id}/{asset_path}`
with `media_type` `text/html; charset=utf-8`
(`src/scistudio/panels/assets.py:65`) and exactly two headers:

```python
# src/scistudio/api/routes/panels.py:121-124
PANEL_ASSET_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Cross-Origin-Resource-Policy": "cross-origin",
}
```

No `Content-Security-Policy`, no `X-Frame-Options`, no `Content-Disposition`. A
third-party package panel, or a project panel that arrived with a shared
project, is therefore a same-origin HTML document that a browser will execute
with the application's origin if it is ever loaded outside the sandboxed frame —
by direct navigation, by a link, by `window.open`. The server does not enforce
the property the frontend's comment says the design depends on.

`Content-Security-Policy: sandbox allow-scripts` on this route's responses would
make the boundary a property of the document rather than of one call site. This
is defence in depth rather than a spec violation — no FR requires the header —
but the spec's own reasoning is what makes it worth having.

**Class**: defect in the code (a security property asserted in prose and
enforced on only one path).

### 3.4 (P3 — agreement) FR-021's "no other route" clause is neither true nor tested, and A-008's premise is inaccurate

FR-021: *"The route MUST answer read-only cross-origin requests … and **no other
route MUST answer such requests**, which is what keeps the asset route the only
thing a panel can reach without the host."* A-008: *"The asset route sends no
cross-origin read headers today; it gains them for its own responses only."*

**Evidence.** `src/scistudio/api/app.py:257-262` installs a global
`CORSMiddleware` over the whole application:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # default: localhost:5173/8000, 127.0.0.1:5173/8000
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`origins` becomes `["*"]` when `SCISTUDIO_CORS_ORIGINS=*`
(`app.py:244-246`). In that configuration every route answers every origin —
including the `null` origin a sandboxed panel presents — and FR-021's stated
invariant is gone. In the default configuration the invariant happens to hold
only because `"null"` is not in the allow-list, which is an accident of the
default rather than an enforced property. Either way, A-008's *"sends no
cross-origin read headers today"* was not accurate when written.

**No test defends any of it.** `grep -rn "PANEL_ASSET_CORS_HEADERS\|Access-Control" tests/ frontend/src`
returns **zero** matches. `tests/panels/test_panel_asset_route.py` covers
confinement, the suffix allowlist, traversal ids, symlinks, percent-encoding,
the size bound, directories, empty paths and remote URLs — i.e. all of SC-008 —
and nothing about the cross-origin half of FR-021.

**Class**: contract stated in a document with no test; document (A-008)
inaccurate about the code.

### 3.5 (P3 — code) A displaying panel drives host chrome with an unvalidated path

`grantedOutboundTypes` (`panelCapability.ts:78-84`) grants `host_action` to a
displaying mount, justified by D-017 as *"chrome the frame cannot perform for
itself … a download is not an emission, it is the host saving a file the panel
is already showing."* Two of the three actions match that description; the third
does not:

```ts
// frontend/src/components/DataPreview.parts/PreviewHost.tsx:559-572
function editorHandoffPath(envelope, params) {
  ...
  const candidates = [params?.path, handoff.path, envelope.payload?.path, envelope.metadata?.path];
```

`params` is the panel's own `host_action` payload, and `params.path` is taken
**first**, unvalidated, then passed to `useAppStore.getState().openFileTab(path)`
(`PreviewHost.tsx:366`). Impact is bounded — the project file route confines
with `relative_to(project_root)` (`api/routes/projects.py:150`, `484`) — so the
worst case is a panel opening an editor tab on a project file the person did not
ask for. But "open this arbitrary path in the editor" is not the thing D-017
argues a displaying panel needs, and FR-011 forbids it outright.

`export`/`download` are better constrained: the resource id must be one the
envelope declares (`exportResourceId`, `PreviewHost.tsx:551-556`) and the
destination comes from a native save dialog.

---

## 4. Findings — P3 / documentation and dead code

### 4.1 FR-041's second clause is unmet by the document that states it

FR-041 (`spec:489-491`) requires *"the spec MUST state how the renamed symbols'
stability markers are derived."* §4.5 (`spec:776-781`) restates the requirement
— *"FR-041 requires the spec to state how the renamed symbols' markers are
derived rather than leaving it to the implementer"* — and **the spec never
states the rule.** `grep -n "stability marker\|since=\|provisional"` over the
spec returns only those two passages and the §4.2 table row.

The rule does exist, but only in code and fixture: renamed symbols keep
`since="0.3.1"` (`core/panels.py:103`, `224`;
`tests/adr052_contract/expected_surface.json`), new ones get `since="0.3.4"`.
The inventory half of FR-041 is done and passing; the spec half is not.
**Class**: defect in a document.

### 4.2 `docs/adr/ADR-048.md` names three test files that no longer exist

Its `tests:` block lists `tests/api/test_previewers.py`,
`tests/previewers/test_preview_routing.py` and
`tests/previewers/test_preview_data_access.py`. None exists;
`tests/previewers/` is gone (correctly — spec §4.2 deletes it) and
`tests/api/test_previewers.py` is now `tests/api/test_panels.py`. `ADR-048.md`
**is** in the panel spec's `governs.files`, so updating it was in scope.

I checked every governed path in all nine documents in scope; these three are
the only unresolved live entries. `ADR-054.md`'s nine unresolved paths are all
under `planned_governs` (the explore session, which this spec's `scope.out`
excludes) and are correct as planned surfaces.

Worth noting for the tooling: `full_audit`'s `doc_drift` reports
`files_checked=827, findings=0`. It checks `governs.files` and does not check
the `tests:` block, which is why these three survived a passing audit.

### 4.3 Two specs claim the same three implementation files

`docs/specs/adr-051-interactive-blocks.md` `governs.files` still claims
`src/scistudio/blocks/base/interactive.py`,
`src/scistudio/engine/scheduler/_dispatch.py` and
`frontend/src/App.parts/InteractiveModals.tsx` — all three of which
`docs/specs/adr-054-panel-contract.md` `governs.files` also claims. The 051 spec
*was* updated for the type move (its `contracts` list names
`scistudio.core.panels.PanelManifest`), so the omission is partial rather than
wholesale. `ADR-051-addendum2.md` deliberately claims no code surface, which is
the right choice for a transfer record but leaves the transfer unrecorded on the
receiving side.

### 4.4 Two compiled-in interactive-panel components survive, kept alive by a test

`frontend/src/components/DataRouterModal.tsx` (178 lines),
`frontend/src/components/PairEditorModal.tsx` (200 lines) and the
`DataRouterModal.parts/` directory are still in the tree. Nothing in production
imports them: `grep -rn "DataRouterModal\|PairEditorModal" frontend/src`
returns only `interactiveModals.designSystem.test.tsx:11-44` (which mounts and
asserts on them), the `.parts/` files themselves, and one comment in
`Git/CommitDialog.tsx:12`. `InteractiveModals.tsx` now renders
`InteractivePanelHost` (line 84) and holds no built-in registry, so FR-037 is
satisfied — but the two React implementations of the two built-in interactive
panels sit beside their `core.interactive.*` documents, with a green test
asserting a component nothing mounts. This is the shape of failure ADR-054 §9
names ("a third implementation appearing beside the two it was meant to
replace"), and Story 5's *"a maintainer finds one mechanism"* is weakened by it.

### 4.5 The rename is partial in the panel subsystem itself

FR-038: *"The concept MUST be named panel throughout the code. The retired word
MUST survive only as the name of the displaying capability, in historical
documents, and in the compatibility shim."*

`grep -c previewer_id src/scistudio/panels/*.py` → **120** occurrences, on
`PanelSpec.previewer_id`, `PreviewEnvelope.previewer_id` and their consumers —
i.e. inside the renamed subsystem, not the shim.
`src/scistudio/panels/models.py:1` still opens *"Typed models for the extensible
preview subsystem."* Thirty-one frontend files still contain `previewer`
case-insensitively.

I judge this **defensible but undeclared**: `to_dict` (`core/panels.py:333-342`)
documents that the wire keys are the ones ADR-051 clients already read, and
FR-023/FR-051 scope the rename to endpoint naming and the `capabilities`→
`features` field (which *is* done — `PanelManifest.features`,
`PanelSpec.features`, `panel.json` `features`). But no governing document
records that the wire field `previewer_id` is exempt from FR-038, so FR-038 as
written and the tree as built disagree.

### 4.6 Contracts with no test

Beyond §3.4 (FR-021 cross-origin):

- **A-007** — the spec says T-011 carries its verification.
  `frontend/src/store/usePanelReload.ts:24-28` claims it is done and cites *"the
  report on A-007 **in the issue**"* — an out-of-repository reference for a
  security-relevant assumption. `tests/api/test_panel_document_events.py` covers
  the real gap that was found (`.html` missing from
  `ADR036_FILE_ALLOWLIST`) and covers it honestly, but nothing tests that echo
  suppression does not swallow an agent write.
- **FR-047 confinement** — see §3.2; the one test named for it does not test it.
- **FR-002 `entry` confinement** — `read_panel_declaration`
  (`core/panels.py:531`) checks `(directory / manifest.entry).is_file()` but
  neither confines `entry` to the directory nor checks it against
  `is_allowed_asset_suffix`, though both helpers exist and `editing._confined_file`
  applies exactly those checks on the write path. Consequence is bounded (the
  browser normalises `..` out of the URL and `resolve_confined_asset` would
  refuse it; a disallowed suffix yields a 404 at mount) — a self-inflicted load
  failure, not an escape. Still an asymmetry between the read and write paths.
- **`resolve_providers=False`** — `discovery.py:300` documents it as *"Off in a
  listing that must not execute package code."* No production caller passes it;
  every listing path executes provider code.

---

## 5. What I Verified Holds

Stated specifically, because "consistent" without evidence is not a finding.

| Claim | How I checked | Result |
|---|---|---|
| SC-001, Python half | `grep -rn PANEL_API_VERSION src frontend` | **One** definition, `core/panels.py:49`. `panels/models.py:56`, `blocks/base/interactive.py:61`, `panels/__init__.py:50` re-export it; `previewers/{__init__,models}.py` alias it as `PREVIEWER_API_VERSION`. The frontend spells **no** version literal — `panelDescriptor.ts` and `PanelHost.tsx` read `accepted_api_version` off the descriptor. (Documents: §2.2.) |
| SC-002 | `ls frontend/src/components/DataPreview.parts frontend/src/App.parts/InteractiveModals.parts` | `dynamicPreviewer.ts`, `previewerHostApi.ts`, `panelModuleLoader.ts`, `DynamicPanel.tsx`, `coreViewers.tsx`, `PlotViewer.tsx` — **all absent**. One loader (`mountPanelFrame`) remains. |
| SC-003 | `ls src/scistudio/panels/builtin/` | Exactly **11** directories, matching FR-033's nine previewers + two interactive panels, each holding exactly `index.html` + `panel.json` (pinned by `test_panel_directory_holds_nothing_but_its_own_two_files`). No external `<script src=`, `<link href=`, or `import()` in any of them — FR-034/A-004 self-containment holds. (Caveat: §4.4.) |
| SC-008 | `tests/panels/test_panel_asset_route.py` + reading `resolve_confined_asset` | One implementation (`panels/assets.py:190`), resolve-then-`relative_to`, suffix allowlist after confinement, `is_safe_panel_id` applied to the id before any join (`api/routes/panels.py:161`). Parametrised over all four tier roots. The two FR-022 routes (`api/routes/blocks.py:529`, `api/routes/data.py:537`) call the same function via `resolve_asset` — no second copy of the check. |
| SC-010 | `grep` for envelope-kind dispatch in the frontend | No mapping from a response's kind to a component survives. The one `kind ===` left (`PreviewHost.tsx:393`) is a tutorial telemetry predicate on `target.kind`, not a panel choice. `envelope_response` (`api/routes/panels.py:216`) stamps `panel`, `fallback_panel_id` and `fallback_panel`; `PreviewHost.tsx:403-425` mounts what it is told. |
| SC-012 | `lint-imports`, `full_audit`, `pytest tests/architecture tests/adr052_contract` | All green. The `Panels must not depend on engine, blocks, workflow, ai, or api` contract is a real import-linter contract, so FR-001's layering claim is machine-enforced rather than asserted. |
| SC-013 | Read `ADR-048-addendum1.md:197-252` | Three clauses, each *"settled by looking rather than by judging"*, plus an explicit deletion list. `compat.py:39-55` repeats the same list file-by-file. FR-044 satisfied. |
| SC-016 | `tests/panels/test_panel_capability_gate.py:53-63` | Refusal happens in `blocks.registry._capability._validate_interactive_capability` at **discovery**, and the diagnostic names the block, the panel and `producing`. `test_the_check_runs_before_the_block_ever_pauses` guards the timing. |
| FR-008 | Read `panelFrame.ts` | `PANEL_FRAME_SANDBOX = "allow-scripts"` and nothing else; `referrerpolicy="no-referrer"`; **both** replacement checks applied to every inbound message — `event.source !== handle.contentWindow` (line 173) **and** the per-mount token (`isPanelEnvelope`, `panelMessages.ts:355`). Token issued per **mount**, not per panel, from `crypto.randomUUID`. `isPanelDocumentUrl` refuses remote, protocol-relative, `data:`, `blob:` and `javascript:` URLs. |
| FR-009 / FR-014 / SC-006 | Read `panelFrame.ts:404-748` | Four bounded waits (load 10s, handshake 5s, read 15s, state 1s), eight typed failure reasons, and one behaviour: a `PanelFailure` naming the panel, `dispose()`, error surface, fallback. The guards `try/catch` every property access — correct for a hostile document. |
| FR-011 emit half / SC-007 | Read `panelCapability.ts:130-176`, `PanelHost.tsx:293-297` | The gate is **structural**, not a conditional: `emitConsumer` is `null` for a displaying mount, so there is nothing behind the gate to reach by accident. Tested from the host's side (`panelCapability.test.ts:61-89`) by observing the consumer is never called. |
| FR-019 / FR-026 / FR-027 | Read `discovery.py:355-370`, `editing.py:305-336` | Shadowing walks `PANEL_TIER_ORDER` most-shadowing-first; losers are kept in `shadowed` rather than dropped, which is what lets `_shadowed_tier` answer "is there anything to revert to". Copy-on-write keeps the id, skips symlinks, and confines every copied file to the destination. |
| FR-031 | Read `PanelHost.tsx:349-431`, `panelMessages.ts:527-552` | The snapshot rides `carriedState` keyed on `panelId`, is consumed exactly once, and `sanitizePanelState` discards anything that will not `JSON.stringify` rather than failing the reload — matching the Edge Cases entry verbatim. |
| FR-042 / FR-043 / SC-009 | Read `compat.py` | The shim wraps the retired module form into a real panel directory rather than restoring a second loader — so SC-001/SC-002 stay true. The generated declaration is `capability: "displaying"`, and the adapter document constructs no emit path at all: "enforced twice", and both halves are real. Bundle copy is bounded (200 files / 32 MiB) and filtered by the same suffix allowlist. |
| FR-048 / FR-049 | Read `panels/router.py:109-170`, `panels/choices.py` | Candidates are filtered by `spec.capability.satisfies(capability)` **before** the ladder (`router.py:159`); a producing request that finds nothing falls back to the displaying resolution and the descriptor is built with `granted_capability=DISPLAYING` (`router.py:126-133`). The choices file is versioned, one map per capability, and a version-1 file is read whole as the displaying layer. |
| FR-050 | `dispatch.py:576-579`, `_validate_interactive_capability` | Manifest resolved before the announce branch; `PanelManifest.capability` defaults to `PRODUCING` precisely because the only Python constructor is a block class. |

---

## 6. Recommendation

**pass-with-fixes.**

Blocking, in my judgement, is one item:

- **§3.2** — the unconfined `provider` join. It is a filesystem-reachable
  arbitrary-code-execution path that fires on project open, in a module whose
  docstring asserts the confinement, in a repository that lists three prior
  incidents of this exact class fifty lines away in a sibling module. The fix is
  four lines and mirrors code that already exists.

Should land with it, cheaply:

- **§2.2** — import `PANEL_API_VERSION` into `tests/panels/test_builtin_panels.py`
  instead of restating it. One line, and it converts a test that would survive a
  version bump into one that would not.
- **§3.1** — extend `_refuse_dunder_reach` to string constants.
- **§4.2** — three stale paths in `ADR-048.md`'s `tests:` block.

Should be decided rather than fixed:

- **§2.3** — either build the revert control FR-028 requires, or amend FR-028/
  FR-029 to describe what shipped. The backend for it is complete and tested;
  what is missing is the frontend, and shipping the requirement unmet is the
  worse of the two options.
- **§2.1** — the D-0NN references. Whatever the decision, FR-011's text and
  `panelCapability.ts` should stop disagreeing.

Everything in §4 and the remaining §3 items is ordinary follow-up.
