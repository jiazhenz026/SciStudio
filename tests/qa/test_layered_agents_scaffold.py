from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

AGENTS_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "src/scieasy/core/AGENTS.md",
    ROOT / "src/scieasy/blocks/AGENTS.md",
    ROOT / "src/scieasy/blocks/ai/AGENTS.md",
    ROOT / "src/scieasy/qa/AGENTS.md",
    ROOT / "frontend/AGENTS.md",
    ROOT / ".workflow/AGENTS.md",
    ROOT / "docs/AGENTS.md",
    ROOT / ".github/AGENTS.md",
]

REQUIRED_SECTIONS = [
    "## Identity",
    "## Policy",
    "## Routing",
    "## Data classification",
    "## Assessment rubric",
    "## Paths",
]

NEW_SKILLS = [
    "workflow-gate",
    "hotfix-mode",
    "bug-fix-workflow",
    "speckit-feature",
    "agent-manager",
    "dispatch-agents",
    "test-author",
    "doc-drift-guard",
    "provenance-tagger",
    "adr-router",
    "pr-maintainer",
    "mantis-proof",
    "session-logs",
    "release-maintainer",
    "scieasy-skill-creator",
    "codemod-with-adr",
    "hallucination-guard",
    "maintainers-reverse",
]

HOOKS = [
    "branch-before-edit.sh",
    "pytest-timeout-injection.sh",
    "block-npm-run-dev.sh",
    "trailer-validation.sh",
    "governance-mod-guard.sh",
    "codex-review-reconcile-cap.sh",
    "tracking-branch-verify.sh",
    "instructions-loaded-audit.sh",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter_body(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    _, _, rest = text.partition("---\n")
    _, _, body = rest.partition("---\n")
    return body


def test_agents_files_have_required_sections_in_order() -> None:
    for path in AGENTS_FILES:
        text = _text(path)
        offsets = [text.index(section) for section in REQUIRED_SECTIONS]
        assert offsets == sorted(offsets), path
        assert "✅" in text and "⚠️" in text and "🚫" in text, path
        assert text.count("|") >= 18, path

    assert "## Out-of-scope" in _text(ROOT / "AGENTS.md")
    assert len(_text(ROOT / "AGENTS.md").splitlines()) <= 200


def test_pointer_skills_are_short_and_mark_deferred_targets() -> None:
    for name in NEW_SKILLS:
        path = ROOT / ".claude/skills" / name / "SKILL.md"
        text = _text(path)
        body_lines = _frontmatter_body(text).splitlines()
        assert len(body_lines) <= 30, path
        assert "Canonical target:" in text, path
        assert "TODO(#1113)" in text, path
        assert "When uncertain, prefer no edit with explanation." in text, path


def test_rule_and_hook_scaffolds_record_deferred_activation() -> None:
    for path in (ROOT / ".claude/rules").glob("*.md"):
        text = _text(path)
        assert "paths:" in text, path
        assert "TODO(#1113)" in text, path

    for name in HOOKS:
        path = ROOT / "scripts/hooks" / name
        text = _text(path)
        assert text.startswith("#!/usr/bin/env bash"), path
        assert "TODO(#1113)" in text, path


def test_runtime_pointer_files_exist() -> None:
    assert _text(ROOT / "CURSOR.md").strip() == "@include AGENTS.md"
    assert _text(ROOT / "GEMINI.md").strip() == "@include AGENTS.md"
    assert _text(ROOT / ".aiderrc").strip() == "system: AGENTS.md"
