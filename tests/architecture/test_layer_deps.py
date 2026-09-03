"""Architecture enforcement: layer dependency rules.

Ensures that lower layers never import from higher layers.  The hierarchy is:

    Layer 1  core/
    Layer 2  blocks/
    Layer 3  engine/
    Layer 4  ai/           (the scistudio.ai services package, NOT blocks/ai/)
    Layer 4  previewers/   (the ADR-048 preview subsystem, consumed by api/)
    Layer 4  plot/         (the first-class plot engine, #1824; consumed by api/ AND ai/)
    Layer 5  api/

``explore/`` is the ADR-054 notebook dependency-analysis subsystem (#2231). It
sits outside the layer ordering: it imports nothing from SciStudio beyond
``scistudio.stability`` and nothing third-party at module level (numpy/pandas
are lazy, inside the fingerprint only) — the FR-035 constraint asserted by
``test_explore_import_constraint`` below.

``plot/`` is the relocated ``render(collection)`` engine (#1824, ADR-052 §9). It
is a first-class feature consumed by both the REST route and the MCP plot tools,
so it must import NEITHER ``scistudio.api`` NOR ``scistudio.ai``; callers inject a
``PlotRuntimeContext`` instead.

``previewers/`` is a subsystem the API layer mounts; it may depend on core but
must never import up into ``scistudio.api`` (ADR-048 / #1598).

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
        # The ADR-054 notebook dependency-analysis subsystem (#2231, FR-035):
        # stdlib-only analysis that imports nothing from SciStudio beyond the
        # stability markers (scistudio.stability) and its own package. The full
        # constraint (including lazy-only numpy/pandas) is asserted by
        # test_explore_import_constraint below.
        "explore",
        [
            "scistudio.core",
            "scistudio.blocks",
            "scistudio.engine",
            "scistudio.api",
            "scistudio.ai",
            "scistudio.workflow",
            "scistudio.previewers",
            "scistudio.plot",
            "scistudio.utils",
            "scistudio.cli",
            "scistudio.qa",
            "scistudio.agent_provisioning",
            "scistudio.tutorials",
            "scistudio.desktop",
            "scistudio.testing",
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


# ---------------------------------------------------------------------------
# FR-035: the explore subsystem's import constraint
# ---------------------------------------------------------------------------


def _collect_module_level_imports(nodes: list[ast.stmt]) -> list[tuple[str, int]]:
    """Collect ``(module, level)`` for imports at module level of a source tree.

    Mirrors ``_collect_imports`` (``if TYPE_CHECKING:`` bodies are skipped,
    plain ``if`` and ``try`` bodies are recursed) but keeps the relative-import
    level and does not descend into function or class bodies, so *lazy* imports
    inside functions are deliberately not seen here.
    """
    results: list[tuple[str, int]] = []
    for node in nodes:
        if isinstance(node, ast.If):
            if _is_type_checking_guard(node):
                results.extend(_collect_module_level_imports(node.orelse))
                continue
            results.extend(_collect_module_level_imports(node.body))
            results.extend(_collect_module_level_imports(node.orelse))
            continue
        if isinstance(node, ast.Try):
            results.extend(_collect_module_level_imports(node.body))
            for handler in node.handlers:
                results.extend(_collect_module_level_imports(handler.body))
            results.extend(_collect_module_level_imports(node.orelse))
            results.extend(_collect_module_level_imports(node.finalbody))
            continue
        if isinstance(node, ast.Import):
            results.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            results.append((node.module or "", node.level))
    return results


def test_explore_import_constraint() -> None:
    """FR-035: ``explore`` imports the standard library only at module level.

    Allowed beyond the standard library: relative (intra-package) imports and
    ``scistudio.stability`` (the stability markers). numpy and pandas are
    permitted only lazily inside the fingerprint, so any module-level
    third-party import is a violation.
    """
    import sys

    files = _collect_py_files("explore")
    assert files, f"No .py files found under {SRC_ROOT / 'explore'}"

    allowed_first_party = ("scistudio.stability", "scistudio.explore")
    violations: list[str] = []
    for filepath in files:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
        for module, level in _collect_module_level_imports(tree.body):
            if level > 0:
                continue  # intra-package relative import
            root = module.split(".", 1)[0]
            if root in sys.stdlib_module_names:
                continue
            if any(module == allowed or module.startswith(allowed + ".") for allowed in allowed_first_party):
                continue
            relative = filepath.relative_to(SRC_ROOT)
            violations.append(f"  {relative}: imports {module}")

    assert not violations, (
        "explore/ has module-level imports beyond the standard library, "
        "scistudio.stability, and itself (FR-035):\n" + "\n".join(violations)
    )
