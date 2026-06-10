"""Tests for the single ADR-042 Addendum 6 surface classifier (spec §2/§4.1).

The pre-Addendum-6 design scattered the per-PR gate-record-path exclusion and
the sentrux-applicability predicate across four governance modules (#1316,
#1340, #1362), and local (`gate_record._sentrux_applies`, excluding `tests/**`)
disagreed with CI (`sentrux_gate.sentrux_applies_to_changes`, including it).
Addendum 6 collapses all of that into one ``surfaces`` module. These tests own
the classifier's path predicates: the gate-record exclusion is applied once, and
``sentrux_applies`` is the single CI-inclusive predicate local and CI both use.
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record import surfaces


class TestGateRecordPathExclusion:
    """``is_gate_record_path`` recognises the canonical records location once."""

    def test_records_json_matches(self) -> None:
        assert surfaces.is_gate_record_path(".workflow/records/1357-adr-044-subworkflow.json")

    def test_records_nested_subdir_matches(self) -> None:
        assert surfaces.is_gate_record_path(".workflow/records/archive/old.json")

    def test_windows_separators_normalised(self) -> None:
        assert surfaces.is_gate_record_path(r".workflow\records\1357-foo.json")

    def test_non_records_workflow_path_does_not_match(self) -> None:
        assert not surfaces.is_gate_record_path(".workflow/hooks/pre-commit.sh")
        assert not surfaces.is_gate_record_path(".github/workflows/ci.yml")

    def test_unrelated_path_does_not_match(self) -> None:
        assert not surfaces.is_gate_record_path("src/scistudio/qa/governance/gate_record/evaluator.py")
        assert not surfaces.is_gate_record_path("CHANGELOG.md")

    def test_records_pattern_exposed_for_callers(self) -> None:
        assert ".workflow/records/**" in surfaces.GATE_RECORD_PATTERNS


class TestSurfaceClassificationExcludesGateRecords:
    """A per-PR gate record is neither governance, protected-core, nor workflow."""

    def test_records_path_is_not_governance(self) -> None:
        assert not surfaces.is_governance_path(".workflow/records/1357-foo.json")

    def test_records_path_is_not_protected_core(self) -> None:
        assert not surfaces.is_protected_core_path(".workflow/records/1357-foo.json")

    def test_records_path_is_not_workflow_ci(self) -> None:
        assert not surfaces.is_workflow_ci_path(".workflow/records/1357-foo.json")

    def test_non_records_workflow_path_still_governance(self) -> None:
        assert surfaces.is_governance_path(".github/workflows/ci.yml")
        assert surfaces.is_workflow_ci_path(".github/workflows/ci.yml")

    def test_qa_governance_source_is_governance(self) -> None:
        assert surfaces.is_governance_path("src/scistudio/qa/governance/gate_record/evaluator.py")

    def test_ai_developer_docs_are_governed(self) -> None:
        # §7.8: docs/ai-developer/** is a governance surface and a governed doc.
        assert surfaces.is_governance_path("docs/ai-developer/rules.md")
        assert surfaces.is_governed_doc_path("docs/ai-developer/rules.md")


class TestSentruxApplicabilityIsSingleCiInclusivePredicate:
    """``sentrux_applies`` resolves the §4.1 asymmetry — tests/** ARE applicable."""

    def test_source_is_applicable(self) -> None:
        assert surfaces.sentrux_applies("src/scistudio/blocks/io/io_block.py")

    def test_tests_are_applicable_ci_inclusive(self) -> None:
        # The §4.1 fix: local must agree with CI and include tests/**.
        assert surfaces.sentrux_applies("tests/qa/test_x.py")

    def test_records_path_is_not_applicable(self) -> None:
        assert not surfaces.sentrux_applies(".workflow/records/1357-foo.json")

    def test_non_records_workflow_path_still_applicable(self) -> None:
        assert surfaces.sentrux_applies(".workflow/hooks/pre-commit.sh")
        assert surfaces.sentrux_applies(".github/workflows/ci.yml")

    def test_ordinary_docs_not_applicable_but_adr_is(self) -> None:
        assert not surfaces.sentrux_applies("docs/user/quickstart.md")
        assert surfaces.sentrux_applies("docs/adr/ADR-042-addendum1.md")
        assert surfaces.sentrux_applies("docs/specs/example.md")

    def test_changes_helper_is_per_file_not_per_pr(self) -> None:
        # A records-only diff is not applicable; mixing in a source file is.
        assert not surfaces.sentrux_applies_to_changes([".workflow/records/1357-foo.json"])
        assert surfaces.sentrux_applies_to_changes(
            [".workflow/records/1357-foo.json", "src/scistudio/blocks/io/io_block.py"]
        )

    def test_empty_diff_is_not_applicable(self) -> None:
        # Unlike the legacy fail-closed default, an empty changed-file set has no
        # sentrux-applicable surface; the evaluator records the advisory, not a
        # block (sentrux is opt-in per the active addendum).
        assert not surfaces.sentrux_applies_to_changes([])
