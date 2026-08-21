"""Conformance checks for core tutorial 5 — "SciStudio at a Glance" (#2084).

The summary level is the one core tutorial that is reading-only by design
(ADR-053 §2.2 as revised by FR-092): one step per card, eight cards, each step
satisfied by its pages having been served. These checks pin the properties the
level's reading surface and the dispatch contract rely on, beyond what the
directory-scanning checks in ``test_core_tutorials.py`` already enforce for
every core tutorial.

Dependency: the ``pages:`` step field is added by the #2061 vocabulary batch
(agent P1 of the Learning Center levels rollout). Until that lands in the
umbrella branch, ``load_manifest`` rejects the manifest and this module fails —
which is the intended signal that the branch has not yet been integrated, not
a fault in the tutorial.

What each check protects:

* Reading-only status is what routes the tutorial to the Reading tab and to
  the reading window instead of the floating step card. A stray judged
  condition would silently move it back to the hands-on surface.
* A page named by a step but missing on disk fails the *reader*, mid-card,
  with nothing to press. Serving is satisfying (the pages route records
  ``page_reached``), so a missing file is also a step that can never complete.
* ``done_when`` and ``pages`` are two spellings of the same list. If they
  drift, either a page can be skipped and the card still completes, or the
  card waits on a page the reader is never shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

TUTORIAL_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core" / "scistudio-at-a-glance"
)
PAGES_DIR = TUTORIAL_DIR / "assets" / "pages"

#: The eight cards, in the step order the owner fixed (scenarios doc 关卡 5).
EXPECTED_CARD_TITLES = (
    "Workflow",
    "Block",
    "Data type",
    "Previewer",
    "Plot card",
    "History",
    "My library",
    "Others",
)


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


@pytest.fixture(scope="module")
def raw_steps() -> list[dict[str, Any]]:
    with (TUTORIAL_DIR / "tutorial.yaml").open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    steps = raw.get("steps")
    assert isinstance(steps, list) and steps, "the manifest declares no steps"
    return steps


def test_manifest_validates(manifest: TutorialManifest) -> None:
    assert manifest.id == "scistudio-at-a-glance"
    assert manifest.order == 5


def test_is_reading_only(manifest: TutorialManifest) -> None:
    """The property that files the tutorial under Reading and licenses FR-092."""
    assert manifest.is_reading_only, (
        "the summary level must be reading-only: every step waits on continue or page_reached and nothing else"
    )


def test_no_bootstrap(manifest: TutorialManifest) -> None:
    """A reading tutorial creates no project (dispatch contract for #2084)."""
    assert manifest.bootstrap is None


def test_eight_cards_in_owner_order(manifest: TutorialManifest) -> None:
    titles = tuple(step.title for step in manifest.steps)
    assert titles == EXPECTED_CARD_TITLES


def test_every_step_has_a_one_line_summary(manifest: TutorialManifest) -> None:
    for step in manifest.steps:
        assert step.say and step.say.strip(), f"step {step.id!r} has no card summary"
        assert "\n" not in step.say.strip(), f"step {step.id!r}'s summary is not one line"


def test_every_declared_page_file_exists(raw_steps: list[dict[str, Any]]) -> None:
    for step in raw_steps:
        pages = step.get("pages")
        assert isinstance(pages, list) and pages, f"step {step.get('id')!r} declares no pages"
        for name in pages:
            page_file = PAGES_DIR / f"{name}.md"
            assert page_file.is_file(), f"step {step.get('id')!r} names missing page {name!r}"


def test_page_names_are_unique_across_the_tutorial(raw_steps: list[dict[str, Any]]) -> None:
    """``page_reached`` records a bare name; a repeat would satisfy two cards."""
    seen: list[str] = []
    for step in raw_steps:
        seen.extend(step.get("pages") or [])
    assert len(seen) == len(set(seen)), f"duplicate page names: {sorted(set(n for n in seen if seen.count(n) > 1))}"


def test_done_when_is_exactly_the_pages(raw_steps: list[dict[str, Any]]) -> None:
    """The two spellings of a card's reading list must agree, page for page."""
    for step in raw_steps:
        pages = step.get("pages") or []
        done_when = step.get("done_when") or {}
        terms = done_when.get("all")
        assert isinstance(terms, list), f"step {step.get('id')!r} must wait on all of its pages"
        reached = []
        for term in terms:
            assert set(term) == {"page_reached"}, f"step {step.get('id')!r} judges a non-reading term: {term}"
            reached.append(term["page_reached"]["page"])
        assert reached == pages, f"step {step.get('id')!r}: done_when pages {reached} != declared pages {pages}"


def test_no_orphan_page_files(raw_steps: list[dict[str, Any]]) -> None:
    """A page on disk that no step names is unreachable copy — dead weight."""
    declared = {name for step in raw_steps for name in (step.get("pages") or [])}
    on_disk = {path.stem for path in PAGES_DIR.glob("*.md")}
    assert on_disk == declared, (
        f"orphan pages: {sorted(on_disk - declared)}; missing pages: {sorted(declared - on_disk)}"
    )


def test_step_view_exposes_pages(manifest: TutorialManifest) -> None:
    """The parsed step carries ``pages`` in reading order (#2061 batch, item 9).

    The reading surface draws its pager from the step view, so the parsed
    attribute and the raw YAML must be the same list — not merely sets.
    """
    with (TUTORIAL_DIR / "tutorial.yaml").open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    raw_pages = {step["id"]: step.get("pages") or [] for step in raw["steps"]}
    for step in manifest.steps:
        assert list(getattr(step, "pages", ())) == raw_pages[step.id]
