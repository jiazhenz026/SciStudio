"""Tests for ``scieasy.qa.audit.skill_pointer_sync`` (ADR-044 §11)."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.skill_pointer_sync import (
    MAX_BODY_LINES,
    check,
    detect_skill_kind,
)
from scieasy.qa.schemas.report import Severity


def _write_skill(
    repo: Path,
    skill_name: str,
    *,
    kind: str | None = "procedural",
    target: str | None = "docs/contributing/workflows/new-feature.md",
    body_extra: str = "",
) -> Path:
    path = repo / ".claude/skills" / skill_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\nname: " + skill_name + "\n"
    fm += "description: x\n"
    if kind is not None:
        fm += f"kind: {kind}\n"
    fm += "---\n"
    body = (
        f"# {skill_name}\n\nFor canonical procedure, read: `{target}`\n"
        if target
        else f"# {skill_name}\n\nNo pointer.\n"
    )
    body += body_extra
    path.write_text(fm + body, encoding="utf-8")
    return path


def _write_workflow_doc(repo: Path, slug: str, *, related_skills: list[str] | None = None) -> Path:
    path = repo / "docs/contributing/workflows" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = f"---\nworkflow_id: {slug}\n"
    if related_skills:
        fm += "related_skills:\n"
        for s in related_skills:
            fm += f"  - {s}\n"
    fm += "---\n"
    path.write_text(fm + f"# {slug}\n\nbody\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# detect_skill_kind
# ---------------------------------------------------------------------------


class TestDetectKind:
    def test_valid_procedural(self) -> None:
        assert detect_skill_kind({"kind": "procedural"}) == "procedural"

    def test_valid_tool_wrapping(self) -> None:
        assert detect_skill_kind({"kind": "tool-wrapping"}) == "tool-wrapping"

    def test_valid_bootstrap(self) -> None:
        assert detect_skill_kind({"kind": "bootstrap-meta"}) == "bootstrap-meta"

    def test_invalid_kind(self) -> None:
        assert detect_skill_kind({"kind": "wrong"}) is None

    def test_missing_kind(self) -> None:
        assert detect_skill_kind({}) is None

    def test_non_string_kind(self) -> None:
        assert detect_skill_kind({"kind": 42}) is None


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_no_skills_dir(self, tmp_path: Path) -> None:
        assert check(tmp_path) == []

    def test_valid_procedural_skill_target_exists(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "new-feature")
        _write_skill(
            tmp_path,
            "new-feature",
            kind="procedural",
            target="docs/contributing/workflows/new-feature.md",
        )
        findings = check(tmp_path)
        # The only finding may be "workflow has no related_skills" — but
        # actually the workflow doc was created without related_skills entry.
        # That's a *workflow_sync*-level check, not skill_pointer_sync's
        # reverse closure. Reverse closure here just checks that ≥1 skill
        # points at the workflow — which IS the case.
        # So zero findings.
        assert findings == []

    def test_missing_kind_warning(self, tmp_path: Path) -> None:
        # speckit-style skill without kind field.
        _write_skill(
            tmp_path,
            "no-kind",
            kind=None,
            target="docs/contributing/workflows/new-feature.md",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.missing-kind" and f.severity == Severity.WARNING for f in findings)

    def test_missing_frontmatter_error(self, tmp_path: Path) -> None:
        path = tmp_path / ".claude/skills/bad/SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("no frontmatter\n", encoding="utf-8")
        findings = check(tmp_path)
        assert any(
            f.rule_id == "skill-pointer-sync.missing-frontmatter" and f.severity == Severity.ERROR for f in findings
        )

    def test_body_too_long_warning(self, tmp_path: Path) -> None:
        long_body = "extra line\n" * (MAX_BODY_LINES + 5)
        _write_skill(
            tmp_path,
            "long",
            kind="procedural",
            target="docs/contributing/workflows/new-feature.md",
            body_extra=long_body,
        )
        # Create the target so target_missing doesn't fire.
        _write_workflow_doc(tmp_path, "new-feature")
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.body-too-long" for f in findings)

    def test_procedural_duplication_warning(self, tmp_path: Path) -> None:
        body = "1. step one\n2. step two\n3. step three\n4. step four\n"
        _write_skill(
            tmp_path,
            "dup",
            kind="procedural",
            target="docs/contributing/workflows/new-feature.md",
            body_extra=body,
        )
        _write_workflow_doc(tmp_path, "new-feature")
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.procedural-duplication" for f in findings)

    def test_pointer_shape_wrong_error_procedural(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "bad-shape",
            kind="procedural",
            target="docs/wrong/place/foo.md",
        )
        findings = check(tmp_path)
        assert any(
            f.rule_id == "skill-pointer-sync.pointer-shape-wrong" and f.severity == Severity.ERROR for f in findings
        )

    def test_target_missing_info_procedural(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "missing-target",
            kind="procedural",
            target="docs/contributing/workflows/not-yet.md",
        )
        findings = check(tmp_path)
        # Will be either target-missing OR workflows-dir-absent (dormant).
        # If the workflows dir is absent (no workflow doc created), the
        # check returns the dormant marker for reverse closure but the
        # target-missing for the per-skill resolution.
        # In this test we did not create a workflow doc, so workflows
        # dir is absent → reverse closure is dormant; target-missing for
        # procedural fires because the pointed-at file doesn't exist.
        assert any(f.rule_id == "skill-pointer-sync.target-missing" for f in findings)

    def test_no_pointer_warning(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "no-pointer",
            kind="procedural",
            target=None,
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.no-pointer" for f in findings)

    def test_tool_wrapping_reference_target(self, tmp_path: Path) -> None:
        ref_path = tmp_path / "docs/contributing/reference/doc-drift.md"
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text("body\n", encoding="utf-8")
        _write_skill(
            tmp_path,
            "doc-drift",
            kind="tool-wrapping",
            target="docs/contributing/reference/doc-drift.md",
        )
        findings = check(tmp_path)
        # No errors — target exists.
        assert not any(f.rule_id == "skill-pointer-sync.pointer-shape-wrong" for f in findings)

    def test_tool_wrapping_module_target(self, tmp_path: Path) -> None:
        # Create the corresponding src file.
        module_file = tmp_path / "src/scieasy/qa/audit/foo.py"
        module_file.parent.mkdir(parents=True, exist_ok=True)
        module_file.write_text("pass\n", encoding="utf-8")
        _write_skill(
            tmp_path,
            "foo-skill",
            kind="tool-wrapping",
            target="scieasy.qa.audit.foo",
        )
        findings = check(tmp_path)
        assert not any(f.rule_id == "skill-pointer-sync.pointer-shape-wrong" for f in findings)
        assert not any(f.rule_id == "skill-pointer-sync.target-missing" for f in findings)

    def test_tool_wrapping_module_target_missing(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "ghost",
            kind="tool-wrapping",
            target="scieasy.qa.audit.nowhere",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.target-missing" for f in findings)

    def test_tool_wrapping_invalid_shape(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "bad",
            kind="tool-wrapping",
            target="foo/bar.md",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.pointer-shape-wrong" for f in findings)

    def test_bootstrap_meta_target_shape(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "speckit-foo",
            kind="bootstrap-meta",
            target="docs/doc-guide/speckit.md",
        )
        findings = check(tmp_path)
        # No shape error, but target-missing INFO since doc-guide is absent.
        assert not any(f.rule_id == "skill-pointer-sync.pointer-shape-wrong" for f in findings)
        assert any(f.rule_id == "skill-pointer-sync.target-missing" for f in findings)

    def test_bootstrap_meta_invalid_shape(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "bad-bootstrap",
            kind="bootstrap-meta",
            target="docs/wrong/place.md",
        )
        findings = check(tmp_path)
        assert any(f.rule_id == "skill-pointer-sync.pointer-shape-wrong" for f in findings)

    def test_workflows_dir_absent_dormant(self, tmp_path: Path) -> None:
        # No workflow docs created at all.
        _write_skill(
            tmp_path,
            "x",
            kind="bootstrap-meta",
            target="docs/doc-guide/x.md",
        )
        findings = check(tmp_path)
        assert any(
            f.rule_id == "skill-pointer-sync.workflows-dir-absent" and f.severity == Severity.INFO for f in findings
        )

    def test_workflow_unreferenced_error(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "lonely")
        # No skill points at "lonely".
        # Need a skill to anchor the workflows dir exists.
        _write_skill(
            tmp_path,
            "other",
            kind="procedural",
            target="docs/contributing/workflows/other.md",
        )
        _write_workflow_doc(tmp_path, "other")
        findings = check(tmp_path)
        assert any(
            f.rule_id == "skill-pointer-sync.workflow-unreferenced"
            and f.file == "docs/contributing/workflows/lonely.md"
            for f in findings
        )
