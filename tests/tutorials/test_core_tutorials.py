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
from pathlib import Path

import pytest

from scistudio.tutorials.actions import CopyAction, ReplayAction, WriteAction
from scistudio.tutorials.conditions import UI_EVENT_NAMES, VOCABULARY
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
    """Every action the manifest declares, from bootstrap and from every step."""
    found: list[WriteAction | CopyAction | ReplayAction] = []
    if manifest.bootstrap is not None:
        found.extend(manifest.bootstrap.do)
    for step in manifest.steps:
        found.extend(step.do)
    return found


def _asset_sources(manifest: TutorialManifest) -> list[str]:
    """Every tutorial-directory-relative path any action reads, replays included."""
    sources: list[str] = []
    for action in _actions(manifest):
        if isinstance(action, ReplayAction):
            for segment in action.segments:
                sources.append(segment.source)
                sources.extend(bound.source for bound in segment.do)
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

        def walk(condition, step_id: str) -> None:
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
            if step.highlight is not None:
                assert step.highlight in HIGHLIGHT_TARGETS, f"step {step.id!r} highlights unknown {step.highlight!r}"

    def test_every_referenced_asset_exists_on_disk(self, directory: Path) -> None:
        """A manifest naming a missing asset is a tutorial that breaks at that step."""
        manifest = _load(directory)
        for relative in _asset_sources(manifest):
            resolved = manifest.resolve_asset(relative)
            assert resolved.exists(), f"{manifest.id}: action source {relative!r} does not exist at {resolved}"

    def test_copy_sources_are_directories_and_write_sources_are_files(self, directory: Path) -> None:
        """The two actions are not interchangeable; the mismatch only shows at run time."""
        manifest = _load(directory)
        for action in _actions(manifest):
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
        for action in _actions(manifest):
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
        for action in _actions(manifest):
            if not isinstance(action, WriteAction):
                continue
            if not action.destination.startswith("plots/"):
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
        for action in _actions(manifest):
            if not isinstance(action, WriteAction) or not action.destination.startswith("blocks/"):
                continue
            tree = ast.parse(manifest.resolve_asset(action.source).read_text(encoding="utf-8"))
            for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
                for node in cls.body:
                    target = node.target if isinstance(node, ast.AnnAssign) else None
                    if target is None or not isinstance(target, ast.Name) or target.id != "type_name":
                        continue
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        shipped.add(node.value.value)
        if not shipped:
            pytest.skip("this tutorial ships no project blocks")

        def walk(condition, step_id: str) -> None:
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
    """

    result = discover_tutorials()
    assert result.tutorials, "discovery found no core tutorials"
    for tutorial in result.tutorials:
        reason = unmet_requirement(tutorial.manifest, DiscoveryEnvironment())
        assert reason is None, (
            f"core tutorial {tutorial.key.tutorial_id!r} ships in a SciStudio it says it cannot run in: {reason}"
        )
        assert tutorial.is_startable, f"core tutorial {tutorial.key.tutorial_id!r} is discovered but not startable"


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
