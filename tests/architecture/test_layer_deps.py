"""Architecture enforcement: layer dependency rules.

Ensures that lower layers never import from higher layers.  The hierarchy is:

    Layer 1  core/
    Layer 2  blocks/
    Layer 3  engine/
    Layer 4  ai/           (the scistudio.ai services package, NOT blocks/ai/)
    Layer 4  previewers/   (the ADR-048 preview subsystem, consumed by api/)
    Layer 4  plot/         (the first-class plot engine, #1824; consumed by api/ AND ai/)
    Layer 4  explore/      (the ADR-054 notebook analysis; consumed by api/ AND the kernel)
    Layer 5  api/

``plot/`` is the relocated ``render(collection)`` engine (#1824, ADR-052 §9). It
is a first-class feature consumed by both the REST route and the MCP plot tools,
so it must import NEITHER ``scistudio.api`` NOR ``scistudio.ai``; callers inject a
``PlotRuntimeContext`` instead.

``previewers/`` is a subsystem the API layer mounts; it may depend on core but
must never import up into ``scistudio.api`` (ADR-048 / #1598).

``explore/`` is the ADR-054 subsystem, and it carries two rules of different
scope, which is worth reading carefully before changing either.

The subsystem rule is the ordinary one: the ``explore`` entry in
``LAYER_RULES`` forbids ``api``, ``ai``, and ``engine`` (spec 3 FR-008,
FR-060). The session runtime imports ``core`` for storage, lineage, and
versioning and ``blocks`` for the registry, which is what spec 3 §4.1 places it
beside the engine to do. ``test_engine_does_not_import_explore`` is the other
half of FR-060, since a one-directional rule needs both halves stated.
``test_explore_never_imports_upward_at_any_depth`` is the same forbidden list —
read out of ``LAYER_RULES``, not restated — applied to function and class bodies
as well as the module body, because the explore runtime defers imports inside
functions by design and a violation written that way would otherwise be
invisible.

The stricter rule is about **two modules**, not the subsystem: spec 2 FR-035
requires the analysis and the fingerprint to import from the standard library
and, lazily and only inside the fingerprint, numpy and pandas, and to import
nothing from SciStudio beyond ``scistudio.stability``. That is what lets the
session, the API layer, and the kernel adapter all import the analysis without
a layering question. ``test_explore_imports_are_allowlisted`` asserts it over
``FR_035_CONSTRAINED_MODULES``, and fails if one of those modules is renamed
away rather than silently ceasing to apply.

Cross-cutting packages (workflow/, utils/, cli/) are exempt from layer ordering
but core/ still must not import workflow/.

Imports guarded by ``if TYPE_CHECKING:`` are excluded because they have no
runtime effect.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "scistudio"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _is_type_checking_guard(node: ast.If) -> bool:
    """Return ``True`` when *node* is ``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _collect_imports(
    nodes: list[ast.stmt],
    imports: list[str],
) -> None:
    """Walk a list of AST statements and collect runtime import strings.

    Imports inside ``if TYPE_CHECKING:`` blocks are skipped entirely.
    """
    for node in nodes:
        # Recurse into if/else but skip TYPE_CHECKING bodies
        if isinstance(node, ast.If):
            if _is_type_checking_guard(node):
                # Skip the body (type-only imports); still check ``else``
                _collect_imports(node.orelse, imports)
                continue
            # Normal if — recurse into both branches
            _collect_imports(node.body, imports)
            _collect_imports(node.orelse, imports)
            continue

        # Recurse into try/except/finally
        if isinstance(node, ast.Try):
            _collect_imports(node.body, imports)
            for handler in node.handlers:
                _collect_imports(handler.body, imports)
            _collect_imports(node.orelse, imports)
            _collect_imports(node.finalbody, imports)
            continue

        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)


def _get_imports_from_file(filepath: Path) -> list[str]:
    """Parse *filepath* and return all runtime-imported module strings."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    imports: list[str] = []
    _collect_imports(tree.body, imports)
    return imports


def _runtime_imports_at_any_depth(source: str, *, filename: str = "<scratch>") -> list[str]:
    """Every runtime-imported module in *source*, function and class bodies included.

    ``_get_imports_from_file`` walks the module body only, which is the right
    reading for a rule about what a module costs to import. It is the wrong
    reading for a rule about what a subsystem is *allowed to reach*: an import
    written inside a function still runs, and the explore subsystem is built on
    function-level imports by design — ``SessionService.build_kernel`` defers
    ``jupyter_client``, ``ExploreSession.cell_marks`` defers ``packaging``. A
    forbidden import written the same way would be invisible to the module-level
    walk, which is exactly where it would end up.

    ``if TYPE_CHECKING:`` bodies are excluded at any depth, as they are there.
    """
    tree = ast.parse(source, filename=filename)

    type_checking_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            for statement in node.body:
                for child in ast.walk(statement):
                    type_checking_only.add(id(child))

    imports: list[str] = []
    for node in ast.walk(tree):
        if id(node) in type_checking_only:
            continue
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
    return imports


def _collect_py_files(subdir: str) -> list[Path]:
    """Collect all ``.py`` files under ``SRC_ROOT / subdir``."""
    target = SRC_ROOT / subdir
    if not target.exists():
        return []
    return sorted(target.rglob("*.py"))


# ---------------------------------------------------------------------------
# Forbidden-import checker
# ---------------------------------------------------------------------------


def _is_forbidden(imp: str, forbidden_prefix: str) -> bool:
    """Return ``True`` when *imp* matches *forbidden_prefix*.

    Special handling for ``scistudio.ai`` to avoid false positives on
    ``scistudio.blocks.ai`` (which is in the blocks layer, not the AI
    services layer).
    """
    # Exact match (e.g. ``import scistudio.api``)
    if imp == forbidden_prefix:
        return True

    # Prefix match (e.g. ``from scistudio.api.routes import ...``)
    prefix_dot = forbidden_prefix if forbidden_prefix.endswith(".") else forbidden_prefix + "."
    if imp.startswith(prefix_dot):
        # Exclude false positives: ``scistudio.blocks.ai.*`` is NOT the AI
        # services layer ``scistudio.ai.*``.
        return not (forbidden_prefix == "scistudio.ai" and imp.startswith("scistudio.blocks.ai"))

    return False


# ---------------------------------------------------------------------------
# Layer rules
# ---------------------------------------------------------------------------

LAYER_RULES: list[tuple[str, list[str]]] = [
    (
        "core",
        [
            "scistudio.blocks",
            "scistudio.engine",
            "scistudio.api",
            "scistudio.ai",
            "scistudio.workflow",
        ],
    ),
    (
        "blocks",
        [
            "scistudio.engine",
            "scistudio.api",
            "scistudio.ai",
        ],
    ),
    (
        "engine",
        [
            "scistudio.api",
            "scistudio.ai",
        ],
    ),
    (
        "ai",
        [
            "scistudio.api",
        ],
    ),
    (
        "previewers",
        [
            "scistudio.api",
        ],
    ),
    (
        # The first-class plot engine (#1824, ADR-052 §9). Consumed by both the
        # REST route (api/) and the MCP plot tools (ai/), so it must import
        # NEITHER — callers inject a PlotRuntimeContext instead.
        "plot",
        [
            "scistudio.api",
            "scistudio.ai",
        ],
    ),
    (
        # The ADR-054 explore subsystem. Spec 3 §4.1 places it beside the engine
        # at the layer of ``previewers`` and ``plot``: it imports ``core`` for
        # storage, lineage, and versioning and ``blocks`` for the registry, and
        # it imports neither the API, nor AI, nor the engine (spec 3 FR-008,
        # FR-060). ``test_engine_does_not_import_explore`` is the other half of
        # FR-060 — the engine never imports it either, and the interactive pause
        # is the one place they meet, through a prompt event.
        #
        # The analysis and fingerprint modules inside this package are held to a
        # far stricter rule — standard library plus stability markers only —
        # by ``test_explore_imports_are_allowlisted`` below (spec 2 FR-035).
        # That is a rule about two modules, not about the subsystem.
        "explore",
        [
            "scistudio.api",
            "scistudio.ai",
            "scistudio.engine",
        ],
    ),
]


@pytest.mark.parametrize(
    ("layer", "forbidden"),
    LAYER_RULES,
    ids=[rule[0] for rule in LAYER_RULES],
)
def test_layer_does_not_import_forbidden(layer: str, forbidden: list[str]) -> None:
    """Verify that *layer* contains no runtime imports from *forbidden* modules."""
    files = _collect_py_files(layer)
    assert files, f"No .py files found under {SRC_ROOT / layer}"

    violations: list[str] = []
    for filepath in files:
        imports = _get_imports_from_file(filepath)
        for imp in imports:
            for forbidden_prefix in forbidden:
                if _is_forbidden(imp, forbidden_prefix):
                    relative = filepath.relative_to(SRC_ROOT)
                    violations.append(f"  {relative}: imports {imp}")

    assert not violations, f"Layer '{layer}/' has forbidden imports:\n" + "\n".join(violations)


def test_layer_rules_cover_all_source_layers() -> None:
    """Sanity check: every non-cross-cutting source directory appears in at least one rule."""
    checked_layers = {rule[0] for rule in LAYER_RULES}
    expected = {"core", "blocks", "engine", "ai", "previewers", "plot", "explore"}
    assert expected.issubset(checked_layers), f"Missing layer rules for: {expected - checked_layers}"


#: The ``explore`` entry's forbidden list, read out of ``LAYER_RULES`` rather
#: than restated. FR-060 has one enumeration of what the subsystem may not
#: import; the depth test below is the same rule looked at more closely, not a
#: second mechanism, and deriving the list is what keeps it that way.
EXPLORE_FORBIDDEN: list[str] = next(forbidden for layer, forbidden in LAYER_RULES if layer == "explore")


def test_explore_never_imports_upward_at_any_depth() -> None:
    """FR-060 over the whole file, not only its module body.

    ``test_layer_does_not_import_forbidden`` walks each module's top level. That
    is the correct depth for "what does importing this cost", and the wrong
    depth for "what may this subsystem reach": the explore runtime defers
    imports inside functions as a matter of course — ``jupyter_client`` in
    ``build_kernel``, ``packaging`` in ``cell_marks``, the kernel and bridge
    classes in the service's factories — so a lazy ``import scistudio.api``
    inside a method is the shape a violation would actually take here, and the
    module-level walk cannot see it.

    Spec 3 §4.1 is unconditional about the direction: the subsystem imports
    ``core`` and ``blocks``, and it imports neither the API, nor AI, nor the
    engine. Nothing in that sentence is about where in a file the import is
    written.
    """
    violations: list[str] = []
    for filepath in _collect_py_files("explore"):
        source = filepath.read_text(encoding="utf-8")
        for imp in _runtime_imports_at_any_depth(source, filename=str(filepath)):
            for forbidden_prefix in EXPLORE_FORBIDDEN:
                if _is_forbidden(imp, forbidden_prefix):
                    violations.append(f"  {filepath.relative_to(SRC_ROOT)}: imports {imp}")

    assert not violations, (
        "the explore subsystem must import neither the API, nor AI, nor the engine, at any depth "
        "(ADR-054 spec 3 FR-008, FR-060):\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    ("scratch", "expected"),
    [
        pytest.param("import scistudio.api\n", "scistudio.api", id="module-level-import"),
        pytest.param(
            "def open_panel():\n    import scistudio.api\n",
            "scistudio.api",
            id="deferred-inside-a-function",
        ),
        pytest.param(
            "class Service:\n    def build(self):\n        from scistudio.engine.events import EventBus\n",
            "scistudio.engine.events",
            id="deferred-inside-a-method",
        ),
        pytest.param(
            "def resolve():\n    try:\n        from scistudio.ai.agent import mcp\n    except ImportError:\n"
            "        mcp = None\n",
            "scistudio.ai.agent",
            id="deferred-inside-a-try",
        ),
    ],
)
def test_the_explore_depth_rule_catches_a_planted_import(scratch: str, expected: str) -> None:
    """The depth rule fails on a violation rather than merely passing on clean code.

    A rule that has never been shown to fail is a rule nobody has tested. Each
    case is a way an upward import could plausibly be written into an explore
    module — including the deferred forms the subsystem already uses for
    legitimate reasons, which is what makes them plausible.
    """
    found = _runtime_imports_at_any_depth(scratch)
    assert any(_is_forbidden(imp, prefix) for imp in found for prefix in EXPLORE_FORBIDDEN), (
        f"a planted {expected!r} was not caught; found {found}"
    )


def test_the_explore_depth_rule_still_allows_core_and_blocks() -> None:
    """The depth rule must not become the over-tight rule spec 3 §4.1 rejects.

    ``explore`` imports ``core`` for storage, lineage, and versioning and
    ``blocks`` for the registry and the Code Block — that is what §4.1 places it
    beside the engine to do. A depth check that forbade those would block the
    runtime from doing its job while looking stricter, which is the failure mode
    this asserts against.
    """
    scratch = (
        "from scistudio.core.lineage.store import LineageStore\n"
        "def cell_marks():\n"
        "    from scistudio.blocks.code.backends.notebook import NotebookBackend\n"
    )
    found = _runtime_imports_at_any_depth(scratch)
    assert found == ["scistudio.core.lineage.store", "scistudio.blocks.code.backends.notebook"]
    assert not [imp for imp in found for prefix in EXPLORE_FORBIDDEN if _is_forbidden(imp, prefix)]


def test_the_explore_depth_rule_ignores_type_checking_imports() -> None:
    """A ``TYPE_CHECKING`` import has no runtime effect and is not a violation.

    The session module already imports its kernel types this way. Counting them
    would fail the suite on code that is correct, which is how a layer rule gets
    weakened by whoever has to make the build green.
    """
    scratch = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from scistudio.api.runtime import ApiRuntime\n"
        "    def _later():\n"
        "        import scistudio.engine\n"
    )
    assert _runtime_imports_at_any_depth(scratch) == ["typing"]


def test_engine_does_not_import_explore() -> None:
    """FR-060, the half a one-directional rule always forgets.

    ``scistudio.explore`` not importing the engine is enforced by the
    ``explore`` entry in ``LAYER_RULES``. That says nothing about the engine
    importing ``explore``, and spec 3 §4.1 forbids it: the interactive pause is
    the one point where the engine and a session meet, and it meets the session
    the way it meets every interactive block — through a prompt event and a
    decision, never through a reference to the session.

    Without this, the engine could take a direct dependency on the session
    service and every other rule here would still pass.
    """
    violations: list[str] = []
    for filepath in _collect_py_files("engine"):
        for imp in _get_imports_from_file(filepath):
            if imp == "scistudio.explore" or imp.startswith("scistudio.explore."):
                violations.append(f"  {filepath.relative_to(SRC_ROOT)}: imports {imp}")

    assert not violations, (
        "the engine must reach a session through a prompt event and a decision, "
        "never through a reference to it (ADR-054 spec 3 FR-060):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# ADR-054 spec 2 FR-035 / SC-011: the explore subsystem's import allowlist
# ---------------------------------------------------------------------------

#: The only SciStudio modules the **analysis** may import at module level.
#: ``scistudio.stability`` carries the tier and ``since`` decorators (ADR-052 §5),
#: which are no-ops at runtime; ``scistudio.explore`` itself is the package.
EXPLORE_ALLOWED_SCISTUDIO_IMPORTS: set[str] = {"scistudio.stability", "scistudio.explore"}

#: The modules FR-035 constrains. Its subject is "the analysis and fingerprint
#: modules", not the whole subsystem: the session runtime that
#: ``docs/specs/adr-054-explore-session.md`` adds beside them imports ``core``
#: for storage, lineage, and versioning and ``blocks`` for the registry, which
#: is what §4.1 of that spec places it there to do. The package ``__init__``
#: is included because it re-exports only the analysis, which is what keeps
#: importing the analysis from dragging a kernel in.
#:
#: The subsystem-wide rule — explore imports neither ``api``, nor ``ai``, nor
#: ``engine`` — is the ``explore`` entry in ``LAYER_RULES`` above, and it
#: applies to every file in the package.
FR_035_CONSTRAINED_MODULES: frozenset[str] = frozenset({"__init__.py", "dependency_analysis.py", "fingerprint.py"})


def _is_stdlib(module: str) -> bool:
    """Return ``True`` when *module*'s top-level package ships with CPython."""
    return module.partition(".")[0] in sys.stdlib_module_names


def test_explore_imports_are_allowlisted() -> None:
    """FR-035: the analysis imports the standard library, and SciStudio only for stability markers.

    The constraint's subject is the analysis and fingerprint modules, not the
    whole subsystem — see ``FR_035_CONSTRAINED_MODULES``. The second assertion
    below fails if one of those modules is renamed or removed, so the rule
    cannot quietly stop applying to the code it exists for.

    ``_get_imports_from_file`` collects **module-level** imports only — it never
    descends into a function body — so an import written lazily inside the
    fingerprint, which is what FR-035 permits for numpy and pandas, is invisible
    here by construction. Anything third-party at module level is a violation,
    and so is any SciStudio import beyond the allowlist.
    """
    files = [f for f in _collect_py_files("explore") if f.name in FR_035_CONSTRAINED_MODULES]
    assert files, f"No FR-035-constrained modules found under {SRC_ROOT / 'explore'}"
    assert {f.name for f in files} == set(FR_035_CONSTRAINED_MODULES), (
        "FR_035_CONSTRAINED_MODULES names a module that no longer exists; the constraint "
        "must follow the analysis rather than silently stop applying to it"
    )

    violations: list[str] = []
    for filepath in files:
        relative = filepath.relative_to(SRC_ROOT)
        for imp in _get_imports_from_file(filepath):
            if _is_stdlib(imp):
                continue
            if imp.partition(".")[0] != "scistudio":
                violations.append(f"  {relative}: imports third-party {imp} at module level")
                continue
            if not any(
                imp == allowed or imp.startswith(allowed + ".") for allowed in EXPLORE_ALLOWED_SCISTUDIO_IMPORTS
            ):
                violations.append(f"  {relative}: imports {imp}, which FR-035 does not allow")

    assert not violations, "explore/ violates the FR-035 import allowlist:\n" + "\n".join(violations)


def test_explore_does_not_import_ipython_or_a_notebook_library() -> None:
    """FR-003: the analysis depends on the standard library only.

    IPython, ``nbformat``, and every static-analysis package are named by the
    spec because the temptation is real: IPython would transform magics and
    ``nbformat`` would parse the notebook. Both are refused, so this assertion
    names them rather than relying on the allowlist alone to catch a
    reintroduction.
    """
    forbidden = {"IPython", "nbformat", "nbclient", "jupyter_client", "astroid", "jedi", "libcst", "parso"}
    violations: list[str] = []
    for filepath in (f for f in _collect_py_files("explore") if f.name in FR_035_CONSTRAINED_MODULES):
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.partition(".")[0] in forbidden:
                    violations.append(f"  {filepath.relative_to(SRC_ROOT)}: imports {name}")

    assert not violations, "explore/ imports a package FR-003 forbids:\n" + "\n".join(violations)
