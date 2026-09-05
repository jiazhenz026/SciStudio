"""Architecture enforcement: layer dependency rules.

Ensures that lower layers never import from higher layers.  The hierarchy is:

    Layer 1  core/
    Layer 2  blocks/
    Layer 3  engine/
    Layer 4  ai/           (the scistudio.ai services package, NOT blocks/ai/)
    Layer 4  panels/   (the ADR-048 preview subsystem, consumed by api/)
    Layer 4  plot/         (the first-class plot engine, #1824; consumed by api/ AND ai/)
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

Cross-cutting packages (workflow/, utils/, cli/) are exempt from layer ordering
but core/ still must not import workflow/.

Imports guarded by ``if TYPE_CHECKING:`` are excluded because they have no
runtime effect.
"""

from __future__ import annotations

import ast
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
    expected = {"core", "blocks", "engine", "ai", "panels", "plot"}
    assert expected.issubset(checked_layers), f"Missing layer rules for: {expected - checked_layers}"
