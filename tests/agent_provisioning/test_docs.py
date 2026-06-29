"""Tests for ``agent_provisioning.docs`` (#1850, ADR-052 §7).

The docs sub-step provisions the packaged user guide (with the self-contained
API reference) and the agent reference docs into a project.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.agent_provisioning import install_project_agent_assets
from scistudio.agent_provisioning.docs import write_docs

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
