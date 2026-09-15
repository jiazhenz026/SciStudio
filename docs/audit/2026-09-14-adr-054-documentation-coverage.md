---
title: "ADR-054 Documentation And Agent Teaching Coverage Audit"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [40, 48, 49, 51, 52, 53, 54, 55]
related_specs: [adr-054-panels, adr-054-miniapp]
language_source: en
---

# ADR-054 Documentation And Agent Teaching Coverage Audit

## 1. Findings

**Recommendation: do not call all ADR-054 documentation complete.** Phase D has
a real MiniApp skill, provisioning, live tool descriptions, tips, and updated
dialog specifications. It lacks the human MiniApp guide and still routes block
conversion into legacy panel-authoring instructions. Most Phase C documentation
was explicitly deferred, rather than accidentally omitted from Phase D.

This is a source audit of `feat/2354-miniapp-phase-d` at **3c1439d1**. The first
pass used 8ca7ecd4; the final pass includes the later committed skill rewrite.
Screenshot tooling, renderer guidance, and consumer-guide repairs being developed
in parallel are **pending** here, not credited as delivered. No application,
consumer document, or other agent's worktree was modified by this audit.

### P1 — Finish the skill/tool pairing before shipping the current candidate

**D1. The rewritten MiniApp skill instructs an unavailable screenshot tool.**
`src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md:95` now tells the
agent to use `screenshot_gui`. At this audit revision the MCP implementation has
`open_gui` at `src/scistudio/ai/agent/mcp/tools_qa.py:399`, which returns a URL,
but no registered `screenshot_gui`. Therefore its required visual verification
step cannot be followed from the shipped SciStudio tool surface. The original
8ca7ecd4 skill did not require this tool; it stopped at descriptor validation
and an open request. This is a current integration dependency, not proof that
the in-progress screenshot implementation is defective. Land that tool with its
real input/result shape and verify its image reaches the agent before release.

### P2 — Phase D teaching gaps to close with the current feature

**D2. Conversion sends the agent to the old panel recipe.**
`src/scistudio/panels/miniapp_create.py:382` directs conversion to
`scistudio-write-block`; that skill at line 22 directs the agent to
`.scistudio/agent-reference/block-contract.md`. The packaged source
`src/scistudio/_agent_reference/block-contract.md:45` teaches an ES module,
`module_url`, and `mount(container, host)` (lines 54–66), rather than a discovered
`panel.json` folder and the frame SDK's `writeBack`. Legacy compatibility through
0.5.x makes this obsolete guidance rather than proof every conversion crashes.
Nevertheless it actively guides a new Phase D output onto the deprecated form.
Update this conversion teaching path now; the general panel skill remains Phase C
(panels spec FR-045, lines 784–791).

**D3. The shipped human guide contains no MiniApp workflow.**
`src/scistudio/_user_guide/README.md:21` lists the guide's app pages and line 32
lists authoring pages. Neither it nor the guide tree contains MiniApp or All
Previewers instructions. `using-the-gui.md:81` describes previews and quick plots
only. Users cannot learn creation, source prerequisites, single-click opening,
stop/restart and lost runtime state, conversion, or the move to My Library.
This also affects AI documentation search and the actual Learning Center Reading
tab: `src/scistudio/api/routes/user_docs.py:17` serves the packaged `_user_guide`
tree. Tips are present but are not a procedural guide. This requirement follows
the shipped UI semantics in MiniApp FR-018–FR-039 and AGENTS.md §3.4; the current
Phase D checklist does not explicitly inventory this consumer surface.

**D4. The MiniApp specification contradicts the approved memory presentation.**
`docs/specs/adr-054-miniapp.md:439` correctly prohibits memory figures in the
normal interface, while line 729 still says the tab shows memory so users can
stop it. `docs/adr/ADR-054.md:738` says memory is made visible without identifying
the diagnostics-only surface. Reconcile those sentences with FR-015 and the
owner's guided decision; keep backend measurements documented as diagnostics.

### P2 — Separately tracked Phase C work, not Phase D regressions

**C1. The panel authoring and migration guide has not landed.**
`docs/specs/adr-054-panels.md:776` (FR-044) requires
`docs/package-development/panels.md`; that file is absent. The actual existing
guide, `docs/package-development/previewers.md:13`, still introduces the two-half
Python-provider/ES-module design as the normal authoring path, without a 0.6
migration section. The index (line 27), architecture (line 76), publishing
(line 33), and blocks page (line 146) still teach/link only that form. Required
folder/schema, SDK/read contracts, local libraries, offline/CDN caveats, sample
testing, contexts, and four-tier discovery have no complete developer guide.

**C2. The general panel skill and its reference network are absent.**
FR-045 at `docs/specs/adr-054-panels.md:784` requires
`scistudio-write-panel/SKILL.md`, provisioning, and links from the base,
write-block, inspect-data skills and `_agent_reference`. The file and provisioning
entry do not exist. `scistudio-inspect-data/SKILL.md:66` mentions richer views but
does not route to the new panel authoring contract. The MiniApp skill is real,
but does not replace the preview/interactive panel skill promised by Phase C.

**C3. Supersession notes and public API prose are incomplete.**
FR-047 at `docs/specs/adr-054-panels.md:797` requires the ADR-048 and ADR-051 specs
to say which frontend contracts are replaced. Neither has an ADR-054 note; for
example `docs/specs/adr-051-interactive-blocks.md:226` still describes built-in
components and dynamic `module_url` imports. `src/scistudio/blocks/base/interactive.py:83`
retains that description in the public `PanelManifest` docstring, and the
packaged generated reference repeats it at
`src/scistudio/_user_guide/api-reference/scistudio.blocks.base.md:299`.
The generator is faithfully repeating stale source prose; rebuilding alone
cannot repair it. The enterprise spec does document the token exception but
still says panels are paused (`adr-055-enterprise-support.md:311`), despite
`api/routes/panels.py:939` registering the prefix now.

**C4. The requested architecture proposal is not present.**
FR-048 at `docs/specs/adr-054-panels.md:802` calls for proposed revisions to
ARCHITECTURE.md §9.6, §12.2.3, §5.3.1 and the project layout. Existing
`docs/planning/adr-054-owner-doc-proposal.md` is the Phase A ADR/spec metadata,
security, and transport patch, not those architecture sections. Current
`docs/architecture/ARCHITECTURE.md:1774` and line 2204 still describe only
`previewers/` drop-ins; the new `panels/` project location is absent. Proposal
and owner application remain separate; this audit does not authorize editing
that protected document.

### P3 — Remaining consistency and release housekeeping

- `src/scistudio/_skills/scistudio/SKILL.md:107` says 35 tools while its static
  catalog at line 125 says 38. Real category rendering includes panels and
  library (`ai/agent/system_prompt.py:195`); refresh counts when screenshot tools
  land, or avoid a brittle prose count. The library fallback correctly says
  block promotion: the current MCP promotion tool is block-only, while the
  directory promotion UI uses a separate HTTP route. Do not document a nonexistent
  MCP MiniApp promotion signature.
- `CHANGELOG.md` has no MiniApp feature entry, and `README.md:106` routes package
  authors only to the existing previewer guide. The changelog was explicitly N/A
  during the guided checkpoint; add the release-facing entry when preparing the
  combined feature PR. A main README feature paragraph is optional; navigation
  into the real consumer/developer pages is the essential fix.

## 2. Required Artifact And Delivery Matrix

Line anchors below refer to 3c1439d1. Missing paths have no invented line number.

| Requirement and source | Actual artifact / consumer | Status at audit revision |
| --- | --- | --- |
| A: panel/context/read/SDK/token/CDN contracts; panels FR-001–FR-039 | `docs/adr/ADR-054.md` §§2–8; `docs/specs/adr-054-panels.md` §§3–4; `docs/planning/adr-054-{backend,frontend,security,contract}-notes.md` | Written technical contracts/evidence; ADR Proposed and specs Draft, not accepted user guides |
| B: nine core viewers and two interactive panels; FR-040–FR-043 | `docs/planning/adr-054-phase-b-parity.md`; actual `panels/builtin/*` folders with `panel.sample.json` | Written migration/parity evidence and runnable asset examples; not an authoring guide |
| C: full panel author guide; FR-044 | `docs/package-development/panels.md` | Missing, tracked #2295 |
| C: legacy guide through 0.5.x with 0.6 migration; FR-044 | `docs/package-development/previewers.md:13` | Written but old design is still the recommended form |
| C: package docs entry points and cross-links; FR-044 | package-development `index.md:27`, `architecture.md:76`, `publishing.md:33`, `blocks.md:146` | Not updated for `scistudio.panels` / panel folders |
| C: general panel skill, index, provisioning; FR-045 | `_skills/scistudio/scistudio-write-panel/SKILL.md`; `agent_provisioning/skills.py:87` | Skill absent, no provisioning entry |
| C/D: block authoring and conversion teaching; FR-045 / MiniApp FR-036 | `_skills/.../scistudio-write-block/SKILL.md:22`; `_agent_reference/block-contract.md:45` | Old ES-module recipe; affects shipped conversion directly |
| C: inspect-data and reference cross-links; FR-045 | `_skills/.../scistudio-inspect-data/SKILL.md:66`; `_agent_reference/README.md` and `package-discovery.md` | No new panel reference/skill links |
| C: source-free page checks; FR-046 | `panels/sdk/1/scistudio-panel.js:332`; builtin sample JSON | Sample mechanism exists; full author instructions remain missing |
| C: ADR-048/051 supersession; FR-047 | `docs/specs/adr-048-preview-system.md`; `adr-051-interactive-blocks.md:226` | Supersession notes missing |
| A/C: ADR-049 contract rows; FR-038 / FR-047 | `docs/adr/ADR-049.md:394` and 410 | Written, explicitly partial; does not falsely claim full install-validator enforcement |
| A/C: enterprise token exception; FR-026 / FR-047 | `docs/specs/adr-055-enterprise-support.md:311`, 418 | Contract written; sequencing text stale (“paused”) |
| C: architecture proposal; FR-048 | `docs/planning/adr-054-owner-doc-proposal.md`; `ARCHITECTURE.md:1774` | Phase A proposal exists; required architecture proposal still missing |
| C/E: tutorial assets/copy; FR-049 | `tutorials/core/what-is-a-type/tutorial.yaml:366`, 597; legacy `panel.mjs` / `image_preview.py` | Not migrated; explicitly deferred from #2295 to #2288 by owner |
| D: MiniApp authoring skill; FR-028 | `_skills/.../scistudio-write-miniapp/SKILL.md` | Real, substantially rewritten; screenshot tool dependency pending D1 |
| D: packaged skill and provider installation; FR-028 | `pyproject.toml:143`; `agent_provisioning/skills.py:87`; `tests/packaging/test_wheel_skills.py:27` | Bundle glob, eight-name list and resource-test inventory agree; no source evidence of omission |
| D: tool schemas and live prompt; FR-029/030 | `ai/agent/mcp/tools_panels.py:130`, 215; `ai/agent/system_prompt.py:195`; base skill catalog | validate/open signatures and categories present; screenshot feature not present at baseline |
| D: human creation/use/convert/library instructions; FR-018–FR-039 + AGENTS §3.4 | `_user_guide/README.md:21`, `using-the-gui.md:81`, `ai-assistant.md` | MiniApp guide and links missing |
| D: user-guide delivery / Learning Center Reading | `agent_provisioning/docs.py:39`; `api/routes/user_docs.py:17`; `pyproject.toml:151` | Working delivery mechanism, but no MiniApp content to deliver |
| D: introductory tips; FR-038 | `frontend/src/components/palette/tips/tipPool.ts:121`, 126, 211 | Written: purpose, Python, ask-agent entry |
| D: All Previewers tutorial route/copy; FR-040 | welcome tutorial lines 363–378; what-is-a-type line 730; `docs/specs/adr-053-learning-center.md` | Written; route vocabulary retained and user text names All Previewers |
| D: latest guided UI semantics | `docs/specs/adr-054-miniapp.md:820` onward | Written: project source isolation, single click, labels, automatic ports, native type select, conversion explanation and icon close |
| D: memory/lifecycle/dependencies | MiniApp FR-008–FR-015; `panels/process_config.py`; rewritten MiniApp skill | Runtime contracts written; user troubleshooting absent; stale memory sentence D4 |
| C/D: generated Python reference | `docs/user/reference/`; `_user_guide/api-reference/`; `mkdocs.yml` | Existing public modules covered; PanelManifest prose stale at source; do not add internal `scistudio.panels` Python APIs as public roots |
| C/D: committed GUI e2e scenario; specs §4.4 | `docs/ai-developer/e2e/` | No ADR-054 panel/MiniApp scenario found; checklist explicitly routes this to Phase C/E |
| Release entry and navigation | `CHANGELOG.md`; `README.md:106`; user-guide index | No MiniApp release note or human-guide entry yet |

## 3. Packaging, Other Branches, And Scope Boundaries

The `_skills` source is package data and provisioning writes flat sibling skill
directories to both `.claude/skills` and `.agents/skills`. `_user_guide` and
`_agent_reference` are likewise package data. The Learning Center uses the
packaged tree, not the project's possibly older copy. This review inspected the
source globs, names, copy logic and test inventories; it did not build a fresh
wheel or inspect a released installer. “No missing bundle entry” is not a claim
that all existing user projects have already refreshed their managed files.

The Phase B branch tip **64efc4fc** has one later runtime/test fix commit absent
from the initial integration base. That commit adds no missing user guide,
package-development guide, or skill: those documents are not waiting there.

Other local branches contain `adr-054-documentation.md` and
`adr-054-agent-enablement.md` drafts dated September 2. They describe an earlier
explore-session/notebook design, are not in this integration branch, and are not
consumer documentation. They were inspected as possible prior work, not treated
as governing requirements for the later panel/MiniApp design.

Issue **#2295** is open and explicitly owns FR-044/045/047/048 and the Phase C
e2e scenario. It says the tutorial stays unchanged and defers it to **#2288**.
The Phase D checklist (`docs/planning/adr-054-phase-d-checklist.md:89`) likewise
excludes Phase C authoring/migration docs and Phase E tutorial rewrite. These
deferrals are real tracked scope boundaries, not completed documents. No new
CLI command is required for the MiniApp feature: the implemented author entry is
MCP plus the existing install/provisioning path, documented in
`docs/cli-integration.md:121`. External package migrations remain #2288 work in
their respective repositories.

## 4. Minimum Follow-Up

For the Phase D PR, complete D1–D4: land screenshot tool plus truthful visual
verification instructions; fix the conversion-specific interactive panel
recipe; add one concise MiniApp human guide with index/GUI/AI links; reconcile
memory wording. Document creation, source selection, single-click opening,
restart/stop/close behavior, export versus workflow output, conversion, and
project-to-library moves. Include current renderer/screenshot guidance when its
implementation lands. Add the release note and update tool catalogs/counts.

Keep the general panel author guide, full legacy migration, write-panel skill,
architecture proposal, general spec supersession and tutorial migration on their
existing Phase C/E issues. The conversion-specific repair does not require
silently delivering all of Phase C. Re-run this matrix against the final combined
commit before claiming the documentation gaps closed.

Evidence is source inspection, `rg` inventories, branch comparisons, and read-only
issue queries. No GUI run, wheel installation, native Windows test, full test
suite, or CI result is claimed by this report.
