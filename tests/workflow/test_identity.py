"""Workflow run identity derived from the workflow file (#2394)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest
import yaml

from scistudio.workflow.identity import (
    declared_id_for_file_name,
    is_path_identity,
    project_relative_path_for_identity,
    rewrite_workflow_id_text,
    workflow_identity_for_path,
    workflow_identity_for_relative_path,
)


@pytest.mark.parametrize(
    ("relative", "identity"),
    [
        ("workflows/main.yaml", "main"),
        ("workflows/my analysis-2.yaml", "my analysis-2"),
        ("subworkflows/qc.yaml", "@subworkflows@qc.yaml"),
        ("subworkflows/qc.swf.yaml", "@subworkflows@qc.swf.yaml"),
        ("workflows/nested/main.yaml", "@workflows@nested@main.yaml"),
        ("workflows/main.yml", "@workflows@main.yml"),
        ("workflows/@odd.yaml", "@workflows@%40odd.yaml"),
        ("sub/a@b%c.yaml", "@sub@a%40b%25c.yaml"),
    ],
)
def test_identity_round_trips_to_the_file(relative: str, identity: str) -> None:
    assert workflow_identity_for_relative_path(relative) == identity
    assert project_relative_path_for_identity(identity) == PurePosixPath(relative)
    assert is_path_identity(identity) is identity.startswith("@")


def test_identities_are_single_path_segments() -> None:
    """The identity is used as a directory name, a file name and a URL path parameter."""
    for relative in ("subworkflows/deep/er/qc.yaml", "a/b/c.yml"):
        identity = workflow_identity_for_relative_path(relative)
        assert "/" not in identity and "\\" not in identity


def test_distinct_files_never_share_an_identity() -> None:
    files = [
        "workflows/main.yaml",
        "subworkflows/main.yaml",
        "workflows/@subworkflows@main.yaml.yaml",
        "workflows/sub/main.yaml",
        "workflows/sub@main.yaml",
    ]
    identities = [workflow_identity_for_relative_path(f) for f in files]
    assert len(set(identities)) == len(files)


def test_a_stem_that_is_not_a_valid_path_form_names_a_top_level_file() -> None:
    assert project_relative_path_for_identity("@legacy") == PurePosixPath("workflows/@legacy.yaml")
    assert not is_path_identity("@legacy")
    assert not is_path_identity("@sub@..@x.yaml")


def test_identity_for_an_absolute_path_inside_the_project(tmp_path: Path) -> None:
    (tmp_path / "subworkflows").mkdir()
    target = tmp_path / "subworkflows" / "qc.yaml"
    target.write_text("workflow: {}\n", encoding="utf-8")
    assert workflow_identity_for_path(tmp_path, target) == "@subworkflows@qc.yaml"
    assert workflow_identity_for_path(tmp_path, "workflows/main.yaml") == "main"
    with pytest.raises(ValueError, match="outside the project"):
        workflow_identity_for_path(tmp_path / "subworkflows", tmp_path / "workflows" / "main.yaml")


@pytest.mark.parametrize(
    ("name", "declared"),
    [("main.yaml", "main"), ("qc.swf.yaml", "qc"), ("run.YML", "run"), ("a.b.yaml", "a.b")],
)
def test_declared_id_for_file_name(name: str, declared: str) -> None:
    assert declared_id_for_file_name(name) == declared


def test_rewrite_keeps_comments_and_order() -> None:
    text = "# header\nworkflow:\n  # the id\n  id: old  # trailing\n  version: 1.0.0\n  nodes: []\n"
    rewritten = rewrite_workflow_id_text(text, "new")
    assert rewritten == "# header\nworkflow:\n  # the id\n  id: new  # trailing\n  version: 1.0.0\n  nodes: []\n"


def test_rewrite_inserts_a_missing_id_and_quotes_when_needed() -> None:
    rewritten = rewrite_workflow_id_text("workflow:\n  version: '1'\n  nodes: []\n", "yes")
    assert rewritten is not None
    assert yaml.safe_load(rewritten)["workflow"] == {"id": "yes", "version": "1", "nodes": []}


def test_rewrite_ignores_nested_id_keys() -> None:
    text = "workflow:\n  nodes:\n    - id: load\n  id: old\n"
    rewritten = rewrite_workflow_id_text(text, "new")
    assert rewritten is not None
    assert yaml.safe_load(rewritten)["workflow"] == {"nodes": [{"id": "load"}], "id": "new"}


def test_rewrite_refuses_text_without_a_workflow_mapping() -> None:
    assert rewrite_workflow_id_text("id: flat\nnodes: []\n", "new") is None
    assert rewrite_workflow_id_text("workflow: {id: inline}\n", "new") is None
