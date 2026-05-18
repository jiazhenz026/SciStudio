"""Tests for ``scieasy.agent_provisioning.qa_skills`` (Phase 1H sub-PR 3).

References
----------
ADR-042 §17.3 — cross-runtime installer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scieasy.agent_provisioning import qa_skills


def _write_manifest(path: Path, names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"skills": [{"name": n, "priority": "P0", "kind": "tool-wrapping"} for n in names]}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Manifest reader
# ---------------------------------------------------------------------------


def test_list_required_skills_reads_yaml(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    _write_manifest(manifest, ["a", "b", "c"])
    assert qa_skills.list_required_skills(manifest) == ["a", "b", "c"]


def test_list_required_skills_missing_returns_empty(tmp_path: Path) -> None:
    assert qa_skills.list_required_skills(tmp_path / "missing.yaml") == []


def test_list_required_skills_handles_string_entries(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"skills": ["only-string"]}), encoding="utf-8")
    assert qa_skills.list_required_skills(manifest) == ["only-string"]


def test_list_required_skills_skips_malformed(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump({"skills": [{"name": "good"}, {"no_name_key": "x"}, 42]}),
        encoding="utf-8",
    )
    assert qa_skills.list_required_skills(manifest) == ["good"]


def test_list_required_skills_handles_non_list_root(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"skills": "not-a-list"}), encoding="utf-8")
    assert qa_skills.list_required_skills(manifest) == []


# ---------------------------------------------------------------------------
# install_qa_skills — happy path
# ---------------------------------------------------------------------------


def test_install_writes_to_claude_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, ["alpha", "beta"])

    # The real `_read_skill_body` walks from the installed package location;
    # in tests we need to redirect it to our fixture source bodies.
    bodies = {
        "alpha": "---\nname: alpha\n---\nbody-alpha\n",
        "beta": "---\nname: beta\n---\nbody-beta\n",
    }
    monkeypatch.setattr(qa_skills, "_read_skill_body", lambda name: bodies[name])

    written = qa_skills.install_qa_skills(tmp_path, manifest_path=manifest)
    assert sorted(written) == [
        ".claude/skills/alpha/SKILL.md",
        ".claude/skills/beta/SKILL.md",
    ]
    assert (tmp_path / ".claude" / "skills" / "alpha" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "---\nname: alpha\n---\nbody-alpha\n"


def test_install_is_idempotent_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, ["one"])
    monkeypatch.setattr(qa_skills, "_read_skill_body", lambda _name: "---\nname: one\n---\noriginal\n")
    first = qa_skills.install_qa_skills(tmp_path, manifest_path=manifest)
    assert first == [".claude/skills/one/SKILL.md"]

    # Mutate the installed file to a customised version.
    (tmp_path / ".claude" / "skills" / "one" / "SKILL.md").write_text("customised\n", encoding="utf-8")
    second = qa_skills.install_qa_skills(tmp_path, manifest_path=manifest)
    assert second == []  # nothing rewritten without force
    assert (tmp_path / ".claude" / "skills" / "one" / "SKILL.md").read_text(encoding="utf-8") == "customised\n"


def test_install_force_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, ["one"])
    monkeypatch.setattr(qa_skills, "_read_skill_body", lambda _name: "---\nname: one\n---\noriginal\n")
    qa_skills.install_qa_skills(tmp_path, manifest_path=manifest)
    (tmp_path / ".claude" / "skills" / "one" / "SKILL.md").write_text("customised\n", encoding="utf-8")

    written = qa_skills.install_qa_skills(tmp_path, manifest_path=manifest, force=True)
    assert written == [".claude/skills/one/SKILL.md"]
    assert (tmp_path / ".claude" / "skills" / "one" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "---\nname: one\n---\noriginal\n"


def test_install_falls_back_to_placeholder_when_source_missing(tmp_path: Path) -> None:
    # When no source SKILL.md is resolvable, a placeholder body is written
    # so installer runs are idempotent against partial source trees.
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, ["totally-nonexistent-skill-name-xyz"])
    written = qa_skills.install_qa_skills(tmp_path, manifest_path=manifest)
    assert written == [".claude/skills/totally-nonexistent-skill-name-xyz/SKILL.md"]
    body = (tmp_path / ".claude" / "skills" / "totally-nonexistent-skill-name-xyz" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "source body missing" in body


def test_install_with_explicit_runtimes_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, ["x"])
    monkeypatch.setattr(qa_skills, "_read_skill_body", lambda _name: "---\nname: x\n---\nbody-x\n")
    # An unknown runtime is silently ignored (forward-compat for sub-PR 2).
    written = qa_skills.install_qa_skills(
        tmp_path,
        manifest_path=manifest,
        runtimes=["claude", "codex-future"],
    )
    assert written == [".claude/skills/x/SKILL.md"]


def test_install_empty_manifest_returns_empty(tmp_path: Path) -> None:
    manifest = tmp_path / "docs" / "skills" / "required.yaml"
    _write_manifest(manifest, [])
    assert qa_skills.install_qa_skills(tmp_path, manifest_path=manifest) == []


# ---------------------------------------------------------------------------
# End-to-end roundtrip with the real repo manifest
# ---------------------------------------------------------------------------


def test_real_repo_manifest_resolves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install the real 11-skill manifest into a temp project and confirm all 11 land."""
    here = Path(__file__).resolve()
    repo_root = next(p for p in here.parents if (p / "pyproject.toml").is_file())
    src_manifest = repo_root / "docs" / "skills" / "required.yaml"
    if not src_manifest.is_file():
        pytest.skip("real manifest not present in this fixture")

    # Copy the real manifest into a sandbox project so the installer's
    # default-manifest lookup hits OUR sandbox path.
    dst_manifest = tmp_path / "docs" / "skills" / "required.yaml"
    dst_manifest.parent.mkdir(parents=True)
    dst_manifest.write_text(src_manifest.read_text(encoding="utf-8"), encoding="utf-8")

    # Bodies come from importlib.resources lookup against the live package,
    # so we don't need to copy the source SKILL.md files into tmp_path.
    written = qa_skills.install_qa_skills(tmp_path)
    assert len(written) == 11
    for rel in written:
        body = (tmp_path / rel).read_text(encoding="utf-8")
        assert body.startswith("---\n")
        # Real bodies must not be placeholders.
        assert "source body missing" not in body
