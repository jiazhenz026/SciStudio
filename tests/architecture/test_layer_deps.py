"""Architecture enforcement: layer dependency rules.

Ensures that lower layers never import from higher layers.  The hierarchy is:

    Layer 1  core/
    Layer 2  blocks/
    Layer 3  engine/
    Layer 4  ai/           (the scistudio.ai services package, NOT blocks/ai/)
    Layer 4  panels/   (the ADR-048 preview subsystem, consumed by api/)
    Layer 4  plot/         (the first-class plot engine, #1824; consumed by api/ AND ai/)
    Layer 4  explore/      (the ADR-054 notebook analysis; consumed by api/ AND the kernel)
    Layer 5  api/

``plot/`` is the relocated ``render(collection)`` engine (#1824, ADR-052 §9). It
is a first-class feature consumed by both the REST route and the MCP plot tools,
so it must import NEITHER ``scistudio.api`` NOR ``scistudio.ai``; callers inject a
``PlotRuntimeContext`` instead.

``panels/`` is a subsystem the API layer mounts; it may depend on core but
must never import up into ``scistudio.api`` (ADR-048 / #1598).

``core/panels.py`` is the shared panel contract (ADR-054 spec 1 FR-001, FR-040,
D-009). It is in Layer 1 for a layering reason rather than a filing one: the
block layer declares a manifest on a block class, the panel subsystem validates
manifests above it, and the API layer routes them above that, so the one type
all three read has to sit below all three.
:func:`test_the_panel_contract_is_reachable_downward_from_every_consumer`
checks that directly, because the per-layer rules above would still pass if the
contract were duplicated instead of shared.

``explore/`` is the ADR-054 notebook dependency analysis. Its constraint is
tighter than a layer rule and is stated as an allowlist rather than a
forbidden-import list: ADR-054 spec 2 FR-035 requires that it import from the
standard library and, lazily and only inside the fingerprint, a closed list of
third-party packages, and that it import nothing from SciStudio beyond
``scistudio.stability``. That is what lets the session, the API layer, and the
kernel adapter all import it without a layering question.
``test_explore_imports_are_allowlisted`` asserts the allowlist **at every
depth**, because every import FR-035 permits is written lazily inside a function
and a module-level reader would therefore measure none of them; the ``explore``
entry in ``LAYER_RULES`` is the ordinary layer rule that comes with it.

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
        "panels",
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
        # The ADR-054 notebook dependency analysis (spec 2, FR-035). Imported by
        # the explore session, the API layer, and the kernel adapter alike, so it
        # must import none of them. The allowlist test below is the stronger
        # statement; this rule keeps ``explore`` inside the same mechanism as
        # every other subsystem.
        "explore",
        [
            "scistudio.api",
            "scistudio.ai",
            "scistudio.engine",
            "scistudio.blocks",
            "scistudio.core",
            "scistudio.panels",
            "scistudio.plot",
            "scistudio.workflow",
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


#: The module the ADR-054 panel contract lives in (FR-001, D-009), and the
#: layers whose modules read it.
PANEL_CONTRACT_MODULE = "scistudio.core.panels"
PANEL_CONTRACT_CONSUMERS = ("blocks", "panels")


def test_the_panel_contract_module_is_in_the_core_layer() -> None:
    """FR-040: the layer enumeration names the module the contract lives in."""
    contract = SRC_ROOT / "core" / "panels.py"
    assert contract.is_file(), f"the panel contract must live at {contract}"
    assert PANEL_CONTRACT_MODULE.split(".")[1] == "core"


@pytest.mark.parametrize("layer", PANEL_CONTRACT_CONSUMERS)
def test_the_panel_contract_is_reachable_downward_from_every_consumer(layer: str) -> None:
    """Each consumer imports the contract from core rather than restating it.

    The point of FR-001 is not that ``core/panels.py`` exists; it is that
    nothing above it defines a second manifest, capability set, or version
    constant of its own. The per-layer forbidden-import rules cannot see that —
    a duplicated contract breaks no import direction at all — so the property is
    asserted here: at least one module in each consuming layer imports the
    contract, and no module in any of them defines the version constant.
    """
    files = _collect_py_files(layer)
    assert files, f"No .py files found under {SRC_ROOT / layer}"

    importers = [
        path.relative_to(SRC_ROOT).as_posix()
        for path in files
        if any(imp == PANEL_CONTRACT_MODULE for imp in _get_imports_from_file(path))
    ]
    assert importers, f"layer {layer!r} must read the panel contract from {PANEL_CONTRACT_MODULE}"


def test_the_block_layer_does_not_import_the_panel_subsystem() -> None:
    """ADR-054 9.2: the block layer sits below the panel subsystem.

    ``panels/`` is not in the block layer's forbidden list above, because
    ``panels/`` was never below it — the two are unordered siblings for
    everything except this contract. Since the contract moved to core, the block
    layer has no remaining reason to reach into ``panels/`` at all, and an edge
    appearing there would be the first sign of the duplication FR-001 removes.
    """
    violations: list[str] = []
    for path in _collect_py_files("blocks"):
        for imp in _get_imports_from_file(path):
            if imp == "scistudio.panels" or imp.startswith("scistudio.panels."):
                violations.append(f"  {path.relative_to(SRC_ROOT).as_posix()}: imports {imp}")
    assert not violations, "the block layer must not import the panel subsystem:\n" + "\n".join(violations)


def test_layer_rules_cover_all_source_layers() -> None:
    """Sanity check: every non-cross-cutting source directory appears in at least one rule."""
    checked_layers = {rule[0] for rule in LAYER_RULES}
    expected = {"core", "blocks", "engine", "ai", "panels", "plot", "explore"}
    assert expected.issubset(checked_layers), f"Missing layer rules for: {expected - checked_layers}"


# ---------------------------------------------------------------------------
# ADR-054 spec 2 FR-035 / SC-011: the explore subsystem's import allowlist
# ---------------------------------------------------------------------------

#: The only SciStudio modules ``scistudio.explore`` may import at module level.
#: ``scistudio.stability`` carries the tier and ``since`` decorators (ADR-052 §5),
#: which are no-ops at runtime; ``scistudio.explore`` itself is the package.
EXPLORE_ALLOWED_SCISTUDIO_IMPORTS: set[str] = {"scistudio.stability", "scistudio.explore"}


def _is_stdlib(module: str) -> bool:
    """Return ``True`` when *module*'s top-level package ships with CPython."""
    return module.partition(".")[0] in sys.stdlib_module_names


#: The only third-party packages ``scistudio.explore`` may import, and the only
#: module that may import them. FR-035 permits numpy and pandas "lazily and only
#: inside the fingerprint", and spec §4.1 directs the same module to hash array
#: bytes through ``xxhash``; nothing else under ``explore/`` may reach for a
#: third-party package at any depth.
EXPLORE_ALLOWED_THIRD_PARTY: set[str] = {"numpy", "pandas", "xxhash"}

#: The file the three above are permitted in, relative to ``src/scistudio``.
EXPLORE_THIRD_PARTY_MODULE = Path("explore") / "fingerprint.py"


def _absolute_module(node: ast.ImportFrom, relative: Path) -> str:
    """Resolve ``from . import x`` to the dotted package it actually names.

    A relative import is an import like any other, and ``from .. import core``
    would leave ``explore/`` if it were skipped for having no ``module``.
    """
    if node.level == 0:
        return node.module or ""
    package = ["scistudio", *relative.parts[:-1]]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module]) if node.module else ".".join(base)


def _collect_imports_at_any_depth(source: str, relative: Path) -> list[tuple[str, int]]:
    """Every runtime import in *source*, function bodies included, as ``(module, lineno)``.

    The counterpart of :func:`_collect_imports`, which walks statement lists at
    module level. This one uses :func:`ast.walk`, so an import written inside a
    ``def`` is reported like any other. ``if TYPE_CHECKING:`` bodies are still
    excluded, because a type-only import has no runtime effect.
    """
    tree = ast.parse(source, filename=str(relative))
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            for statement in node.body:
                for inner in ast.walk(statement):
                    guarded.add(id(inner))

    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((_absolute_module(node, relative), node.lineno))
    return found


def _explore_import_violations(source: str, relative: Path) -> list[str]:
    """Report every import in *source* that FR-035's allowlist does not permit.

    Split out from the test so the test can be shown to fail: its sibling feeds
    it a lazy ``import requests`` and asserts it is caught. A criterion whose
    measurement has never been seen to fail is a statement, and SC-011 spent this
    change as one.
    """
    violations: list[str] = []
    for module, lineno in _collect_imports_at_any_depth(source, relative):
        top = module.partition(".")[0]
        if _is_stdlib(module):
            continue
        if top == "scistudio":
            if not any(
                module == allowed or module.startswith(allowed + ".") for allowed in EXPLORE_ALLOWED_SCISTUDIO_IMPORTS
            ):
                violations.append(f"  {relative}:{lineno}: imports {module}, which FR-035 does not allow")
            continue
        if top not in EXPLORE_ALLOWED_THIRD_PARTY:
            violations.append(f"  {relative}:{lineno}: imports third-party {module}, which FR-035 forbids")
        elif relative != EXPLORE_THIRD_PARTY_MODULE:
            violations.append(
                f"  {relative}:{lineno}: imports {module}, which FR-035 permits only inside {EXPLORE_THIRD_PARTY_MODULE}"
            )
    return violations


def test_explore_imports_are_allowlisted() -> None:
    """FR-035 / SC-011: the closed import allowlist, measured at every depth.

    FR-035 names three third-party packages — numpy, pandas, and the ``xxhash``
    digest spec §4.1 directs the fingerprint to use — permits them *only inside
    the fingerprint*, and allows nothing from SciStudio beyond the stability
    markers. Every one of the three is written lazily, inside a function body, so
    the criterion cannot be measured by a module-level reader: SC-011 says as
    much, and :func:`_collect_imports_at_any_depth` is what makes that sentence
    true. A lazy ``import requests`` in either module is a violation here, and so
    is a lazy ``import numpy`` in ``dependency_analysis.py``, which FR-035 gives
    to the fingerprint alone.

    The sibling below proves this test can fail; without it the allowlist would
    be an assertion nobody has watched bite.
    """
    files = _collect_py_files("explore")
    assert files, f"No .py files found under {SRC_ROOT / 'explore'}"

    violations: list[str] = []
    for filepath in files:
        relative = filepath.relative_to(SRC_ROOT)
        violations.extend(_explore_import_violations(filepath.read_text(encoding="utf-8"), relative))

    assert not violations, "explore/ violates the FR-035 import allowlist:\n" + "\n".join(violations)


def test_the_explore_import_allowlist_catches_what_it_claims_to() -> None:
    """The negative control for the allowlist: each forbidden shape is reported.

    SC-011's previous measurement could not fail — it read module-level imports
    only, while every import FR-035 permits is lazy — so a fourth lazy dependency
    would have passed every check in the subsystem. These four sources are what
    that reader could not see; each must now be a violation, and the permitted
    shape beside them must not be.
    """
    fingerprint = EXPLORE_THIRD_PARTY_MODULE
    analysis = Path("explore") / "dependency_analysis.py"

    assert _explore_import_violations("def h():\n    import requests\n    return requests\n", fingerprint), (
        "a lazy third-party import inside the fingerprint must be caught"
    )
    assert _explore_import_violations("def h():\n    import numpy\n    return numpy\n", analysis), (
        "FR-035 permits numpy inside the fingerprint only"
    )
    assert _explore_import_violations("def h():\n    from scistudio.core import x\n    return x\n", fingerprint), (
        "a lazy SciStudio import beyond the stability markers must be caught"
    )
    assert _explore_import_violations("class C:\n    def h(self):\n        import jedi\n", analysis), (
        "depth is not a hiding place"
    )
    assert not _explore_import_violations(
        "import symtable\nfrom scistudio.stability import provisional\n\n\ndef h():\n    import xxhash\n",
        fingerprint,
    ), "the shape FR-035 permits must not be reported"


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
    for filepath in _collect_py_files("explore"):
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
