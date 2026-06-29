"""Tests for ``agent_provisioning.docs`` (#1850, ADR-052 §7).

The docs sub-step provisions the packaged user guide (with the self-contained
API reference) and the agent reference docs into a project.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.agent_provisioning import install_project_agent_assets
from scistudio.agent_provisioning.docs import write_docs, write_package_docs

# Landing files that must exist after provisioning.
_USER_GUIDE_LANDERS = (
    "user-guide/README.md",
    "user-guide/getting-started.md",
    "user-guide/api-reference/index.md",
)
_AGENT_REF_LANDERS = (
    ".scistudio/agent-reference/README.md",
    ".scistudio/agent-reference/public-api.md",
    ".scistudio/agent-reference/block-contract.md",
    ".scistudio/agent-reference/workflow-schema.md",
    ".scistudio/agent-reference/plot-contract.md",
)


def _write_installed_package_docs(
    packages_root: Path,
    *,
    module_name: str,
    flat: bool = False,
    version: str = "0.1.0",
) -> Path:
    install_dir = packages_root / f"{module_name.replace('_', '-')}-{version}"
    module_dir = install_dir / module_name if flat else install_dir / "src" / module_name
    docs_dir = module_dir / "_scistudio_docs"
    (docs_dir / "agent-reference").mkdir(parents=True)
    (docs_dir / "api-reference").mkdir(parents=True)
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (docs_dir / "manifest.json").write_text(
        (f'{{\n  "package_name": "{module_name.replace("_", " ").title()}",\n  "version": "{version}"\n}}\n'),
        encoding="utf-8",
    )
    (docs_dir / "agent-reference" / "README.md").write_text(
        f"# Agent docs for {module_name}\n",
        encoding="utf-8",
    )
    (docs_dir / "api-reference" / "index.md").write_text(
        f"# API reference for {module_name} {version}\n",
        encoding="utf-8",
    )
    return install_dir


def test_write_docs_provisions_both_trees(tmp_project_dir: Path) -> None:
    written = write_docs(tmp_project_dir, force=False)
    assert written, "expected docs to be written"

    for rel in (*_USER_GUIDE_LANDERS, *_AGENT_REF_LANDERS):
        assert (tmp_project_dir / rel).is_file(), f"missing provisioned doc: {rel}"


def test_write_docs_includes_api_reference_pages(tmp_project_dir: Path) -> None:
    """The self-contained API reference (not just the index) is provisioned."""
    write_docs(tmp_project_dir, force=False)
    ref_dir = tmp_project_dir / "user-guide" / "api-reference"
    pages = list(ref_dir.glob("scistudio.*.md"))
    assert pages, "expected per-root API reference pages"
    # Self-contained: a real signature/heading, not an mkdocstrings directive.
    base = (ref_dir / "scistudio.blocks.base.md").read_text(encoding="utf-8")
    assert "::: scistudio" not in base, "API reference must be self-contained, not directive shells"
    assert "InputPort" in base


def test_write_docs_provisions_installed_package_reference(tmp_project_dir: Path, tmp_path: Path) -> None:
    packages_root = tmp_path / "packages"
    _write_installed_package_docs(packages_root, module_name="scistudio_blocks_probe")

    written = write_docs(tmp_project_dir, force=False, package_dirs=[packages_root])

    agent_root = tmp_project_dir / ".scistudio" / "agent-reference"
    hidden_package = agent_root / "packages" / "scistudio-blocks-probe"
    user_package = tmp_project_dir / "user-guide" / "package-reference" / "scistudio-blocks-probe"
    assert (hidden_package / "README.md").is_file()
    assert (hidden_package / "api-reference" / "index.md").is_file()
    assert (user_package / "api-reference" / "index.md").is_file()
    assert ".scistudio/agent-reference/package-index.md" in written
    assert "Scistudio Blocks Probe" in (agent_root / "package-index.md").read_text(encoding="utf-8")
    assert "scistudio-blocks-probe/api-reference/index.md" in (
        tmp_project_dir / "user-guide" / "package-reference" / "index.md"
    ).read_text(encoding="utf-8")


def test_write_package_docs_discovers_flat_wheel_layout(tmp_project_dir: Path, tmp_path: Path) -> None:
    packages_root = tmp_path / "packages"
    _write_installed_package_docs(
        packages_root,
        module_name="scistudio_blocks_wheelprobe",
        flat=True,
        version="0.2.0",
    )

    write_package_docs(tmp_project_dir, package_dirs=[packages_root])

    assert (
        tmp_project_dir
        / ".scistudio"
        / "agent-reference"
        / "packages"
        / "scistudio-blocks-wheelprobe"
        / "api-reference"
        / "index.md"
    ).is_file()


def test_write_package_docs_refreshes_changed_package_reference(tmp_project_dir: Path, tmp_path: Path) -> None:
    packages_root = tmp_path / "packages"
    _write_installed_package_docs(packages_root, module_name="scistudio_blocks_refresh", version="0.1.0")
    write_package_docs(tmp_project_dir, package_dirs=[packages_root])

    source_index = (
        packages_root
        / "scistudio-blocks-refresh-0.1.0"
        / "src"
        / "scistudio_blocks_refresh"
        / "_scistudio_docs"
        / "api-reference"
        / "index.md"
    )
    source_index.write_text("# API reference for refreshed package\n", encoding="utf-8")

    written = write_package_docs(tmp_project_dir, package_dirs=[packages_root])

    target_index = (
        tmp_project_dir / "user-guide" / "package-reference" / "scistudio-blocks-refresh" / "api-reference" / "index.md"
    )
    assert "user-guide/package-reference/scistudio-blocks-refresh/api-reference/index.md" in written
    assert target_index.read_text(encoding="utf-8") == "# API reference for refreshed package\n"


def test_write_docs_idempotent_preserves_edits(tmp_project_dir: Path) -> None:
    write_docs(tmp_project_dir, force=False)
    edited = tmp_project_dir / "user-guide" / "README.md"
    edited.write_text("# user edit\n", encoding="utf-8")

    written = write_docs(tmp_project_dir, force=False)
    assert "user-guide/README.md" not in written
    assert edited.read_text(encoding="utf-8") == "# user edit\n"


def test_write_docs_force_overwrites(tmp_project_dir: Path) -> None:
    write_docs(tmp_project_dir, force=False)
    target = tmp_project_dir / "user-guide" / "README.md"
    target.write_text("# garbage\n", encoding="utf-8")

    write_docs(tmp_project_dir, force=True)
    assert "garbage" not in target.read_text(encoding="utf-8")


def test_orchestrator_runs_docs_substep(tmp_project_dir: Path) -> None:
    """install_project_agent_assets provisions the docs alongside skills/hooks."""
    result = install_project_agent_assets(tmp_project_dir, force=False)
    assert "user-guide/README.md" in result.written
    assert ".scistudio/agent-reference/public-api.md" in result.written
    assert (tmp_project_dir / "user-guide" / "api-reference" / "index.md").is_file()
