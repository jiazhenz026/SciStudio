"""Tests for #786 — slash command discovery endpoint.

The endpoint walks 4 known roots:
* ``~/.claude/commands/*.md``
* ``~/.claude/skills/<name>/SKILL.md`` (or ``skill.md``)
* ``<project>/.claude/commands/*.md``
* ``~/.claude/plugins/*/commands/*.md``

These tests fake ``Path.home()`` to a tmp dir so we can populate
each source deterministically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.api.app import create_app


@pytest.fixture
def app() -> Any:
    return create_app()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_slash_commands_lists_all_four_sources(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    fake_project = tmp_path / "project"
    fake_home.mkdir()
    fake_project.mkdir()

    # 1. ~/.claude/commands/*.md
    _write(
        fake_home / ".claude" / "commands" / "user_hello.md",
        "---\ndescription: Say hi to user\n---\nbody",
    )
    # 2. ~/.claude/skills/<name>/SKILL.md  +  another with lowercase skill.md
    _write(
        fake_home / ".claude" / "skills" / "scanpy" / "SKILL.md",
        "---\nname: scanpy\ndescription: Single-cell analysis\n---\n",
    )
    _write(
        fake_home / ".claude" / "skills" / "rdkit" / "skill.md",
        "# rdkit\nCheminformatics toolkit\n",
    )
    # 3. <project>/.claude/commands/*.md
    _write(
        fake_project / ".claude" / "commands" / "deploy.md",
        "---\ndescription: Deploy this project\n---\n",
    )
    # 4. ~/.claude/plugins/*/commands/*.md
    _write(
        fake_home / ".claude" / "plugins" / "p1" / "commands" / "p1cmd.md",
        "Plugin command body\n",
    )

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    with TestClient(app) as client:
        r = client.get(f"/api/ai/slash_commands?project_dir={fake_project}")
        assert r.status_code == 200
        cmds = r.json()["commands"]
        by_source: dict[str, list[str]] = {}
        for c in cmds:
            by_source.setdefault(c["source"], []).append(c["name"])
        assert "user_hello" in by_source.get("user-commands", [])
        assert "scanpy" in by_source.get("user-skills", [])
        assert "rdkit" in by_source.get("user-skills", [])
        assert "deploy" in by_source.get("project", [])
        assert "p1cmd" in by_source.get("plugin", [])


def test_slash_commands_handles_missing_directories_gracefully(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "empty-home"
    fake_home.mkdir()
    fake_project = tmp_path / "empty-project"
    fake_project.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    with TestClient(app) as client:
        r = client.get(f"/api/ai/slash_commands?project_dir={fake_project}")
        assert r.status_code == 200
        assert r.json()["commands"] == []


def test_slash_commands_parses_frontmatter_description(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    fake_project = tmp_path / "project"
    fake_home.mkdir()
    fake_project.mkdir()
    _write(
        fake_home / ".claude" / "commands" / "with_meta.md",
        "---\ndescription: A described command\n---\nbody",
    )
    _write(
        fake_home / ".claude" / "commands" / "no_meta.md",
        "# heading\nNormal body line that becomes the description.\n",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    with TestClient(app) as client:
        r = client.get(f"/api/ai/slash_commands?project_dir={fake_project}")
        items = {c["name"]: c for c in r.json()["commands"]}
        assert items["with_meta"]["description"] == "A described command"
        # H1 heading fallback for files without frontmatter.
        assert "heading" in items["no_meta"]["description"]
