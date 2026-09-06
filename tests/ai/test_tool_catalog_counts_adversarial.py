"""Adversarial tests against the counts and the catalogs: are they derived, or restated?

ADR-054 spec 5, FR-025 and FR-026; ADR-054 §8.4 (issue #2254).
Adversarial pass, agent S5-D1.

ADR-054 §8.4 makes a promise about maintenance, and FR-025/FR-026 are how spec 5
keeps it: *"a tool added without updating them fails the suite in places that do
not mention the tool."* ``tests/mcp_tool_expectations.py`` and
``tests/ai/test_tool_catalogs.py`` deliver most of it — the name set is declared
once, the total is derived from it, and each catalog is searched for every
registered tool **name**.

What is not covered is the arithmetic the catalogs also carry. Both live
catalogs state a *number* beside every group and, in the base skill, a total
twice over:

    **Static fallback (47 tools — ...)**
    - **Workflow (12)** — ...

Nothing reads those digits. A ninth tool added to the session group updates the
name list, passes ``test_catalog_lists_every_registered_tool``, and leaves the
base skill telling every Codex agent that there are seven session tools and
forty-seven in total. That is the same failure §8.4 exists to prevent, one layer
below where the existing assertion looks.

The same is true of the task-skill count FR-009 requires be moved: the base
skill says "the seven task skills" and the provisioning template says "the seven
task skills sit beside it", and the provisioning suite counts *files written*
rather than either sentence.

The tests here close that gap, and two meta-tests prove the existing catalog
assertions really do bite — a suite whose teeth nobody has checked is a suite
that may already have none.
"""

from __future__ import annotations

import ast
import asyncio
import re
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

import tests.ai.test_tool_catalogs as catalog_tests
from scistudio.agent_provisioning.skills import _SKILL_NAMES
from scistudio.ai.agent.mcp import mcp
from tests.mcp_tool_expectations import EXPECTED_GROUP_COUNTS, EXPECTED_TOOL_COUNT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPECTATIONS = _REPO_ROOT / "tests" / "mcp_tool_expectations.py"
_BASE_SKILL = _REPO_ROOT / "src" / "scistudio" / "_skills" / "scistudio" / "SKILL.md"
_AGENT_SPEC = _REPO_ROOT / "docs" / "specs" / "embedded-coding-agent-spec.md"
_PROVISIONING_TEMPLATE = _REPO_ROOT / "src" / "scistudio" / "agent_provisioning" / "templates" / "claude_agents_md.md"

#: The prose catalogs that carry per-group digits. The architecture document is
#: excluded for the same reason ``test_tool_catalogs.py`` excludes it: it is a
#: guarded owner-controlled path whose update lands in #2236.
_COUNTED_CATALOGS: dict[str, Path] = {
    "base skill static fallback": _BASE_SKILL,
    "embedded coding agent spec": _AGENT_SPEC,
}

#: ``**Workflow (12)**`` / ``**QA / project (5)**`` — the shape both catalogs use
#: for a group heading with its count.
_GROUP_HEADING = re.compile(r"\*\*([A-Za-z][A-Za-z /]*?)\s*\((\d+)\)\*\*")

#: ``(47 tools`` — the total, stated in prose.
_PROSE_TOTAL = re.compile(r"\((\d+) tools\b")

_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _registered_count() -> int:
    return len(_run(mcp.list_tools()))


def _group_label(raw: str) -> str:
    """``QA / project`` -> ``qa``; the catalogs label groups more prosaically than the tags."""
    return raw.strip().split("/")[0].strip().lower()


# ---------------------------------------------------------------------------
# The digits nobody reads
# ---------------------------------------------------------------------------


def test_the_base_skills_prose_tool_total_matches_the_registry() -> None:
    """Proves the total the agent is told matches the total the server serves.

    The base skill states the total twice — once describing the live splice and
    once labelling the static fallback — and the second is the only catalog a
    Codex agent ever sees, because the splice does not run there. A wrong number
    beside a right list teaches the agent to stop reading at forty-seven.

    Why the existing tests did not ask: ``test_catalog_lists_every_registered
    _tool`` searches the catalog text for each tool **name** and never looks at a
    digit; ``test_base_skill_tool_catalog_block_lists_every_tool`` does the same
    inside the splice markers. Both pass with any total whatsoever.

    Pushed here, and the number is correct today. The value of the test is that
    it will not stay correct silently.
    """
    text = _BASE_SKILL.read_text(encoding="utf-8")
    stated = [int(match.group(1)) for match in _PROSE_TOTAL.finditer(text)]

    assert stated, "the base skill no longer states a tool total; the assertion below has nothing to hold"
    registered = _registered_count()
    wrong = [value for value in stated if value != registered]
    assert not wrong, (
        f"the base skill tells the agent there are {wrong} tools; the registry serves {registered}. "
        f"ADR-054 §8.4: a tool change moves every catalog that enumerates the tool set, and the "
        f"count in prose is part of the catalog."
    )
    assert registered == EXPECTED_TOOL_COUNT, "and the declared expectation must agree with both"


@pytest.mark.parametrize("catalog_name", sorted(_COUNTED_CATALOGS))
def test_every_catalog_group_count_matches_the_registry(catalog_name: str) -> None:
    """Proves each catalog's per-group digits are the registry's, group by group.

    FR-025 requires the per-group assertions to gain the two new groups, and
    ``test_tool_group_counts_match_the_declared_breakdown`` does that against the
    live tags. The catalogs restate the same eight numbers in prose, in two
    documents, and neither restatement is checked against anything. Counting
    right in the test suite while the document the agent actually reads says
    something else is the failure mode FR-026 exists to prevent.

    Why the existing tests did not ask: the catalog test asserts membership
    (every name appears somewhere in the file) and the group test asserts counts
    (against ``EXPECTED_GROUP_COUNTS``). Nothing joins the two — nothing reads
    the counts *out of the catalogs*.

    Pushed here, and every number is correct today.
    """
    text = _COUNTED_CATALOGS[catalog_name].read_text(encoding="utf-8")
    stated = {_group_label(label): int(count) for label, count in _GROUP_HEADING.findall(text)}
    relevant = {group: count for group, count in stated.items() if group in EXPECTED_GROUP_COUNTS}

    missing = sorted(set(EXPECTED_GROUP_COUNTS) - set(relevant))
    assert not missing, (
        f"{catalog_name} states no count for these registered tool groups: {missing}. "
        f"A group with no heading is a group the agent never learns exists."
    )
    wrong = {
        group: (count, EXPECTED_GROUP_COUNTS[group])
        for group, count in relevant.items()
        if count != EXPECTED_GROUP_COUNTS[group]
    }
    assert not wrong, f"{catalog_name} states stale group counts (stated, actual): {wrong}"


def test_the_prose_task_skill_counts_match_the_provisioned_skill_list() -> None:
    """Proves FR-009's two prose counts against the list provisioning actually writes.

    FR-009 names four things that must move for an added skill: the
    orchestration, the skill list, "the provisioning template's statement of the
    task-skill count", and the provisioning test that counts written files. The
    fourth is asserted (``assert len(written) == 16``). The third is a sentence
    in ``claude_agents_md.md``, and the base skill carries the same sentence
    again. Neither is read by any test, so the seventh skill landed correctly and
    the eighth need not.

    Why the existing tests did not ask: ``tests/agent_provisioning/test_skills.py``
    holds its own copy of the skill names and asserts the number of files
    written. A file count moves when a skill is added; an English sentence does
    not.

    Pushed here, and both sentences are correct today.
    """
    task_skills = len(_SKILL_NAMES) - 1  # the base skill is not a task skill
    assert task_skills > 0

    pattern = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r"|\d+)\s+task skills\b", re.IGNORECASE)
    for label, path in (("base skill", _BASE_SKILL), ("provisioning template", _PROVISIONING_TEMPLATE)):
        text = path.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        assert matches, f"{label} ({path.name}) no longer states a task-skill count in prose"
        for raw in matches:
            stated = _NUMBER_WORDS.get(raw.lower()) if not raw.isdigit() else int(raw)
            assert stated == task_skills, (
                f"{label} says there are {raw!r} task skills; provisioning writes {task_skills} "
                f"({sorted(name for name in _SKILL_NAMES if name != 'scistudio')}). FR-009 moves this sentence."
            )


# ---------------------------------------------------------------------------
# Meta — does the existing suite actually bite?
# ---------------------------------------------------------------------------


def _register_probe_tool(name: str, *, category: str) -> None:
    @mcp.tool(name=name, tags={f"category:{category}", "read"})
    async def _probe() -> str:
        """A tool registered by an adversarial test and removed again."""
        return "probe"


def _remove_probe_tool(name: str) -> None:
    provider = getattr(mcp, "local_provider", mcp)
    provider.remove_tool(name)


def test_a_tool_registered_without_a_catalog_entry_fails_the_catalog_assertion() -> None:
    """Proves ADR-054 §8.4's promise is real: an uncatalogued tool fails the suite.

    §8.4 is a claim about what happens to a maintainer who forgets, and FR-026
    is the mechanism. A claim like that is worth executing rather than reading:
    a substring search over prose is exactly the kind of assertion that can be
    subtly toothless — a name that happens to appear in a paragraph for an
    unrelated reason, a catalog path that silently stopped existing, a search
    over the wrong file.

    So this registers a tool the catalogs have never heard of, runs the real
    catalog assertion, and requires it to fail — for each catalog separately, so
    a catalog that quietly went missing cannot hide behind the other.

    Why the existing tests did not ask: nothing anywhere exercises the failure
    branch of a catalog assertion. Every run of the suite has been a run in which
    the catalogs were already complete.

    Pushed here, and the assertion has teeth.
    """
    probe = "zz_uncatalogued_probe_tool"
    checker = catalog_tests.test_catalog_lists_every_registered_tool
    fallback_checker = catalog_tests.test_base_skill_tool_catalog_block_lists_every_tool

    _register_probe_tool(probe, category="session")
    try:
        for catalog_name in sorted(catalog_tests._CATALOGS):
            with pytest.raises(AssertionError) as failure:
                checker(catalog_name)
            assert probe in str(failure.value), f"{catalog_name}: the failure must name the missing tool"
        with pytest.raises(AssertionError) as fallback_failure:
            fallback_checker()
        assert probe in str(fallback_failure.value)
    finally:
        _remove_probe_tool(probe)

    checker("base skill static fallback")  # and the registry is clean again


def test_a_tool_registered_in_no_declared_group_fails_the_count_and_membership_assertions() -> None:
    """Proves the count assertions bite in all three of the ways a tool can be added wrong.

    A tool can arrive in an existing group without moving the declaration, in a
    group nobody declared, or with no ``category:`` tag at all. FR-025's
    assertions are supposed to catch each; this runs them against a tool
    registered each way and requires a failure every time.

    Why the existing tests did not ask: the same reason as above — the suite has
    only ever run against a correct registry, so the assertions' *sensitivity*
    has never been observed, only their agreement.

    Pushed here, and all three bite.
    """
    counts = catalog_tests.test_tool_group_counts_match_the_declared_breakdown
    membership = catalog_tests.test_group_membership_matches_the_declared_breakdown
    categorised = catalog_tests.test_every_registered_tool_declares_a_category

    probe = "zz_ungrouped_probe_tool"

    # (1) An extra tool in a declared group moves that group's count.
    _register_probe_tool(probe, category="session")
    try:
        with pytest.raises(AssertionError):
            counts()
        with pytest.raises(AssertionError):
            membership()
    finally:
        _remove_probe_tool(probe)

    # (2) A group nobody declared is a new key in the breakdown.
    _register_probe_tool(probe, category="telepathy")
    try:
        with pytest.raises(AssertionError):
            counts()
    finally:
        _remove_probe_tool(probe)

    # (3) No category at all: invisible to every per-group assertion but one.
    @mcp.tool(name=probe, tags={"read"})
    async def _untagged() -> str:
        """A tool with no category tag."""
        return "probe"

    try:
        with pytest.raises(AssertionError):
            categorised()
    finally:
        _remove_probe_tool(probe)

    counts()
    membership()
    categorised()


# ---------------------------------------------------------------------------
# Derived, not restated
# ---------------------------------------------------------------------------


def _assignments(module_path: Path) -> dict[str, ast.expr]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else node.targets if isinstance(node, ast.Assign) else []
        )
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = value
    return found


def test_the_expected_tool_counts_are_computed_rather_than_written_down() -> None:
    """Proves the totals in the declaration module cannot disagree with the names they count.

    ``mcp_tool_expectations.py`` says of ``EXPECTED_TOOL_COUNT``: "Derived, never
    written down: a total that can disagree with the names it counts is the
    defect this module exists to remove." That is a property of the *source*, not
    of a value, and it is the kind of property a well-meant edit reverses — a
    reviewer who sees ``len(...)`` failing on an import cycle types the number in
    and both the docstring and the guarantee are gone with no test to notice.

    Why the existing tests did not ask: nothing reads this module's source. Its
    module-level ``assert`` checks that the group counts sum to the total, which
    both a derived and a hand-typed total would satisfy.

    Pushed here, and both totals are computed.
    """
    assignments = _assignments(_EXPECTATIONS)

    total = assignments.get("EXPECTED_TOOL_COUNT")
    assert total is not None, "EXPECTED_TOOL_COUNT is no longer a module-level assignment"
    assert not isinstance(total, ast.Constant), (
        f"EXPECTED_TOOL_COUNT is written down as {ast.unparse(total)}; it must be derived from "
        f"EXPECTED_TOOL_NAMES so the two cannot disagree."
    )

    per_group = assignments.get("EXPECTED_GROUP_COUNTS")
    assert per_group is not None
    assert not isinstance(per_group, ast.Dict), (
        f"EXPECTED_GROUP_COUNTS is written down as a literal mapping; it must be derived from "
        f"EXPECTED_TOOL_GROUPS: {ast.unparse(per_group)[:120]}"
    )

    names = assignments.get("EXPECTED_TOOL_NAMES")
    assert names is not None and not isinstance(names, (ast.Set, ast.List)), (
        "EXPECTED_TOOL_NAMES must be the union of the per-group sets, not a second full listing"
    )


def test_no_count_assertion_site_writes_the_registry_total_down_a_second_time() -> None:
    """Proves the total lives in one place, which is what makes moving it a one-line change.

    ADR-054 §8.4 names five count-assertion sites and
    ``mcp_tool_expectations.py`` was written so that all five read one
    declaration. A sixth site that asserted ``len(tools) == 47`` directly would
    pass today, would be invisible to a reviewer reading the declaration module,
    and would fail on the next tool in a file that does not mention the tool —
    which is §8.4's own description of the cost this arrangement removes.

    The scan is deliberately narrow: only modules that both talk to the registry
    (``list_tools``) and assert a bare integer equal to the live total. A file
    that does neither cannot be restating the total.

    Why the existing tests did not ask: the declaration module is imported by
    the five sites, and nothing checks that it is imported by *every* site.

    Pushed here, and the total is written down once.
    """
    registered = _registered_count()
    offenders: dict[str, list[str]] = {}
    for path in sorted((_REPO_ROOT / "tests").rglob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        if "list_tools" not in text:
            continue
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
                continue
            operands = [node.test.left, *node.test.comparators]
            for operand in operands:
                if isinstance(operand, ast.Constant) and operand.value == registered:
                    offenders.setdefault(path.relative_to(_REPO_ROOT).as_posix(), []).append(ast.unparse(node.test))

    assert offenders == {}, (
        f"these modules assert the registry total as a literal instead of importing "
        f"EXPECTED_TOOL_COUNT from tests/mcp_tool_expectations.py: {offenders}"
    )
