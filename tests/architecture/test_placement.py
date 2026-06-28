"""Architecture enforcement: file placement and documentation rules.

Validates that:

* No stray ``.py`` files exist in the package root.
* Every ``.py`` file has a module-level docstring.
* Code runners (``CodeRunner`` implementations) are only in
  ``blocks/code/runners/``.
* Phase 11 deletions are not silently re-introduced (T-TRK-001
  ``process/contrib/``, T-TRK-004 ``blocks/io/adapters/`` and
  ``adapter_registry.py``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "scistudio"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_stray_files_in_package_root() -> None:
    """Only Python dunder bootstrap files may sit directly in ``src/scistudio/``.

    The original rule was a hard-equals on ``["__init__.py"]`` to keep
    drive-by ``foo.py`` from accumulating at the top level. Evolved
    (#1014) to an allowlist set so the standard Python dunder pattern
    ``__main__.py`` (PEP 338, 2005 — the canonical "this package is
    runnable" marker) can ship alongside ``__init__.py`` without
    bypassing the architecture rule.

    Files allowed:

    * ``__init__.py`` — package init (always required).
    * ``__main__.py`` — enables ``python -m scistudio ...`` dispatch.
      Every ``.scistudio/mcp.json`` invokes the bridge via
      ``{sys.executable} -m scistudio mcp-bridge`` so the bridge always
      runs from the same interpreter that emitted the manifest
      (avoids the PATH-shadowed ``scistudio.EXE`` foot-gun the
      2026-05-14 hotfix originally addressed).

    Anything else stays in a subpackage.
    """
    # #1742: _version.py (single source) + version.py (deriver) are intentional
    # top-level modules imported very early by __init__.
    allowed = {"__init__.py", "__main__.py", "_version.py", "version.py"}
    py_files = sorted(f.name for f in SRC_ROOT.iterdir() if f.is_file() and f.suffix == ".py")
    stray = [f for f in py_files if f not in allowed]
    assert not stray, f"Found unexpected files in package root: {stray}"


def _all_py_files() -> list[Path]:
    """Return all ``.py`` files under SRC_ROOT, sorted for determinism."""
    return sorted(SRC_ROOT.rglob("*.py"))


@pytest.mark.parametrize(
    "filepath",
    _all_py_files(),
    ids=[str(f.relative_to(SRC_ROOT)) for f in _all_py_files()],
)
def test_every_module_has_docstring(filepath: Path) -> None:
    """Every ``.py`` file must have a module-level docstring."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    docstring = ast.get_docstring(tree)
    relative = filepath.relative_to(SRC_ROOT)
    assert docstring is not None, f"{relative} is missing a module-level docstring"


def _find_classes_referencing(base_name: str, search_dir: Path) -> list[tuple[Path, str]]:
    """Find classes that reference *base_name* in their bases, outside *search_dir*.

    We use AST analysis rather than runtime imports so that empty stub
    modules (no class defined yet) do not produce false negatives.
    """
    hits: list[tuple[Path, str]] = []
    for filepath in sorted(SRC_ROOT.rglob("*.py")):
        # Skip the canonical directory
        try:
            filepath.relative_to(search_dir)
            continue
        except ValueError:
            pass

        source = filepath.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                name: str | None = None
                if isinstance(base, ast.Name):
                    name = base.id
                elif isinstance(base, ast.Attribute):
                    name = base.attr
                if name == base_name:
                    hits.append((filepath, node.name))
    return hits


def test_no_format_adapter_subclasses_remain() -> None:
    """No ``FormatAdapter`` subclass should exist anywhere in core (T-TRK-004).

    The ``FormatAdapter`` protocol and every concrete adapter under
    ``blocks/io/adapters/`` were deleted in T-TRK-004 per ADR-028 §D2.
    The replacement contract is the abstract :class:`IOBlock` (with
    ``load`` / ``save`` abstractmethods) and the upcoming
    ``LoadData`` / ``SaveData`` classes from T-TRK-007 / T-TRK-008.
    """
    # ``search_dir`` does not need to exist; if it doesn't (post-T-TRK-004
    # state), every ``.py`` file is scanned and the assertion passes only
    # when no class declares ``FormatAdapter`` as a base.
    misplaced = _find_classes_referencing("FormatAdapter", SRC_ROOT / "blocks" / "io" / "adapters")
    violations = [f"  {fp.relative_to(SRC_ROOT)}: class {cls_name}" for fp, cls_name in misplaced]
    assert not violations, "FormatAdapter subclasses found in core after T-TRK-004 deletion:\n" + "\n".join(violations)


def test_runners_in_correct_directory() -> None:
    """Classes inheriting from ``CodeRunner`` should only live in ``blocks/code/runners/``."""
    canonical = SRC_ROOT / "blocks" / "code" / "runners"
    misplaced = _find_classes_referencing("CodeRunner", canonical)
    violations = [f"  {fp.relative_to(SRC_ROOT)}: class {cls_name}" for fp, cls_name in misplaced]
    assert not violations, "CodeRunner subclasses found outside blocks/code/runners/:\n" + "\n".join(violations)


def test_no_py_files_outside_known_packages() -> None:
    """All ``.py`` files should be inside known top-level packages."""
    known_packages = {
        "core",
        "blocks",
        "engine",
        "ai",
        "api",
        "workflow",
        "utils",
        "cli",
        "testing",
        "qa",  # ADR-042: documentation/frontmatter/fact-registry audit tooling
        "agent_provisioning",  # ADR-040 §3.5-3.8: prod-env agent provisioning module
        "previewers",  # ADR-048: extensible type previewer subsystem (scistudio.previewers)
        "plot",  # #1824 / ADR-052 §9: first-class plot render(collection) engine (scistudio.plot)
        "desktop",  # ADR-037: desktop distribution path/resource helpers
        "stability",  # ADR-052 §5: public-API stability decorators (scistudio.stability)
        "telemetry",  # #1855: alpha-only tester check-in (removed in beta with the gate)
    }
    stray: list[str] = []
    for filepath in SRC_ROOT.rglob("*.py"):
        relative = filepath.relative_to(SRC_ROOT)
        parts = relative.parts
        if len(parts) == 1:
            # Root-level files (already checked by test_no_stray_files_in_package_root)
            continue
        top_package = parts[0]
        if top_package not in known_packages:
            stray.append(str(relative))
    assert not stray, f"Found .py files outside known packages: {stray}"


def test_process_contrib_directory_removed() -> None:
    """``blocks/process/contrib/`` must not exist (T-TRK-001).

    Phase 11 abandons the ``contrib`` pattern in favour of the plugin
    package pattern. The four 1-line stub modules and their parent
    directory were deleted by T-TRK-001 (Phase 11 master plan §2.5
    sub-1a). The real ``CellposeSegment`` implementation lives in the
    standalone ``scistudio-blocks-imaging`` package repository (decoupled
    from core per #1770). This regression test prevents the directory from
    being silently re-introduced.
    """
    contrib_dir = SRC_ROOT / "blocks" / "process" / "contrib"
    assert not contrib_dir.exists(), (
        f"{contrib_dir.relative_to(SRC_ROOT)} must not exist — the contrib "
        "pattern was deleted in T-TRK-001 (Phase 11). Add new process "
        "blocks to scistudio/blocks/process/builtins/ or to a standalone "
        "scistudio-blocks-* plugin package repository."
    )


def test_adapters_directory_removed() -> None:
    """``blocks/io/adapters/`` must not exist (T-TRK-004).

    ADR-028 §D2 deletes the entire bundled adapter layer
    (``__init__.py``, ``base.py`` + 8 ``*_adapter.py`` modules) in
    favour of plugin-owned ``IOBlock`` subclasses. The TIFF and mzXML
    adapter logic moves to the imaging and LCMS plugins via
    T-IMG-002 and T-LCMS-002 respectively, sourced from the deleted
    files' git history rather than from a re-introduced ``adapters/``
    directory in core. This regression test prevents the directory
    from being silently re-introduced.
    """
    adapters_dir = SRC_ROOT / "blocks" / "io" / "adapters"
    assert not adapters_dir.exists(), (
        f"{adapters_dir.relative_to(SRC_ROOT)} must not exist — the bundled "
        "adapter layer was deleted in T-TRK-004 (Phase 11). Plugin IO "
        "blocks subclass scistudio.blocks.io.io_block.IOBlock and register "
        "via the scistudio.blocks entry-point group per ADR-028 §D1/§D4."
    )


def test_no_domain_block_package_source_under_core_tree() -> None:
    """Core must ship no decoupled domain block package source (issue #1770).

    The imaging / lcms / spectroscopy / srs packages were decoupled into their
    own repositories. The core repo's importable source tree
    (``src/scistudio``) must therefore contain NO ``scistudio_blocks_*``
    package source. The only ``scistudio_blocks_*`` source permitted in the
    repo is the in-repo test fixture under
    ``tests/fixtures/scistudio-blocks-fixture/`` (a fake stand-in package that
    is never installed and is not part of the shipped ``scistudio``
    distribution). This regression test prevents a domain package from being
    silently re-vendored into core.
    """
    offenders = [
        str(path.relative_to(SRC_ROOT))
        for path in SRC_ROOT.rglob("scistudio_blocks_*")
        if path.is_dir() or path.suffix == ".py"
    ]
    assert not offenders, (
        "Decoupled domain block package source found under the core tree "
        f"src/scistudio (issue #1770): {offenders}. Domain packages live in "
        "their own repositories; the only permitted scistudio_blocks_* source "
        "is the test fixture under tests/fixtures/scistudio-blocks-fixture/."
    )


def test_adapter_registry_removed() -> None:
    """``blocks/io/adapter_registry.py`` must not exist (T-TRK-004).

    ADR-028 §D2 deletes the ``AdapterRegistry`` extension dispatch
    layer. Concrete core loaders (``LoadData`` / ``SaveData``) replace
    this in T-TRK-007 / T-TRK-008 with private ``_load_*`` / ``_save_*``
    dispatch functions, not a runtime registry. This regression test
    prevents the file from being silently re-introduced.
    """
    registry_path = SRC_ROOT / "blocks" / "io" / "adapter_registry.py"
    assert not registry_path.exists(), (
        f"{registry_path.relative_to(SRC_ROOT)} must not exist — the "
        "AdapterRegistry was deleted in T-TRK-004 (Phase 11). Replacement "
        "dispatch lives in LoadData/SaveData per ADR-028 §D1 + Addendum 1."
    )
