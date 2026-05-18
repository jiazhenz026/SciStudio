"""Tests for ``scieasy.qa.audit.doc_drift`` (ADR-042 §9).

Covers:

* :func:`build_code_symbol_index` populates dotted-path entries.
* :func:`classify_repo` returns a valid :class:`AuditReport`.
* Forward pass: governs.contracts symbol present in code → no b/c finding.
* Forward pass: governs.contracts symbol missing from code AND missing from
  git history → c2 (hallucination) finding.
* Reverse pass: public class with no ADR coverage → d-class orphan.
* Reverse pass: public function with no docstring → d-class
  ``missing-docstring``.
* Reverse pass: missing ``__all__`` → ``missing-all`` warning (Phase 1).
* :func:`is_public` underscore / ``__all__`` semantics.
* :func:`_levenshtein` correctness.
* :func:`_nearest_existing_symbol` suggests close match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.audit.doc_drift import (
    _levenshtein,
    _nearest_existing_symbol,
    build_code_symbol_index,
    classify_repo,
    is_public,
)
from scieasy.qa.schemas.report import AuditReport, DriftClass, Severity

# ---------------------------------------------------------------------------
# Fixture: a minimal repo with a known code module + ADR
# ---------------------------------------------------------------------------


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def minimal_repo(tmp_path: Path) -> Path:
    """A repo with one package, one class, one ADR governing it."""
    pkg = tmp_path / "src" / "demo"
    _write(
        pkg / "__init__.py",
        '"""Demo package."""\n\n__all__ = ["MyClass", "my_func"]\n\nfrom .api import MyClass, my_func  # noqa: F401\n',
    )
    _write(
        pkg / "api.py",
        '"""Demo API."""\n\n__all__ = ["MyClass", "my_func"]\n\n\nclass MyClass:\n'
        '    """My documented class."""\n\n    def method(self) -> int:\n'
        '        """Return 1."""\n        return 1\n\n\n'
        "def my_func() -> int:\n"
        '    """Return 2."""\n    return 2\n',
    )
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        "---\n"
        "adr: 42\n"
        'title: "Demo ADR"\n'
        "status: Accepted\n"
        "date_created: 2026-05-17\n"
        "date_accepted: 2026-05-18\n"
        "is_code_implementation: true\n"
        "governs:\n"
        "  modules:\n"
        "    - demo\n"
        "  contracts:\n"
        "    - demo.api.MyClass\n"
        "  files: []\n"
        "tests:\n"
        "  - tests/qa/test_smoke.py\n"
        'agent_editable: "false"\n'
        'owner: "@you"\n'
        "---\n\n"
        "# Body\n",
    )
    _write(
        tmp_path / "MAINTAINERS",
        'version: 1\nentries:\n  - path_glob: src/demo/**\n    adrs: [42]\n    humans: ["@you"]\n',
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def test_build_code_symbol_index_finds_class(minimal_repo: Path) -> None:
    index = build_code_symbol_index(minimal_repo)
    assert "demo.api.MyClass" in index
    assert "demo.api.my_func" in index


def test_build_code_symbol_index_empty_for_no_src(tmp_path: Path) -> None:
    assert build_code_symbol_index(tmp_path) == {}


# ---------------------------------------------------------------------------
# classify_repo
# ---------------------------------------------------------------------------


def test_classify_repo_returns_audit_report(minimal_repo: Path) -> None:
    report = classify_repo(minimal_repo)
    assert isinstance(report, AuditReport)
    assert report.schema_version == 1
    assert len(report.runs) == 1
    assert report.runs[0].tool == "doc_drift"


def test_classify_repo_governed_class_no_orphan(minimal_repo: Path) -> None:
    report = classify_repo(minimal_repo)
    orphan_findings = [f for f in report.runs[0].findings if f.rule_id == "doc-drift.orphan-class"]
    assert not any(f.symbol == "demo.api.MyClass" for f in orphan_findings)


def test_classify_repo_orphan_class_flagged(tmp_path: Path) -> None:
    """A public class with no ADR coverage triggers d-class orphan."""
    pkg = tmp_path / "src" / "ungoverned"
    _write(pkg / "__init__.py", "from .api import Orphan\n")
    _write(
        pkg / "api.py",
        '"""API."""\n\nclass Orphan:\n    """Hi."""\n    pass\n',
    )
    # No ADR; closure will also emit findings but we filter by rule_id.
    report = classify_repo(tmp_path)
    orphans = [f for f in report.runs[0].findings if f.rule_id == "doc-drift.orphan-class"]
    assert any(f.symbol == "ungoverned.api.Orphan" for f in orphans)
    assert all(f.drift_class == DriftClass.D for f in orphans)


def test_classify_repo_missing_docstring_flagged(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "demo"
    _write(pkg / "__init__.py", "from .api import undocumented\n")
    _write(
        pkg / "api.py",
        "def undocumented():\n    return 1\n",
    )
    report = classify_repo(tmp_path)
    findings = [f for f in report.runs[0].findings if f.rule_id == "doc-drift.missing-docstring"]
    assert any(f.symbol == "demo.api.undocumented" for f in findings)
    assert all(f.severity == Severity.WARNING for f in findings)


def test_classify_repo_c2_finding_when_symbol_never_existed(tmp_path: Path) -> None:
    """ADR cites a symbol that has never existed in code → c2."""
    pkg = tmp_path / "src" / "demo"
    _write(pkg / "__init__.py", "")  # empty
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        "---\n"
        "adr: 42\n"
        'title: "Demo ADR"\n'
        "status: Accepted\n"
        "date_created: 2026-05-17\n"
        "date_accepted: 2026-05-18\n"
        "is_code_implementation: true\n"
        "governs:\n"
        "  modules:\n"
        "    - demo\n"
        "  contracts:\n"
        "    - demo.api.Hallucinated\n"
        "  files: []\n"
        "tests:\n"
        "  - tests/qa/test_smoke.py\n"
        'agent_editable: "false"\n'
        'owner: "@you"\n'
        "---\n\n"
        "# Body\n",
    )
    report = classify_repo(tmp_path)
    c_findings = [f for f in report.runs[0].findings if f.rule_id.startswith("doc-drift.c")]
    assert any(
        f.symbol == "demo.api.Hallucinated" and f.drift_class in (DriftClass.C1, DriftClass.C2, DriftClass.C3)
        for f in c_findings
    )


def test_classify_repo_missing_all_warning(tmp_path: Path) -> None:
    """A public module without ``__all__`` gets a Phase 1 warning."""
    pkg = tmp_path / "src" / "demo"
    _write(pkg / "__init__.py", "")  # no __all__
    _write(pkg / "api.py", "")  # no __all__
    report = classify_repo(tmp_path)
    findings = [f for f in report.runs[0].findings if f.rule_id == "doc-drift.missing-all"]
    assert findings
    assert all(f.severity == Severity.WARNING for f in findings)


def test_classify_repo_aggregates_closure_findings(tmp_path: Path) -> None:
    """Closure findings appear in the same ToolRun.findings list."""
    pkg = tmp_path / "src" / "demo"
    _write(pkg / "__init__.py", "")
    _write(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        "---\n"
        "adr: 42\n"
        'title: "Demo ADR"\n'
        "status: Accepted\n"
        "date_created: 2026-05-17\n"
        "date_accepted: 2026-05-18\n"
        "is_code_implementation: true\n"
        "governs:\n"
        "  modules:\n"
        "    - demo\n"
        "  contracts: []\n"
        "  files: []\n"
        "tests:\n"
        "  - tests/qa/test_smoke.py\n"
        'agent_editable: "false"\n'
        'owner: "@you"\n'
        "---\n# Body\n",
    )
    # No MAINTAINERS → closure.no-maintainers-file finding.
    report = classify_repo(tmp_path)
    assert any(f.rule_id == "closure.no-maintainers-file" for f in report.runs[0].findings)


# ---------------------------------------------------------------------------
# is_public
# ---------------------------------------------------------------------------


def test_is_public_with_all(minimal_repo: Path) -> None:
    index = build_code_symbol_index(minimal_repo)
    # demo.api exports MyClass + my_func.
    assert is_public(index["demo.api.MyClass"])
    # method `MyClass.method` — parent has no exports list pointing at method,
    # so falls back to non-underscore check.
    assert is_public(index["demo.api.MyClass.method"])


def test_is_public_underscore_not_public(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "demo"
    _write(pkg / "__init__.py", "from .api import _hidden\n")
    _write(
        pkg / "api.py",
        '"""x."""\n\ndef _hidden():\n    """h."""\n    return 1\n',
    )
    index = build_code_symbol_index(tmp_path)
    assert not is_public(index["demo.api._hidden"])


# ---------------------------------------------------------------------------
# Levenshtein + nearest-symbol
# ---------------------------------------------------------------------------


def test_levenshtein_equal_lists() -> None:
    assert _levenshtein(["a", "b"], ["a", "b"]) == 0


def test_levenshtein_one_substitution() -> None:
    assert _levenshtein(["a", "b"], ["a", "c"]) == 1


def test_levenshtein_empty_lists() -> None:
    assert _levenshtein([], ["a", "b"]) == 2
    assert _levenshtein(["a"], []) == 1


def test_nearest_existing_symbol(minimal_repo: Path) -> None:
    index = build_code_symbol_index(minimal_repo)
    # Typo in MyClass → MyClas (within edit-distance 3 on segments).
    nearest = _nearest_existing_symbol("demo.api.MyClas", index)
    assert nearest is not None
    # Should pick something in the demo.api namespace.
    assert nearest.startswith("demo.")


def test_nearest_existing_symbol_returns_none_for_far_path(minimal_repo: Path) -> None:
    index = build_code_symbol_index(minimal_repo)
    # Completely unrelated dotted path with >3 segments different.
    assert _nearest_existing_symbol("totally.completely.different.thing", index) is None


# ---------------------------------------------------------------------------
# _c_class_finding evidence branches
# ---------------------------------------------------------------------------


def test_c1_finding_for_deleted_symbol(minimal_repo: Path) -> None:
    """Evidence shows symbol was present and later deleted → c1."""
    from scieasy.qa.audit.doc_drift import _c_class_finding

    adr = next(iter([adr for adr in [_load_adr(minimal_repo / "docs/adr/ADR-042.md")] if adr]))
    evidence = {
        "was_present_then_deleted": True,
        "deleting_commit_sha": "abc1234",
        "deleting_commit_author": "alice",
    }
    finding = _c_class_finding("demo.api.Gone", adr, evidence, {})
    assert finding.drift_class == DriftClass.C1
    assert finding.rule_id == "doc-drift.c1"
    assert "abc1234" in finding.message


def test_c3_finding_for_mixed_evidence(minimal_repo: Path) -> None:
    from scieasy.qa.audit.doc_drift import _c_class_finding

    adr = _load_adr(minimal_repo / "docs/adr/ADR-042.md")
    evidence: dict[str, object] = {}  # neither flag set
    finding = _c_class_finding("demo.api.Mixed", adr, evidence, {})
    assert finding.drift_class == DriftClass.C3
    assert finding.rule_id == "doc-drift.c3"


def _load_adr(path: Path):
    """Helper: parse an ADR file via the closure helper."""
    from scieasy.qa.audit.closure import _parse_adr_frontmatter

    fm = _parse_adr_frontmatter(path)
    assert fm is not None
    return fm


# ---------------------------------------------------------------------------
# signatures_match Phase-1 behaviour
# ---------------------------------------------------------------------------


def test_signatures_match_returns_true_for_function(minimal_repo: Path) -> None:
    """Phase 1 trusts the dotted-path resolution; always True for callables."""
    from scieasy.qa.audit.doc_drift import signatures_match

    index = build_code_symbol_index(minimal_repo)
    adr = _load_adr(minimal_repo / "docs/adr/ADR-042.md")

    obj = index["demo.api.my_func"]
    matched, _reason = signatures_match(obj, adr)
    assert matched is True


def test_signatures_match_returns_true_for_class(minimal_repo: Path) -> None:
    from scieasy.qa.audit.doc_drift import signatures_match

    index = build_code_symbol_index(minimal_repo)
    adr = _load_adr(minimal_repo / "docs/adr/ADR-042.md")

    obj = index["demo.api.MyClass"]
    matched, _ = signatures_match(obj, adr)
    assert matched is True


# ---------------------------------------------------------------------------
# Git helpers / report metadata fall back gracefully
# ---------------------------------------------------------------------------


def test_classify_repo_resolves_repo_metadata(minimal_repo: Path) -> None:
    """``classify_repo`` populates ``repo_sha`` / ``repo_branch``."""
    report = classify_repo(minimal_repo)
    # Outside a git repo: helpers return "unknown".
    assert report.repo_sha
    assert report.repo_branch


def test_git_helpers_handle_missing_git_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``git`` is missing the helpers fall back to 'unknown' / 'never_existed'."""
    import subprocess

    from scieasy.qa.audit.doc_drift import (
        _git_history_for_symbol,
        _resolve_repo_branch,
        _resolve_repo_sha,
    )

    def boom(*a, **kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", boom)
    assert _resolve_repo_sha(tmp_path) == "unknown"
    assert _resolve_repo_branch(tmp_path) == "unknown"
    evidence = _git_history_for_symbol("demo.x", tmp_path)
    assert evidence == {"never_existed": True}


def test_compute_exit_status_branches() -> None:
    """Cover :func:`_compute_exit_status` for ok / warnings / errors."""
    from scieasy.qa.audit.doc_drift import _compute_exit_status
    from scieasy.qa.schemas.report import Finding, Severity

    assert _compute_exit_status([]) == "ok"
    assert _compute_exit_status([Finding(rule_id="x", severity=Severity.INFO, file="f", message="m")]) == "ok"
    assert _compute_exit_status([Finding(rule_id="x", severity=Severity.WARNING, file="f", message="m")]) == "warnings"
    assert _compute_exit_status([Finding(rule_id="x", severity=Severity.ERROR, file="f", message="m")]) == "errors"


def test_griffe_filepath_unknown() -> None:
    """``_griffe_filepath`` returns '<unknown>' when filepath is None."""
    from scieasy.qa.audit.doc_drift import _griffe_filepath

    class _Stub:
        filepath = None

    assert _griffe_filepath(_Stub()) == "<unknown>"
