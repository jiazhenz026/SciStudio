"""ADR-048 SPEC 3 docs guardrails for ``docs/block-development/**``.

Two classes of check (spec FR-006 / FR-026 / SC-001, User Story 5):

1. **Stale-phrase checks** — assert the rewritten developer docs, the scaffold
   templates, and the inspect-data skill no longer carry the known-stale
   patterns the rewrite removed:

   * ``produced_type=`` — ``OutputPort`` has no ``produced_type`` field.
   * label-only plot binding — plots bind by node id + output port, never label.
   * hardcoded image preview in core — the rich image viewer is package-owned.
   * old ``preview_data(ref, max_rows=..., max_dim=...)`` argument examples.

2. **Link checks** — every relative markdown link out of the block-development
   docs (and the ADR-048 spec/skill/README/template links the rewrite added)
   resolves to a real file in the repo.

The tests intentionally allow the *documentation of* stale patterns: pages may
mention a stale token inside an explicit "do not write this" warning, so the
stale-phrase scan keys on the *invalid usage form*, not the bare token.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/docs/test_block_development_docs.py -> repo root is parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCK_DEV = REPO_ROOT / "docs" / "block-development"
PREVIEWERS_AND_PLOTS = BLOCK_DEV / "previewers-and-plots.md"
IMPACT_MATRIX = REPO_ROOT / "docs" / "planning" / "adr-048-impact-matrix.md"
INSPECT_SKILL = REPO_ROOT / "src" / "scistudio" / "_skills" / "scistudio" / "scistudio-inspect-data" / "SKILL.md"
SKILL_ROOT = REPO_ROOT / "src" / "scistudio" / "_skills"
SCAFFOLD_TEMPLATES = REPO_ROOT / "src" / "scistudio" / "cli" / "templates" / "block_package"


def _block_dev_pages() -> list[Path]:
    return sorted(BLOCK_DEV.glob("*.md"))


def _iter_doc_files() -> list[Path]:
    files = list(BLOCK_DEV.glob("*.md"))
    files.append(IMPACT_MATRIX)
    return files


# ---------------------------------------------------------------------------
# 1. Stale-phrase checks (SC-001 / User Story 5)
# ---------------------------------------------------------------------------


def test_new_previewers_and_plots_page_exists() -> None:
    """FR-012: the ADR-048 previewer-and-plot author guide must exist."""
    assert PREVIEWERS_AND_PLOTS.is_file(), "docs/block-development/previewers-and-plots.md is missing"


def test_impact_matrix_exists_and_covers_range() -> None:
    """FR-029 / SC-010: the recent-ADR impact matrix exists and spans ADR-036..048."""
    assert IMPACT_MATRIX.is_file(), "docs/planning/adr-048-impact-matrix.md is missing"
    text = IMPACT_MATRIX.read_text(encoding="utf-8")
    for adr in ("ADR-036", "ADR-041", "ADR-043", "ADR-044", "ADR-047", "ADR-048"):
        assert adr in text, f"impact matrix does not reference {adr}"


# Invalid usage form: ``produced_type`` used as a keyword/field assignment.
_PRODUCED_TYPE_USAGE = re.compile(r"produced_type\s*=")
# Old preview_data signature with the removed bounding arguments.
_OLD_PREVIEW_ARGS = re.compile(r"preview_data\([^)]*\b(max_rows|max_dim)\b")
# Any documented call to preview_data must include the required fmt argument.
_PREVIEW_DATA_CALL = re.compile(r"preview_data\(([^)]*)\)")
# Old get_block_output names from ADR-033-era prose.
_OLD_GET_BLOCK_OUTPUT_ARGS = re.compile(r"get_block_output\([^)]*\b(node_id|port_name)\b")
# Editable installs are forbidden in active packaged guidance.
_FORBIDDEN_EDITABLE_INSTALL = re.compile(
    r"\b(?:uv\s+pip\s+install|python\s+-m\s+pip\s+install|pip\s+install)[^\n`]*\s-e(?:\s|$)",
    re.IGNORECASE,
)
_ENTRY_POINT_BLOCK = re.compile(
    r'\[project\.entry-points\."(?P<group>scistudio\.(?:blocks|types|previewers))"\]\s*\n'
    r"(?P<body>(?:\s*[A-Za-z0-9_.-]+\s*=\s*\"[^\"]+\"\s*\n?)+)",
    re.MULTILINE,
)
_ENTRY_POINT_LINE = re.compile(r'^\s*(?P<name>[A-Za-z0-9_.-]+)\s*=\s*"(?P<ref>[^"]+)"\s*$', re.MULTILINE)


def _packaged_guidance_files() -> list[Path]:
    skill_files = sorted(SKILL_ROOT.rglob("*.md"))
    template_files = sorted(
        path for path in SCAFFOLD_TEMPLATES.rglob("*") if path.is_file() and path.suffix in {".md", ".tpl", ".toml"}
    )
    return skill_files + template_files


def _contract_guidance_files() -> list[Path]:
    return _block_dev_pages() + _packaged_guidance_files()


@pytest.mark.parametrize("page", _block_dev_pages(), ids=lambda p: p.name)
def test_no_produced_type_usage_in_docs(page: Path) -> None:
    """FR-006 / SC-001: no doc/example uses ``OutputPort(..., produced_type=...)``."""
    text = page.read_text(encoding="utf-8")
    matches = _PRODUCED_TYPE_USAGE.findall(text)
    assert not matches, f"{page.name} still uses produced_type= (OutputPort has no such field)"


def test_no_produced_type_usage_in_scaffold_templates() -> None:
    """FR-017: the package scaffold templates must not emit produced_type=."""
    offenders = []
    for tpl in SCAFFOLD_TEMPLATES.glob("*.tpl"):
        if _PRODUCED_TYPE_USAGE.search(tpl.read_text(encoding="utf-8")):
            offenders.append(tpl.name)
    assert not offenders, f"scaffold templates still emit produced_type=: {offenders}"


def test_examples_have_no_produced_type() -> None:
    """FR-016: regenerated examples must not carry the stale field."""
    examples_dir = BLOCK_DEV / "examples"
    offenders = []
    for py in examples_dir.rglob("*.py"):
        if _PRODUCED_TYPE_USAGE.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py.relative_to(BLOCK_DEV)))
    assert not offenders, f"examples still use produced_type=: {offenders}"


def test_inspect_skill_has_no_stale_preview_args() -> None:
    """FR-021: the inspect-data skill must not teach max_rows/max_dim preview args."""
    text = INSPECT_SKILL.read_text(encoding="utf-8")
    assert not _OLD_PREVIEW_ARGS.search(text), "scistudio-inspect-data still teaches stale preview_data args"
    # The current signature must be present.
    assert "preview_data(ref, fmt)" in text, "inspect-data skill must document preview_data(ref, fmt)"


@pytest.mark.parametrize("doc", _contract_guidance_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_preview_data_examples_include_required_fmt(doc: Path) -> None:
    """FR-021: active skill/template examples must call ``preview_data`` with ``fmt``."""
    text = doc.read_text(encoding="utf-8")
    offenders = [match.group(0) for match in _PREVIEW_DATA_CALL.finditer(text) if "fmt" not in match.group(1)]
    assert not offenders, f"{doc.relative_to(REPO_ROOT)} has preview_data calls missing fmt: {offenders}"


@pytest.mark.parametrize("doc", _contract_guidance_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_get_block_output_examples_use_current_parameters(doc: Path) -> None:
    """Active docs must use ``get_block_output(run_id, block_id, port)``."""
    text = doc.read_text(encoding="utf-8")
    match = _OLD_GET_BLOCK_OUTPUT_ARGS.search(text)
    assert match is None, f"{doc.relative_to(REPO_ROOT)} uses stale get_block_output parameter {match.group(1)!r}"


def test_inspect_skill_documents_get_block_output_envelope() -> None:
    """The inspect-data skill must document the return envelope fields agents consume."""
    text = INSPECT_SKILL.read_text(encoding="utf-8")
    assert "get_block_output(run_id, block_id, port)" in text
    assert "GetBlockOutputResult" in text
    for field in ("`ref`", "`type`", "`produced_at`"):
        assert field in text, f"inspect-data skill does not document get_block_output envelope field {field}"


@pytest.mark.parametrize("doc", _packaged_guidance_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_packaged_guidance_has_no_editable_install_commands(doc: Path) -> None:
    """Active packaged skills/templates must not teach editable installs."""
    text = doc.read_text(encoding="utf-8")
    assert not _FORBIDDEN_EDITABLE_INSTALL.search(text), f"{doc.relative_to(REPO_ROOT)} teaches editable install"


@pytest.mark.parametrize("doc", _contract_guidance_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_entry_point_examples_use_callable_factories(doc: Path) -> None:
    """Entry-point examples must name callable factories, not module-only refs."""
    text = doc.read_text(encoding="utf-8")
    offenders: list[str] = []
    for block in _ENTRY_POINT_BLOCK.finditer(text):
        for line in _ENTRY_POINT_LINE.finditer(block.group("body")):
            ref = line.group("ref")
            if ":" not in ref or not ref.rsplit(":", 1)[1]:
                offenders.append(f'{line.group("name")} = "{ref}"')
    assert not offenders, f"{doc.relative_to(REPO_ROOT)} has module-only entry points: {offenders}"


def test_previewers_and_plots_states_preview_only_rule() -> None:
    """FR-015: plot jobs are preview-side artifacts, never workflow blocks/DAG nodes."""
    text = PREVIEWERS_AND_PLOTS.read_text(encoding="utf-8").lower()
    assert "preview-only" in text
    assert "node id" in text and "output port" in text  # bind by stable id, not label
    assert "lineage" in text


def test_publishing_teaches_three_entry_points() -> None:
    """FR-009 / SC-003: publishing distinguishes the three entry-point groups."""
    text = (BLOCK_DEV / "publishing.md").read_text(encoding="utf-8")
    for ep in ("scistudio.blocks", "scistudio.types", "scistudio.previewers"):
        assert ep in text, f"publishing.md does not document {ep}"


# ---------------------------------------------------------------------------
# 2. Link checks (FR-026 / SC-007)
# ---------------------------------------------------------------------------

# Matches markdown links [text](target). Skips images and inline anchors.
_LINK_RE = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)")


@pytest.mark.parametrize("doc", _iter_doc_files(), ids=lambda p: p.name)
def test_relative_links_resolve(doc: Path) -> None:
    """Every relative markdown link out of these docs resolves to a real file."""
    text = doc.read_text(encoding="utf-8")
    broken: list[str] = []
    for raw in _LINK_RE.findall(text):
        target = raw.strip()
        # Skip external + pure-anchor links.
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Strip any in-page anchor fragment.
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        # Only treat it as a file link when it looks like a relative path.
        # This avoids false positives from prose such as ``Collection[Image](length=1)``
        # that the markdown-link regex would otherwise capture.
        if "=" in path_part or " " in path_part:
            continue
        if not (path_part.startswith((".", "/")) or "/" in path_part or path_part.endswith((".md", ".py"))):
            continue
        resolved = (doc.parent / path_part).resolve()
        if not resolved.exists():
            broken.append(f"{target} -> {resolved}")
    assert not broken, f"{doc.name} has broken relative links:\n  " + "\n  ".join(broken)
