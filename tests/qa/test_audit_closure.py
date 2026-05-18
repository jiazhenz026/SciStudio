"""Tests for ``scieasy.qa.audit.closure`` (ADR-042 §11).

Covers:

* :func:`check_bidirectional` symmetric (no findings on a closed repo).
* :func:`check_bidirectional` asymmetric — ADR-side path absent from MAINTAINERS.
* :func:`check_bidirectional` asymmetric — MAINTAINERS-side path absent from ADRs.
* Shared-ownership semantic conflict on disagreeing ``agent_editable``
  (§11.3.2 / Q1B.4.2).
* :func:`_module_to_paths` expansion to package files.
* :func:`_glob_to_paths` with ``**`` / ``*`` / literal patterns.
* Missing MAINTAINERS file → ``closure.no-maintainers-file`` error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.audit.closure import (
    _build_adr_path_index,
    _build_maintainers_path_index,
    _check_shared_ownership_conflicts,
    _fnmatch_recursive,
    _glob_to_paths,
    _module_to_paths,
    check_bidirectional,
    load_accepted_adrs,
    load_maintainers,
)
from scieasy.qa.schemas.report import Severity

# ---------------------------------------------------------------------------
# Test repo fixture
# ---------------------------------------------------------------------------


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _accepted_adr_text(
    *,
    adr: int = 42,
    governs_modules: list[str] | None = None,
    governs_files: list[str] | None = None,
    agent_editable: str = "false",
) -> str:
    modules = governs_modules or []
    files = governs_files or []
    modules_yaml = "[]" if not modules else "\n" + "\n".join(f"    - {m}" for m in modules)
    files_yaml = "[]" if not files else "\n" + "\n".join(f"    - {f}" for f in files)
    # is_code_implementation=true requires non-empty governs.modules or contracts.
    has_code = bool(modules)
    tests_yaml = "\n  - tests/qa/test_smoke.py" if has_code else " []"
    return (
        f"---\n"
        f"adr: {adr}\n"
        f'title: "Test ADR {adr}"\n'
        f"status: Accepted\n"
        f"date_created: 2026-05-17\n"
        f"date_accepted: 2026-05-18\n"
        f"is_code_implementation: {str(has_code).lower()}\n"
        f"governs:\n"
        f"  modules: {modules_yaml}\n"
        f"  files: {files_yaml}\n"
        f"tests:{tests_yaml}\n"
        f'agent_editable: "{agent_editable}"\n'
        f'owner: "@you"\n'
        f"---\n\n"
        f"# Body\n"
    )


@pytest.fixture
def closed_repo(tmp_path: Path) -> Path:
    """Repo where ADR governs and MAINTAINERS agree."""
    pkg = tmp_path / "src" / "myproj"
    _write(pkg / "__init__.py", "")
    _write(pkg / "module_a.py", "x = 1\n")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        _accepted_adr_text(governs_modules=["myproj"]),
    )
    _write(
        tmp_path / "MAINTAINERS",
        'version: 1\nentries:\n  - path_glob: src/myproj/**\n    adrs: [42]\n    humans: ["@you"]\n',
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Module-to-glob expansion
# ---------------------------------------------------------------------------


def test_module_to_paths_walks_src_layout(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "foo" / "bar"
    _write(pkg / "__init__.py", "")
    _write(pkg / "baz.py", "x = 1\n")

    paths = _module_to_paths(tmp_path, "foo.bar")
    assert "src/foo/bar/__init__.py" in paths
    assert "src/foo/bar/baz.py" in paths


def test_module_to_paths_missing_module_returns_empty(tmp_path: Path) -> None:
    paths = _module_to_paths(tmp_path, "no.such.module")
    assert paths == set()


def test_module_to_paths_handles_single_file_module(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "foo.py", "x = 1\n")
    paths = _module_to_paths(tmp_path, "foo")
    assert paths == {"src/foo.py"}


# ---------------------------------------------------------------------------
# Glob expansion
# ---------------------------------------------------------------------------


def test_glob_to_paths_literal_present(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "x")
    assert _glob_to_paths(tmp_path, "README.md") == {"README.md"}


def test_glob_to_paths_literal_missing_returned_as_is(tmp_path: Path) -> None:
    # Stale MAINTAINERS entry — must round-trip so closure can flag it.
    assert _glob_to_paths(tmp_path, "deleted.md") == {"deleted.md"}


def test_glob_to_paths_double_star(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a" / "x.py", "x")
    _write(tmp_path / "src" / "a" / "b" / "y.py", "y")
    matched = _glob_to_paths(tmp_path, "src/a/**")
    assert "src/a/x.py" in matched
    assert "src/a/b/y.py" in matched


def test_fnmatch_recursive_double_star_crosses_separators() -> None:
    assert _fnmatch_recursive("src/a/b/c.py", "src/**")
    assert _fnmatch_recursive("src/a.py", "src/**")
    assert not _fnmatch_recursive("docs/a.py", "src/**")


def test_fnmatch_recursive_single_star_does_not_cross_separator() -> None:
    assert _fnmatch_recursive("src/a.py", "src/*.py")
    assert not _fnmatch_recursive("src/a/b.py", "src/*.py")


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------


def test_build_adr_path_index_covers_modules_and_files(closed_repo: Path) -> None:
    adrs = load_accepted_adrs(closed_repo)
    assert len(adrs) == 1
    index = _build_adr_path_index(closed_repo, adrs)
    assert "ADR-042" in index
    assert "src/myproj/__init__.py" in index["ADR-042"]
    assert "src/myproj/module_a.py" in index["ADR-042"]


def test_build_maintainers_path_index(closed_repo: Path) -> None:
    maint = load_maintainers(closed_repo)
    assert maint is not None
    all_paths, owners = _build_maintainers_path_index(closed_repo, maint)
    assert "src/myproj/__init__.py" in all_paths
    assert owners["src/myproj/__init__.py"] == ["src/myproj/**"]


# ---------------------------------------------------------------------------
# check_bidirectional
# ---------------------------------------------------------------------------


def test_closed_repo_no_findings(closed_repo: Path) -> None:
    findings = check_bidirectional(closed_repo)
    assert findings == []


def test_missing_maintainers_emits_no_maintainers_file(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        _accepted_adr_text(governs_modules=["foo"]),
    )
    findings = check_bidirectional(tmp_path)
    assert any(f.rule_id == "closure.no-maintainers-file" for f in findings)


def test_adr_path_without_maintainers_entry(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "myproj"
    _write(pkg / "__init__.py", "")
    _write(pkg / "orphan.py", "x = 1\n")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        _accepted_adr_text(governs_modules=["myproj"]),
    )
    _write(
        tmp_path / "MAINTAINERS",
        'version: 1\nentries:\n  - path_glob: docs/**\n    adrs: [42]\n    humans: ["@you"]\n',
    )
    findings = check_bidirectional(tmp_path)
    asymmetric = [f for f in findings if f.rule_id == "closure.asymmetric"]
    assert any("not governed" in f.message or "no MAINTAINERS entry" in f.message for f in asymmetric)
    assert any(f.file == "src/myproj/orphan.py" for f in asymmetric)


def test_maintainers_path_without_adr_coverage(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "adr" / "ADR-042.md", _accepted_adr_text(governs_files=["README.md"]))
    _write(tmp_path / "README.md", "x")
    _write(tmp_path / "stray.py", "x = 1\n")
    _write(
        tmp_path / "MAINTAINERS",
        "version: 1\nentries:\n"
        "  - path_glob: README.md\n"
        "    adrs: [42]\n"
        '    humans: ["@you"]\n'
        "  - path_glob: stray.py\n"
        "    adrs: [42]\n"
        '    humans: ["@you"]\n',
    )
    findings = check_bidirectional(tmp_path)
    asymmetric = [f for f in findings if f.rule_id == "closure.asymmetric"]
    assert any(f.file == "stray.py" for f in asymmetric)


# ---------------------------------------------------------------------------
# Shared-ownership semantic conflict (§11.3.2 / Q1B.4.2)
# ---------------------------------------------------------------------------


def test_shared_ownership_conflict_on_agent_editable(tmp_path: Path) -> None:
    _write(tmp_path / "shared.py", "x = 1\n")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        _accepted_adr_text(adr=42, governs_files=["shared.py"], agent_editable="false"),
    )
    _write(
        tmp_path / "docs" / "adr" / "ADR-043.md",
        _accepted_adr_text(adr=43, governs_files=["shared.py"], agent_editable="true"),
    )
    adrs = load_accepted_adrs(tmp_path)
    conflicts = _check_shared_ownership_conflicts(adrs)
    assert any(f.rule_id == "closure.multi-adr-conflict" for f in conflicts)
    assert all(f.severity == Severity.WARNING for f in conflicts)


def test_shared_ownership_matching_agent_editable_is_silent(tmp_path: Path) -> None:
    _write(tmp_path / "shared.py", "x = 1\n")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        _accepted_adr_text(adr=42, governs_files=["shared.py"], agent_editable="false"),
    )
    _write(
        tmp_path / "docs" / "adr" / "ADR-043.md",
        _accepted_adr_text(adr=43, governs_files=["shared.py"], agent_editable="false"),
    )
    adrs = load_accepted_adrs(tmp_path)
    assert _check_shared_ownership_conflicts(adrs) == []


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def test_load_accepted_adrs_skips_non_accepted(tmp_path: Path) -> None:
    # Draft ADR (different status block) — must not be loaded.
    draft = _accepted_adr_text(adr=99).replace("Accepted", "Draft").replace("date_accepted: 2026-05-18\n", "")
    _write(tmp_path / "docs" / "adr" / "ADR-099.md", draft)
    assert load_accepted_adrs(tmp_path) == []


def test_load_accepted_adrs_handles_missing_adr_dir(tmp_path: Path) -> None:
    assert load_accepted_adrs(tmp_path) == []


def test_load_maintainers_missing_file(tmp_path: Path) -> None:
    assert load_maintainers(tmp_path) is None


def test_load_maintainers_malformed_yaml(tmp_path: Path) -> None:
    _write(tmp_path / "MAINTAINERS", ":\n: invalid:\n: yaml: : :\n")
    assert load_maintainers(tmp_path) is None


def test_load_maintainers_invalid_schema(tmp_path: Path) -> None:
    _write(tmp_path / "MAINTAINERS", "version: 1\nentries: []\n")
    # Empty entries — schema requires min_length=1.
    assert load_maintainers(tmp_path) is None


def test_load_maintainers_non_mapping_yaml(tmp_path: Path) -> None:
    """``MAINTAINERS`` whose YAML decodes to a list returns None (line 195)."""
    _write(tmp_path / "MAINTAINERS", "- not_a_mapping\n- value\n")
    assert load_maintainers(tmp_path) is None


def test_load_accepted_adrs_skips_yaml_errors(tmp_path: Path) -> None:
    """Malformed YAML in an ADR is silently skipped (line 168)."""
    _write(tmp_path / "docs" / "adr" / "ADR-001.md", "---\n[: invalid\n---\n# Body\n")
    assert load_accepted_adrs(tmp_path) == []


def test_load_accepted_adrs_skips_none_frontmatter(tmp_path: Path) -> None:
    """Files without frontmatter delimiters are silently skipped (line 171)."""
    _write(tmp_path / "docs" / "adr" / "ADR-099.md", "# No frontmatter here\n")
    assert load_accepted_adrs(tmp_path) == []


def test_adr_excludes_subtracts_paths(tmp_path: Path) -> None:
    """``governs.excludes`` correctly carves negation out of ADR index."""
    pkg = tmp_path / "src" / "myproj"
    _write(pkg / "__init__.py", "")
    _write(pkg / "module_a.py", "x = 1\n")
    _write(pkg / "excluded.py", "x = 1\n")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        "---\n"
        "adr: 42\n"
        'title: "Test ADR 42"\n'
        "status: Accepted\n"
        "date_created: 2026-05-17\n"
        "date_accepted: 2026-05-18\n"
        "is_code_implementation: true\n"
        "governs:\n"
        "  modules:\n"
        "    - myproj\n"
        "  files: []\n"
        "  excludes:\n"
        "    - src/myproj/excluded.py\n"
        "tests:\n"
        "  - tests/qa/test_smoke.py\n"
        'agent_editable: "false"\n'
        'owner: "@you"\n'
        "---\n# Body\n",
    )
    adrs = load_accepted_adrs(tmp_path)
    index = _build_adr_path_index(tmp_path, adrs)
    assert "src/myproj/excluded.py" not in index["ADR-042"]
    assert "src/myproj/module_a.py" in index["ADR-042"]


def test_maintainers_excludes_subtracts_paths(tmp_path: Path) -> None:
    """``MAINTAINERS`` entry's ``excludes`` carve out paths."""
    _write(tmp_path / "src" / "a.py", "x")
    _write(tmp_path / "src" / "b.py", "x")
    _write(
        tmp_path / "MAINTAINERS",
        "version: 1\nentries:\n"
        "  - path_glob: src/**\n"
        "    adrs: [42]\n"
        '    humans: ["@you"]\n'
        "    excludes:\n"
        "      - src/b.py\n",
    )
    maint = load_maintainers(tmp_path)
    assert maint is not None
    all_paths, _ = _build_maintainers_path_index(tmp_path, maint)
    assert "src/a.py" in all_paths
    assert "src/b.py" not in all_paths


def test_module_to_paths_walks_repo_layout(tmp_path: Path) -> None:
    """Module-to-paths also tries the no-src layout (line 346 alt branch)."""
    pkg = tmp_path / "demo_no_src"
    _write(pkg / "__init__.py", "")
    _write(pkg / "x.py", "x = 1")
    # The repo doesn't have src/; expansion uses the no-src branch.
    paths = _module_to_paths(tmp_path, "demo_no_src")
    assert "demo_no_src/__init__.py" in paths


def test_glob_to_paths_directory_literal(tmp_path: Path) -> None:
    """A literal directory glob expands to its files."""
    d = tmp_path / "configs"
    _write(d / "a.yaml", "x")
    _write(d / "b.yaml", "y")
    matched = _glob_to_paths(tmp_path, "configs")
    assert "configs/a.yaml" in matched
    assert "configs/b.yaml" in matched
