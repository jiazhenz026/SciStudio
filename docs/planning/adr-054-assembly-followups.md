---
title: "ADR-054 Assembly — Follow-Up Register"
status: Active
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly — Follow-Up Register

The owner forbade new GitHub issues for this dispatch beyond the two
implementation issues (`#2253`, `#2254`). Every deferral, edge case, cleanup and
follow-up an assembly agent finds is recorded here instead, under that agent's
heading, and cited from the `TODO(#NNN)` that defers it.

An entry is a deferral, not a decision. The manager triages this register when
the assembly lands and opens issues for what survives triage.

## S5-B4

### F-B4-1 — The eleven-tool count and catalog move is blocked on S5-B2 and S5-B3

FR-025 and FR-026 require the total tool count, the per-group counts, and every
catalog that lists tools to move for the eleven tools spec 5 adds — four panel
tools (S5-B2, `tools_panels/**`) and seven session tools (S5-B3,
`tools_explore/**`). Neither branch carried a registered tool when this work
landed: `feat/2254-panel-tools` was still at the track head and
`feat/2254-session-tools` did not exist. The S5-B4 dispatch's stop condition is
explicit — take the registered names from those agents' reports rather than
guessing one — so the numbers were **not** moved here.

What did land, and is correct at 36 tools and at 47:

- `tests/ai/test_tool_catalogs.py` reads the live registry and asserts every
  registered tool name appears in each catalog. The assertion is
  one-directional, so it stays green while the catalogs are ahead of the
  registry and **fails loudly, naming the missing tools, the moment the two
  groups register**. That failure is the reminder FR-026 exists to produce.
- The catalogs were brought level with the *current* registry: the base skill's
  static fallback said 35 tools and omitted the whole Library group
  (`promote_to_user_library`, ADR-053 FR-011), and the embedded coding agent
  spec named none of `edit_workflow`, `finish_ai_block`,
  `get_active_workflow_context`, `open_gui`, the six plot tools, or
  `promote_to_user_library`. Both now name all 36.

What still has to move when the two groups land, in one pass:

1. `tests/ai/test_mcp_fastmcp.py` — `_EXPECTED_TOOL_NAMES` gains the eleven
   names; `test_fastmcp_lists_36_tools` becomes 47.
2. `tests/ai/test_finish_ai_block_skeleton.py` —
   `test_registry_now_has_36_tools` becomes 47.
3. `tests/ai/test_tool_catalogs.py` —
   `test_tool_group_counts_match_the_declared_breakdown` gains
   `"panels": 4` and `"explore": 7`.
4. `src/scistudio/_skills/scistudio/SKILL.md` — the static fallback gains a
   Panels group and an Explore-session group, and the two "36 tools" statements
   become 47.
5. `docs/specs/embedded-coding-agent-spec.md` §1.1 — the same two groups and
   the same total.

Cited from the `TODO(#2254)` on
`test_tool_group_counts_match_the_declared_breakdown`.

### F-B4-2 — `docs/architecture/ARCHITECTURE.md` still carries a stale tool table

The architecture document's tool table is the third catalog FR-026 names, and it
is excluded from `tests/ai/test_tool_catalogs.py` because the document is a
guarded, owner-controlled path (`docs/ai-developer/rules.md` §4,
`admin-approved:architecture-doc`). ADR-054 spec 5 §4.5 and A-006 put its update
in the documentation spec's batch, **#2236**. When that batch lands, add the
document to `_CATALOGS` in the catalog test and delete the exclusion paragraph
from its module docstring — at which point the test will also flag whatever the
table is currently missing, which is at least the same nine tools the agent spec
was missing.

Cited from the `TODO(#2236)` in `tests/ai/test_tool_catalogs.py`.

### F-B4-3 — The panel examples corpus and `list_panel_examples` must agree

FR-017 gives S5-B2 a `list_panel_examples` tool that "returns the panel examples
in the corpus"; FR-027 gives S5-B4 the corpus. The corpus is the shipped worked
examples tree, `src/scistudio/_user_guide/examples/`, which provisioning copies
into every project as `user-guide/examples/`, and its curation lives in
`_CORPUS_EXAMPLES` in `src/scistudio/ai/agent/mcp/tools_authoring.py` beside the
block curation that was already there. `list_corpus_examples("panel")` is
exported from that module for `tools_panels` to call, so that there is one
corpus with one place to add to.

If `list_panel_examples` ships reading the built-in panel registry
(`src/scistudio/panels/builtin/`) instead, the two are different sets and FR-017's
"at least one displaying and one producing" is being satisfied by accident rather
than by the corpus. Reconcile at integration: either `list_panel_examples` calls
`list_corpus_examples`, or the corpus curation names the built-in panel ids. The
choice is the manager's; what must not survive is two lists.

### F-B4-4 — `public-api.md` still names `scistudio.previewers` as a canonical root

The canonical-root table in `src/scistudio/_agent_reference/public-api.md` lists
`scistudio.previewers.models` and `scistudio.previewers.data_access`. ADR-054
spec 1 renamed that subsystem to `scistudio.panels`. The rows were left alone
here because the panel-facing reference documents are S5-B2's write set
(`panel-contract.md`, the panel section of `block-contract.md`) and rewriting a
canonical-root row for a subsystem this agent does not own would be two agents
editing one surface. It is a one-line correction for whoever holds the panel
reference documents, or for the spec 6 documentation batch.

### F-B4-5 — The skill count moves in six places, not four

The S5-B4 dispatch and spec 5 FR-009 name four places the task-skill count
lives. There are six. Beyond the orchestration list
(`agent_provisioning/_orchestrate.py`), the skills index
(`agent_provisioning/skills.py`), the provisioning template's prose
(`agent_provisioning/templates/claude_agents_md.md`) and the provisioning test
(`tests/agent_provisioning/test_skills.py`), two more count the same thing:

- `tests/agent_provisioning/test_orchestrate.py` asserts the number of skill
  files the orchestrator writes (`14` → `16`), and
- `tests/packaging/test_wheel_skills.py` carries a `_TASK_SKILLS` tuple that
  every wheel-install skill assertion iterates.

Both were moved with the other four in this change, so nothing is broken. The
follow-up is that FR-009's list is one short of the truth, and the next skill
added will discover the same two the hard way. Worth folding the real list into
the spec, or better, deriving all six from `skills._SKILL_NAMES` so the number
lives once.

### F-B4-6 — `tests/ai/test_mcp_server_skeleton.py` was deliberately not touched

Spec 5 §4.2 lists this file among the count assertions FR-025 moves, and the
S5-B4 write set repeats it. It was left alone. The whole module carries a
`pytestmark = pytest.mark.skip` and a `TODO(#1539)` saying its assertions encode
the ADR-033-era `MCPServer` shape — a hand-rolled JSON-RPC server and a 25-tool
registry across four `tools_*` modules — that the FastMCP migration permanently
superseded. Its `test_total_tool_count_is_25` asserts `9 + 5 + 7 + 4`, which has
not described the registry since ADR-040.

Adding two 2026 tool groups to a skipped test whose total is eleven behind the
truth would make it look maintained without making it run. The live per-group
assertion landed in `tests/ai/test_tool_catalogs.py` instead, reading the
`category:` tags the server actually reports. The re-author of the skeleton file
is already tracked by #1012 / #1539; nothing here changes that.
