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

``explore/`` is the ADR-054 notebook dependency analysis. Its constraint is
tighter than a layer rule and is stated as an allowlist rather than a
forbidden-import list: ADR-054 spec 2 FR-035 requires that it import from the
standard library and, lazily and only inside the fingerprint, numpy and pandas,
and that it import nothing from SciStudio beyond ``scistudio.stability``. That
is what lets the session, the API layer, and the kernel adapter all import it
without a layering question. ``test_explore_imports_are_allowlisted`` asserts
the allowlist; the ``explore`` entry in ``LAYER_RULES`` is the ordinary layer
rule that comes with it.

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
            "scistudio.previewers",
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


def test_layer_rules_cover_all_source_layers() -> None:
    """Sanity check: every non-cross-cutting source directory appears in at least one rule."""
    checked_layers = {rule[0] for rule in LAYER_RULES}
    expected = {"core", "blocks", "engine", "ai", "previewers", "plot", "explore"}
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


def test_explore_imports_are_allowlisted() -> None:
    """FR-035: explore imports the standard library, and SciStudio only for stability markers.

    ``_get_imports_from_file`` collects **module-level** imports only — it never
    descends into a function body — so an import written lazily inside the
    fingerprint, which is what FR-035 permits for numpy and pandas, is invisible
    here by construction. Anything third-party at module level is a violation,
    and so is any SciStudio import beyond the allowlist.
    """
    files = _collect_py_files("explore")
    assert files, f"No .py files found under {SRC_ROOT / 'explore'}"

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
