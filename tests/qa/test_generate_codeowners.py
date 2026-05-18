"""Tests for the CODEOWNERS generator (TC-1C.4).

Covers:
  - Idempotent regeneration from ``.governance-paths.yaml``.
  - Block-replacement semantics (preserve content outside markers).
  - Error paths (corrupted markers).
  - The actual on-disk ``.github/CODEOWNERS`` file is consistent with
    the current ``.governance-paths.yaml``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS_PATH = REPO_ROOT / ".github" / "CODEOWNERS"


def _load_generator():
    """Import the generator script as a module."""
    spec = importlib.util.spec_from_file_location(
        "_generate_codeowners",
        REPO_ROOT / "scripts" / "audit" / "generate_codeowners.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_generate_codeowners", module)
    spec.loader.exec_module(module)
    return module


def test_codeowners_exists() -> None:
    """``.github/CODEOWNERS`` must exist after Phase 1C."""
    assert CODEOWNERS_PATH.exists(), f"missing {CODEOWNERS_PATH}"


def test_codeowners_has_auto_block() -> None:
    """The on-disk CODEOWNERS has the auto-generated markers."""
    text = CODEOWNERS_PATH.read_text(encoding="utf-8")
    assert "# BEGIN auto-generated from .governance-paths.yaml" in text
    assert "# END auto-generated from .governance-paths.yaml" in text


def test_codeowners_check_passes() -> None:
    """``--check`` returns 0: the on-disk file is already up to date."""
    gen = _load_generator()
    expected = gen.generate(repo_root=REPO_ROOT)
    actual = CODEOWNERS_PATH.read_text(encoding="utf-8")
    assert actual == expected, "CODEOWNERS is stale — regenerate"


def test_generate_is_idempotent(tmp_path: Path) -> None:
    """Two consecutive generate() calls produce identical output."""
    gen = _load_generator()
    out = tmp_path / "fake-repo"
    (out / ".github").mkdir(parents=True)
    # Copy the real .governance-paths.yaml so we have a known input.
    (out / ".governance-paths.yaml").write_text(
        (REPO_ROOT / ".governance-paths.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    a = gen.generate(repo_root=out)
    (out / ".github" / "CODEOWNERS").write_text(a, encoding="utf-8")
    b = gen.generate(repo_root=out)
    assert a == b, "second generate() differs from first"


def test_block_markers_present_in_output(tmp_path: Path) -> None:
    """Rendered block always carries BEGIN/END markers."""
    gen = _load_generator()
    paths = ["docs/adr/**", "AGENTS.md"]
    block = gen.render_codeowners_block(paths)
    assert block.startswith("# BEGIN auto-generated from .governance-paths.yaml")
    assert block.rsplit("\n", 1)[0] + "\n" == "# END auto-generated from .governance-paths.yaml\n" or block.endswith(
        "# END auto-generated from .governance-paths.yaml\n"
    )
    assert "docs/adr/**" in block
    assert "AGENTS.md" in block


def test_splice_preserves_content_outside_markers() -> None:
    """``_splice_block`` does not modify bytes outside the auto block."""
    gen = _load_generator()
    existing = (
        "# Custom default rule\n"
        "* @some-owner\n"
        "\n"
        "# BEGIN auto-generated from .governance-paths.yaml\n"
        "old line\n"
        "# END auto-generated from .governance-paths.yaml\n"
        "\n"
        "# Manual trailing rule\n"
        "extra/** @other\n"
    )
    new_block = gen.render_codeowners_block(["new/path/**"])
    spliced = gen._splice_block(existing, new_block)
    assert spliced.startswith("# Custom default rule\n* @some-owner\n\n")
    assert spliced.endswith("# Manual trailing rule\nextra/** @other\n")
    assert "old line" not in spliced
    assert "new/path/**" in spliced


def test_splice_appends_when_markers_absent() -> None:
    """First run appends the block to a file lacking markers."""
    gen = _load_generator()
    existing = "* @some-owner\n"
    new_block = gen.render_codeowners_block(["docs/adr/**"])
    spliced = gen._splice_block(existing, new_block)
    assert spliced.startswith("* @some-owner\n")
    assert "# BEGIN auto-generated from .governance-paths.yaml" in spliced
    assert "docs/adr/**" in spliced


def test_splice_rejects_single_marker() -> None:
    """File with only a BEGIN (or only an END) marker is an error."""
    gen = _load_generator()
    bad_begin_only = "* @owner\n# BEGIN auto-generated from .governance-paths.yaml\nline\n"
    bad_end_only = "* @owner\n# END auto-generated from .governance-paths.yaml\nline\n"
    new_block = gen.render_codeowners_block(["x/**"])
    with pytest.raises(ValueError):
        gen._splice_block(bad_begin_only, new_block)
    with pytest.raises(ValueError):
        gen._splice_block(bad_end_only, new_block)


def test_splice_rejects_reversed_markers() -> None:
    """END appearing before BEGIN is structural corruption — refuse to splice."""
    gen = _load_generator()
    reversed_markers = (
        "# END auto-generated from .governance-paths.yaml\nline\n# BEGIN auto-generated from .governance-paths.yaml\n"
    )
    new_block = gen.render_codeowners_block(["x/**"])
    with pytest.raises(ValueError):
        gen._splice_block(reversed_markers, new_block)


def test_generate_from_real_inputs() -> None:
    """The generator runs end-to-end against the real repo files."""
    gen = _load_generator()
    out = gen.generate(repo_root=REPO_ROOT)
    assert "# BEGIN auto-generated from .governance-paths.yaml" in out
    # Per ADR-043 §3.2 example, ADR/spec dirs are governance.
    assert "docs/adr/**" in out
    assert "MAINTAINERS" in out
    assert "@jiazhenz026" in out


def test_check_mode_returns_zero_when_clean() -> None:
    """``--check`` mode returns 0 when CODEOWNERS matches the generator output."""
    gen = _load_generator()
    exit_code = gen.main(["--repo-root", str(REPO_ROOT), "--check"])
    assert exit_code == 0


def test_column_align_pads_short_path() -> None:
    """Short paths get padded to the column width."""
    gen = _load_generator()
    line = gen._column_align("docs/adr/**", "@owner")
    assert line.startswith("docs/adr/**")
    assert line.endswith("@owner")
    # Padding should align to default width=50.
    assert len(line) >= 50


def test_column_align_falls_back_to_min_pad() -> None:
    """Long paths fall back to a minimum padding rather than negative width."""
    gen = _load_generator()
    long_path = "a/very/long/path/that/exceeds/the/default/column/width/**"
    line = gen._column_align(long_path, "@owner")
    assert "@owner" in line
    # Should have at least 4 spaces between path and owner.
    assert "    @owner" in line or "    @owner" in line
