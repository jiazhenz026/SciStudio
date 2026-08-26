"""Conformance checks for every tutorial SciStudio itself ships.

ADR-053 Learning Center spec §4.3. The tutorials under
``src/scistudio/tutorials/core/`` are product surface: a reader meets them
before they meet anything else, and a fault in one of them is not a failing
test somewhere, it is a reader stuck on step four with nothing to press.

Nothing here names a tutorial. The directory is scanned, so a second core
tutorial is held to the same bar the day it lands rather than the day someone
remembers to extend a list. The one thing asserted about the set as a whole is
that it is not empty — otherwise a scan that silently found nothing would make
every check below pass by vacuum.

What each check is really protecting:

* Schema validation catches the faults the format can see.
* The closed-set checks catch a ``route_to``, ``highlight`` or ``ui_event``
  name the backend or frontend cannot resolve. Those fail *silently* at run
  time — guidance that never appears, or a step that never completes and never
  says why — which is the reason FR-049 closes them at validation.
* The asset check catches a manifest naming a file that is not there. That
  breaks at the step the action sits on, which may be many minutes in.
* The source checks catch shipped teaching material that does not parse or does
  not import. Every ``assets/code`` file here is read by the reader and
  executed by the product, so "it looked right" is not enough.
"""

from __future__ import annotations

import ast
import itertools
import re
from pathlib import Path

import pytest

from scistudio.tutorials.actions import (
    CopyAction,
    FileAction,
    ReplayAction,
    RunAction,
    WriteAction,
    iter_file_actions,
)
from scistudio.tutorials.conditions import UI_EVENT_NAMES, VOCABULARY, Condition
from scistudio.tutorials.discovery import (
    DiscoveryEnvironment,
    _unmet_version,
    discover_tutorials,
    unmet_requirement,
)
from scistudio.tutorials.manifest import (
    HIGHLIGHT_TARGETS,
    ROUTE_TARGETS,
    TUTORIAL_MANIFEST_FILENAME,
    TutorialManifest,
    TutorialSourceKind,
    load_manifest,
)

CORE_TUTORIALS_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core"


def _core_tutorial_dirs() -> list[Path]:
    """Every directory under ``core/`` holding a manifest, found by scanning."""
    if not CORE_TUTORIALS_DIR.is_dir():
        return []
    return sorted(
        entry
        for entry in CORE_TUTORIALS_DIR.iterdir()
        if entry.is_dir() and (entry / TUTORIAL_MANIFEST_FILENAME).is_file()
    )


CORE_TUTORIAL_DIRS = _core_tutorial_dirs()
CORE_TUTORIAL_IDS = [directory.name for directory in CORE_TUTORIAL_DIRS]


def _load(directory: Path) -> TutorialManifest:
    return load_manifest(directory, source_kind=TutorialSourceKind.CORE)


def _actions(manifest: TutorialManifest) -> list[WriteAction | CopyAction | ReplayAction]:
    """Every action the manifest declares: bootstrap, step entry, and triggers.

    Trigger ``do`` lists (#2061) are included for the same reason the manifest
    validator walks them: pressing the button reaches the project as surely as
    entering the step does, and tutorial 4 declares nearly everything it writes
    inside triggers. A declaration site missing here is a hole in every check
    below.
    """
    found: list[WriteAction | CopyAction | ReplayAction] = []
    if manifest.bootstrap is not None:
        found.extend(manifest.bootstrap.do)
    for step in manifest.steps:
        found.extend(step.do)
        if step.trigger is not None:
            found.extend(step.trigger.do)
    return found


def _file_actions(manifest: TutorialManifest) -> list[FileAction]:
    """Every write and copy the manifest can perform, replay-bound ones included.

    A replay segment's ``do`` (FR-061b) is where tutorial 4 lands almost all of
    its files, so a check that filters ``_actions`` down to bare ``WriteAction``
    instances never sees them. ``iter_file_actions`` is the runtime's own
    flattening, reused so this file cannot disagree with it.
    """
    return list(iter_file_actions(_actions(manifest)))


#: A CSI escape sequence — every colour change the transcripts use.
#: A complete bold run -- the one piece of markup a beat may carry.
#: Highlight targets that live in the LEFT panel, and the `route_to` that
#: opens the tab each one is on. The right panel and the bottom panel are
#: not in here: a step routing to a bottom tab leaves the left panel alone
#: and vice versa, so only these can be pointed at through a closed tab.
_LEFT_PANEL_ROUTE_FOR: dict[str, str] = {
    "block_palette": "block_palette",
    "palette_block": "block_palette",
    "type_palette": "data_types",
    "previewer_palette": "previewers",
    "data": "data",
}

#: A `[text](doc:page)` run in a beat -- the one thing besides bold that a
#: beat may carry, and the only place a tutorial can name a page of the user
#: guide (#2083).
_DOC_LINK = re.compile(r"\]\(doc:([^)\s]+)\)")

#: Where those pages ship from.
USER_GUIDE_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "_user_guide"

_BOLD_PAIR = re.compile(r"\*\*[^*]+\*\*")

_ANSI_CSI = re.compile("\x1b\\[[0-9;]*[@-~]")


def _visible_lines(text: str) -> list[str]:
    """The transcript with its colour codes and CRLF removed, split into lines.

    What a reader sees, which is also what the frontend's pacer classifies: the
    escape sequences in front of a line are not characters and do not decide
    where the line starts.
    """
    return _ANSI_CSI.sub("", text).replace("\r", "").split("\n")


def _replay_segment_sources(manifest: TutorialManifest) -> list[str]:
    """Every transcript a replay plays, excluding the files its segments write."""
    sources: list[str] = []
    for action in _actions(manifest):
        if isinstance(action, ReplayAction):
            sources.extend(segment.source for segment in action.segments)
    return sources


def _core_palette_type_names() -> set[str]:
    """The block type names a reader actually finds in their palette.

    Deliberately ``_scan_builtins`` rather than :meth:`BlockRegistry.scan`.
    ``scan`` also walks the ``scistudio.blocks`` entry-point group, which is
    reserved for third-party plugins (#1779) but is served by whatever
    ``*.dist-info`` happens to sit in the developer's environment. A stale
    editable install of core therefore re-registers blocks that
    ``_scan_builtins`` excludes on purpose, and a test built on ``scan`` would
    pass or fail on one machine's leftovers instead of on this repository.
    """
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.blocks.registry._scan import _scan_builtins

    registry = BlockRegistry()
    _scan_builtins(registry)
    return {registry.get_spec(name).type_name for name in registry.all_specs()}


def _asset_sources(manifest: TutorialManifest) -> list[str]:
    """Every tutorial-directory-relative path any action reads, replays included.

    A ``run`` action reads no asset — it names a path inside the reader's
    project, not one in the tutorial directory — so it contributes nothing here
    and must not be asked for a ``source`` it does not have.
    """
    sources: list[str] = []
    for action in _actions(manifest):
        if isinstance(action, RunAction):
            continue
        if isinstance(action, ReplayAction):
            for segment in action.segments:
                sources.append(segment.source)
                sources.extend(bound.source for bound in segment.do if not isinstance(bound, RunAction))
        else:
            sources.append(action.source)
    return sources


# ---------------------------------------------------------------------------
# The set itself
# ---------------------------------------------------------------------------


def test_at_least_one_core_tutorial_ships() -> None:
    """Guards every parametrised check below against passing by finding nothing."""
    assert CORE_TUTORIAL_DIRS, f"no core tutorial found under {CORE_TUTORIALS_DIR}"


def test_core_tutorial_ids_are_unique_and_ordered() -> None:
    manifests = [_load(directory) for directory in CORE_TUTORIAL_DIRS]
    ids = [manifest.id for manifest in manifests]
    assert len(set(ids)) == len(ids), f"duplicate tutorial id among the core tutorials: {ids}"
    # Order places tutorials within their group. Two tutorials claiming the same
    # slot leaves the reader's first lesson decided by directory iteration.
    orders = [manifest.order for manifest in manifests if manifest.order is not None]
    assert len(set(orders)) == len(orders), f"two core tutorials claim the same order: {orders}"


def test_a_tutorial_that_builds_the_reader_a_project_is_not_filed_as_reading() -> None:
    """Two independently declared things that must agree.

    The Learning Center lifts reading tutorials into a tab of their own, and
    decides which those are from the steps' conditions
    (:attr:`TutorialManifest.is_reading_only`). ``bootstrap`` is declared
    separately and decides whether the tutorial gets a project (FR-009).
    Nothing in the code makes one follow from the other, which is what gives
    this check something to catch: a tutorial that creates a working project
    and then never checks whether anything was done in it is listed as
    something to sit and read, and is not one.
    """
    for directory in CORE_TUTORIAL_DIRS:
        manifest = _load(directory)
        if not manifest.creates_project:
            continue
        assert not manifest.is_reading_only, (
            f"{manifest.id} creates a tutorial project but judges nothing the reader does, "
            "so the Learning Center would file it under Reading"
        )


# ---------------------------------------------------------------------------
# Per-tutorial conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("directory", CORE_TUTORIAL_DIRS, ids=CORE_TUTORIAL_IDS)
class TestEveryShippedCoreTutorial:
    def test_loads_and_validates_against_the_published_schema(self, directory: Path) -> None:
        """``load_manifest`` applies the published schema, the vocabulary, and the tier rules."""
        manifest = _load(directory)
        assert manifest.id
        assert manifest.title
        assert manifest.summary
        # FR-010: exactly one of steps or driver. A core tutorial with neither
        # lists fine and then has nothing to show.
        assert bool(manifest.steps) != bool(manifest.driver)

    def test_step_ids_are_unique_and_non_empty(self, directory: Path) -> None:
        manifest = _load(directory)
        step_ids = [step.id for step in manifest.steps]
        assert all(step_ids), "a step declares an empty id"
        assert len(set(step_ids)) == len(step_ids), f"duplicate step id in {manifest.id}: {step_ids}"

    def test_every_step_can_be_advanced(self, directory: Path) -> None:
        """A step either judges completion or is a reading step the reader continues.

        Both are legal (FR-012). What would not be is a step that says nothing
        and judges nothing, which gives the reader neither instruction nor a
        way forward.
        """
        for step in _load(directory).steps:
            assert step.say or step.done_when, f"step {step.id!r} has neither say nor done_when"

    def test_every_condition_term_is_in_the_vocabulary(self, directory: Path) -> None:
        for step in _load(directory).steps:
            if step.done_when is None:
                continue
            unknown = step.done_when.terms() - VOCABULARY
            assert not unknown, f"step {step.id!r} uses terms outside the vocabulary: {sorted(unknown)}"

    def test_every_ui_event_name_is_in_the_closed_set(self, directory: Path) -> None:
        """A name the backend never reports is a step that never advances."""

        def walk(condition: Condition, step_id: str) -> None:
            if condition.is_combinator:
                for operand in condition.operands:
                    walk(operand, step_id)
                return
            if condition.term == "ui_event":
                name = condition.args["name"]
                assert name in UI_EVENT_NAMES, f"step {step_id!r} waits on unknown ui_event {name!r}"

        for step in _load(directory).steps:
            if step.done_when is not None:
                walk(step.done_when, step.id)

    def test_every_route_and_highlight_is_in_its_closed_set(self, directory: Path) -> None:
        """A name outside the set resolves to nothing and the guidance disappears."""
        for step in _load(directory).steps:
            if step.route_to is not None:
                assert step.route_to in ROUTE_TARGETS, f"step {step.id!r} routes to unknown {step.route_to!r}"
            for highlight in step.highlights:
                if highlight is None:
                    continue
                target = highlight.target
                assert target in HIGHLIGHT_TARGETS, f"step {step.id!r} highlights unknown {target!r}"

    def test_every_referenced_asset_exists_on_disk(self, directory: Path) -> None:
        """A manifest naming a missing asset is a tutorial that breaks at that step."""
        manifest = _load(directory)
        for relative in _asset_sources(manifest):
            resolved = manifest.resolve_asset(relative)
            assert resolved.exists(), f"{manifest.id}: action source {relative!r} does not exist at {resolved}"

    def test_every_replay_segment_marks_its_question_with_one_prompt_line(self, directory: Path) -> None:
        """The `>` line is a contract the frontend paces on, not a styling choice.

        The scripted terminal types the reader's question at a human's pace and
        the agent's reply at a machine's (#2083,
        ``frontend/src/components/AIChat/scriptedPacing.ts``). What tells the
        two voices apart is the shell convention the transcripts already
        follow: the question is the line whose first *visible* character — the
        colour codes in front of it do not count — is `>`.

        Two ways that breaks silently, and both are caught here. A segment with
        no `>` line plays the reader's own question at machine speed, so the
        exchange loses the half that makes it an exchange. A reply line that
        happens to open with `>` (a quote, a diff, a shell example) types
        itself out at 45ms a character, which on a long line is a terminal that
        looks hung.
        """
        manifest = _load(directory)
        for relative in _replay_segment_sources(manifest):
            text = manifest.resolve_asset(relative).read_text(encoding="utf-8")
            prompts = [line for line in _visible_lines(text) if line.startswith(">")]
            assert len(prompts) == 1, (
                f"{manifest.id}: replay segment {relative!r} has {len(prompts)} lines opening with '>', "
                f"expected exactly one (the reader's question): {prompts}"
            )

    def test_a_transcript_that_enumerates_the_palette_enumerates_the_real_one(self, directory: Path) -> None:
        """A scripted reply that lists the palette must list the palette they have.

        Tutorial 3 has the agent answer "what blocks do you have to work with?"
        by printing the registry, and the reader is invited to check that answer
        against their own left panel. So the list is a claim about the product,
        not set dressing: name a block that is not there and the tutorial has
        taught a beginner something false at the exact moment it asked them to
        trust it.

        The drift this catches is one-directional and quiet. ``Merge`` and
        ``Split`` are still importable classes — excluded from the palette in
        ``_scan_builtins`` because ``Data Router`` supersedes them, kept for
        plugin development and tests — so a transcript can name them, a
        developer can import them, and nothing complains. Only the reader,
        looking at a panel that does not contain them, finds out.
        """
        manifest = _load(directory)
        palette = _core_palette_type_names()
        for relative in _replay_segment_sources(manifest):
            lines = _visible_lines(manifest.resolve_asset(relative).read_text(encoding="utf-8"))
            for index, line in enumerate(lines):
                if "list_blocks()" not in line:
                    continue
                listed = [
                    entry.split()[0] for entry in itertools.takewhile(lambda text: text.strip(), lines[index + 1 :])
                ]
                assert set(listed) == palette, (
                    f"{manifest.id}: replay segment {relative!r} enumerates the palette as {sorted(listed)}, "
                    f"but the palette a reader gets is {sorted(palette)}"
                )

    def test_no_beat_leaks_an_asterisk_the_dialogue_cannot_render(self, directory: Path) -> None:
        """`**bold**` is the only markup a beat has; anything else reaches the screen.

        `frontend/src/components/LearningCenter.parts/beatText.ts` splits a beat
        on a `**` pair and treats every other character as text, so a lone `*it*`
        -- the habit of anyone who writes markdown all day -- renders as literal
        asterisks in the dialogue box. There is no parse error and no warning: it
        simply looks like the tutorial was written by someone who did not check.
        """
        manifest = _load(directory)
        for step in manifest.steps:
            for index, beat in enumerate(step.say):
                leftover = _BOLD_PAIR.sub("", beat)
                assert "*" not in leftover, (
                    f"{manifest.id}: step {step.id!r} beat {index} carries an asterisk outside a "
                    f"bold pair, which the dialogue renders as itself: {beat!r}"
                )

    def test_a_left_panel_highlight_is_on_a_step_that_opens_that_panel(self, directory: Path) -> None:
        """A ring around a tab nobody is looking at is a ring around nothing.

        `route_to` is a property of the step, not of the beat, and the left
        panel and the bottom panel are separate axes: routing to `ai_chat`
        moves the bottom panel and leaves the left one wherever the previous
        step put it. So a step that rings a palette entry while routing to a
        bottom tab draws its highlight on a tab that may not be open —
        silently, because the highlight simply finds no element.

        Caught by a reader, not by a test, the first time: the QC block's
        "there it is in the palette" beat rang the palette while the left
        panel was still showing Data.
        """
        manifest = _load(directory)
        for step in manifest.steps:
            for highlight in step.highlights:
                if highlight is None:
                    continue
                needed = _LEFT_PANEL_ROUTE_FOR.get(highlight.target)
                if needed is None:
                    continue
                assert step.route_to == needed, (
                    f"{manifest.id}: step {step.id!r} highlights {highlight.target!r}, which is in the "
                    f"left panel, but routes to {step.route_to!r} — it must route to {needed!r} or the "
                    f"ring lands on a tab that may not be open"
                )

    def test_every_doc_link_names_a_page_that_ships(self, directory: Path) -> None:
        """A link to a page that is not there is a 404 with a beat pointing at it.

        The path is what the docs API is asked for verbatim, extension and
        all — `ai-assistant` is not the page, `ai-assistant.md` is — and
        nothing between the beat and the request would notice the
        difference. The reader gets "No such documentation page", having
        been told the guide was right there.

        Both a step's beats and the tutorial's summary are checked: the
        summary carries the same markup, so the catalogue page can point at
        a page that does not exist just as easily.
        """
        manifest = _load(directory)
        beats = [manifest.summary, *(beat for step in manifest.steps for beat in step.say)]
        for beat in beats:
            for page in _DOC_LINK.findall(beat):
                assert (USER_GUIDE_DIR / page).is_file(), (
                    f"{manifest.id}: a beat links to user-guide page {page!r}, which does not ship "
                    f"under {USER_GUIDE_DIR}"
                )

    def test_copy_sources_are_directories_and_write_sources_are_files(self, directory: Path) -> None:
        """The two actions are not interchangeable; the mismatch only shows at run time."""
        manifest = _load(directory)
        for action in _file_actions(manifest):
            if isinstance(action, WriteAction):
                assert manifest.resolve_asset(action.source).is_file(), (
                    f"{manifest.id}: write source {action.source!r} is not a file"
                )
            elif isinstance(action, CopyAction):
                assert manifest.resolve_asset(action.source).is_dir(), (
                    f"{manifest.id}: copy source {action.source!r} is not a directory"
                )

    def test_every_shipped_python_asset_parses(self, directory: Path) -> None:
        """``assets/code/*.py`` is read by the reader and executed by the product."""
        code_dir = directory / "assets" / "code"
        if not code_dir.is_dir():
            pytest.skip("this tutorial ships no code assets")
        sources = sorted(code_dir.rglob("*.py"))
        assert sources, f"{directory.name} has an assets/code directory with no Python in it"
        for source in sources:
            try:
                ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            except SyntaxError as exc:  # pragma: no cover - the assertion is the report
                pytest.fail(f"{source} does not parse: {exc}")

    def test_every_shipped_python_asset_compiles(self, directory: Path) -> None:
        """Compilation is the same gate the interpreter applies when the product imports it.

        The builtin ``compile`` is used rather than ``compileall`` so nothing is
        written: ``compileall`` would drop ``__pycache__`` into the shipped
        asset tree, which is source that goes out in the wheel.
        """
        code_dir = directory / "assets" / "code"
        if not code_dir.is_dir():
            pytest.skip("this tutorial ships no code assets")
        for source in sorted(code_dir.rglob("*.py")):
            try:
                compile(source.read_text(encoding="utf-8"), str(source), "exec")
            except SyntaxError as exc:  # pragma: no cover - the failure is the report
                pytest.fail(f"{source} does not compile: {exc}")

    def test_python_assets_written_into_blocks_declare_a_block(self, directory: Path) -> None:
        """A file landing in ``blocks/`` only registers a block if it declares a class.

        The registry scans ``blocks/`` and picks up block subclasses. A write
        action aiming a module with no class at that directory registers
        nothing, and the step waiting on ``block_registered`` never completes.
        """
        manifest = _load(directory)
        for action in _file_actions(manifest):
            if not isinstance(action, WriteAction):
                continue
            if not action.destination.startswith("blocks/"):
                continue
            tree = ast.parse(manifest.resolve_asset(action.source).read_text(encoding="utf-8"))
            classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
            assert classes, f"{manifest.id}: {action.source!r} lands in blocks/ but declares no class"
            assigned = {
                target.id
                for cls in classes
                for node in cls.body
                if isinstance(node, ast.AnnAssign | ast.Assign)
                for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
                if isinstance(target, ast.Name)
            }
            assert "type_name" in assigned, (
                f"{manifest.id}: {action.source!r} declares no type_name, so nothing can refer to it"
            )

    def test_plot_scripts_declare_the_render_entrypoint(self, directory: Path) -> None:
        """A plot script is called through ``render(collection)`` and nothing else.

        ``scistudio.plot.validation`` rejects any other shape, so a shipped
        script with a differently named function fails when the reader renders
        it rather than when it is written.
        """
        manifest = _load(directory)
        for action in _file_actions(manifest):
            if not isinstance(action, WriteAction):
                continue
            if not action.destination.startswith("plots/"):
                continue
            if not action.destination.endswith(".py"):
                # A plot is a manifest plus a script; only the script is Python.
                continue
            tree = ast.parse(manifest.resolve_asset(action.source).read_text(encoding="utf-8"))
            renders = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render"]
            assert renders, f"{manifest.id}: {action.source!r} lands in plots/ with no render function"
            args = [arg.arg for arg in renders[0].args.args]
            assert args == ["collection"], (
                f"{manifest.id}: {action.source!r} declares render{tuple(args)}, expected render(collection)"
            )

    def test_block_types_the_conditions_wait_on_are_the_ones_the_assets_declare(self, directory: Path) -> None:
        """A ``block_registered`` step must name a ``type_name`` the tutorial actually ships.

        These two facts sit in different files — the condition in the manifest,
        the identifier in the block source — and a typo in either leaves a step
        that can never complete.

        The rule is deliberately "a type this tutorial ships" rather than "a
        type the registry has". Asking the live registry would mean scanning
        it, which picks up whatever packages happen to be installed on the
        machine running the tests and makes the result depend on that. A core
        tutorial waiting on a block it does not ship would have to widen this
        check and say why.

        The limit of the check: a tutorial that deliberately ships two variants
        of the same block — as tutorial 1 does, one of them renamed so the
        reader has something to recover — makes both identifiers legitimately
        "shipped", so swapping the condition from one to the other passes here.
        What it does catch is the fault that actually happens: a name in the
        manifest that no asset declares at all.
        """
        manifest = _load(directory)
        shipped: set[str] = set()
        for action in _file_actions(manifest):
            if not isinstance(action, WriteAction) or not action.destination.startswith("blocks/"):
                continue
            tree = ast.parse(manifest.resolve_asset(action.source).read_text(encoding="utf-8"))
            for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
                for node in cls.body:
                    if not isinstance(node, ast.AnnAssign):
                        continue
                    if not isinstance(node.target, ast.Name) or node.target.id != "type_name":
                        continue
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        shipped.add(node.value.value)
        if not shipped:
            pytest.skip("this tutorial ships no project blocks")

        def walk(condition: Condition, step_id: str) -> None:
            if condition.is_combinator:
                for operand in condition.operands:
                    walk(operand, step_id)
                return
            if condition.term != "block_registered":
                return
            block_type = condition.args["block_type"]
            assert block_type in shipped, (
                f"step {step_id!r} waits on block_registered {block_type!r}, which this tutorial does "
                f"not ship (it ships {sorted(shipped)})"
            )

        for step in manifest.steps:
            if step.done_when is not None:
                walk(step.done_when, step.id)

    def test_a_block_that_needs_configuring_is_checked_for_it(self, directory: Path) -> None:
        """A step that has the reader place an IO block must judge its configuration.

        The failure this catches, found by the owner running tutorial 1: the
        step said "drag a Save block, connect it, and set its path", and its
        ``done_when`` checked only ``node_exists`` and ``edge_exists``. Dragging
        and connecting lit Continue, the reader moved on with an unconfigured
        Save block, and the workflow they were then told to Run could not run.
        Nothing in the tutorial was in a position to notice.

        The rule is narrow on purpose. It applies to the IO blocks below, whose
        whole job is a path the reader supplies, and it asks only that *some*
        step judges that path — not which step, and not which value. A process
        block that runs on defaults is not covered, because requiring a
        configuration check for a block that needs no configuration would be
        ceremony.
        """
        needs_a_path = {"load_data", "save_data"}
        manifest = _load(directory)

        placed: set[str] = set()
        configured: set[str] = set()

        def walk(condition: Condition, _step_id: str) -> None:
            if condition.is_combinator:
                for operand in condition.operands:
                    walk(operand, _step_id)
                return
            block_type = condition.args.get("block_type")
            if not isinstance(block_type, str):
                return
            if condition.term == "node_exists":
                placed.add(block_type)
            elif condition.term in ("config_equals", "config_matches"):
                configured.add(block_type)

        for step in manifest.steps:
            if step.done_when is not None:
                walk(step.done_when, step.id)

        unchecked = sorted((placed & needs_a_path) - configured)
        assert not unchecked, (
            f"{manifest.id}: has the reader place {', '.join(unchecked)} but never judges "
            f"the configuration, so they can continue with a block that cannot run"
        )


def test_every_shipped_tutorial_is_startable_in_this_tree() -> None:
    """A shipped tutorial must be startable by the SciStudio that ships it.

    The check the other tests in this file cannot make. They validate manifests
    in isolation; this one runs the real discovery pass over the real tree and
    asks the question a reader asks by opening the Learning Center: can I press
    start?

    It exists because the first time it was run the answer was no. SciStudio
    versions itself with pre-release segments as a matter of course — this tree
    is an ``a0`` — and ``packaging`` excludes pre-releases from specifier
    matching unless asked not to, so ``requires.scistudio: ">=0.3.1"`` did not
    match ``0.3.3a0`` and the only tutorial the product ships reported itself as
    needing a newer SciStudio than the one it came in. Nothing in a manifest, a
    schema, or a discovery unit test can see that: it needs the shipped
    manifest and the running version in the same assertion.

    The environment states every core tutorial as completed (#2088). What this
    test is about is whether the *installation* can run what it ships — a
    version specifier that excludes its own tree, a package that is not there,
    an agent that is not configured. A prerequisite tutorial is a different
    kind of unavailability: it is the catalogue working as designed, it names
    the tutorial the reader should do first, and it clears itself the moment
    they do. Judging a track of levels against an empty progress store would
    make "level 3 asks you to finish level 2" indistinguishable from "level 3
    cannot run here", and only the second is a defect.
    """

    result = discover_tutorials()
    assert result.tutorials, "discovery found no core tutorials"
    shipped = frozenset(tutorial.key for tutorial in result.tutorials)
    environment = DiscoveryEnvironment(completed_tutorials=shipped)
    for tutorial in result.tutorials:
        assert tutorial.manifest is not None, f"core tutorial {tutorial.key.tutorial_id!r} listed without a manifest"
        reason = unmet_requirement(tutorial.manifest, environment)
        assert reason is None, (
            f"core tutorial {tutorial.key.tutorial_id!r} ships in a SciStudio it says it cannot run in: {reason}"
        )


def test_a_prerequisite_is_the_only_thing_that_may_hold_a_core_tutorial_back() -> None:
    """On a clean install, every core tutorial is startable or names a sibling.

    The complement of the test above. That one fixes progress so environment
    faults are the only thing left; this one fixes the environment so progress
    is. A core tutorial that is unavailable to a first-time reader must be
    unavailable for exactly one reason — a prerequisite level the catalogue
    also ships and lists — because that is the one reason the reader can act
    on from inside the product.
    """

    result = discover_tutorials()
    shipped = {tutorial.key.tutorial_id for tutorial in result.tutorials}
    for tutorial in result.tutorials:
        assert tutorial.manifest is not None
        if tutorial.is_startable:
            continue
        required = tuple(tutorial.manifest.requires.tutorials)
        assert required, (
            f"core tutorial {tutorial.key.tutorial_id!r} is not startable on a clean install and does not "
            f"declare a prerequisite: {unmet_requirement(tutorial.manifest, DiscoveryEnvironment())}"
        )
        missing = [needed for needed in required if needed not in shipped]
        assert not missing, (
            f"core tutorial {tutorial.key.tutorial_id!r} requires {missing}, which this tree does not ship — "
            "the reader would have no way to clear it"
        )
        assert tutorial.key.tutorial_id not in required, (
            f"core tutorial {tutorial.key.tutorial_id!r} requires itself, so nothing a reader does can ever clear it"
        )

    # Reachability, which the per-tutorial checks above cannot see: a cycle
    # gates every level in it forever while each one individually looks
    # well-formed. Walk the declared order and assert the catalogue can be
    # completed from a clean install by doing the levels one at a time.
    remaining = {
        tutorial.key.tutorial_id: set(tutorial.manifest.requires.tutorials)
        for tutorial in result.tutorials
        if tutorial.manifest is not None
    }
    completed: set[str] = set()
    while remaining:
        clearable = [tid for tid, needs in remaining.items() if needs <= completed]
        assert clearable, (
            f"no core tutorial is startable once {sorted(completed)} are done — the remaining "
            f"{ {tid: sorted(needs) for tid, needs in remaining.items()} } wait on each other"
        )
        for tid in clearable:
            completed.add(tid)
            del remaining[tid]


@pytest.mark.parametrize(
    ("specifier", "version"),
    [(">=0.3.1", "0.3.3a0"), (">=0.3.0", "0.4.0rc1"), (">=1.0", "1.1.0b2")],
)
def test_a_prerelease_core_satisfies_a_plain_lower_bound(specifier: str, version: str) -> None:
    """A pre-release build is new enough for a requirement it is numerically past.

    PEP 440's default is right for dependency resolution, where quietly pulling
    an alpha into an environment is the hazard. The question here is the
    opposite one — whether the SciStudio already running is new enough — and
    answering it "no" for every pre-release build would make ``requires``
    unusable rather than merely strict.
    """

    assert _unmet_version(specifier, version) is None


def test_a_prerelease_of_the_required_version_itself_is_still_too_old() -> None:
    """The bound above is a widening, not a removal of the ordering.

    ``1.0.0b2`` precedes ``1.0.0``, so a tutorial requiring ``>=1.0`` is right
    to refuse it. Pinned separately because the obvious over-correction — treat
    any pre-release as satisfying anything — would pass the test above and be
    wrong here.
    """

    assert _unmet_version(">=1.0", "1.0.0b2") is not None
