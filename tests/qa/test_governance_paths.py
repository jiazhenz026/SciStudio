"""Regression tests for the shared governance path helper (#1362).

The helper exists so the four governance modules that consult any
``.workflow/**`` glob agree on what counts as a per-PR gate-record evidence
file. Without it each module reimplemented the exclusion separately and
half of them missed it (see #1316, #1340 for two prior incomplete passes).

This test module covers:

1. ``governance.paths.is_gate_record_path`` direct behaviour.
2. Each of the four governance modules' integration with the helper —
   asserting a records-only diff does not trip the module's check.
"""

from __future__ import annotations

from scistudio.qa.governance import core_change_guard, docs_landing, gate_record, sentrux_gate
from scistudio.qa.governance.paths import GATE_RECORD_PATTERNS, is_gate_record_path


class TestIsGateRecordPath:
    """``is_gate_record_path`` recognises the canonical records location."""

    def test_records_json_matches(self) -> None:
        assert is_gate_record_path(".workflow/records/1357-adr-044-subworkflow.json")

    def test_records_nested_subdir_matches(self) -> None:
        # ``**`` matches arbitrarily many path components, so a hypothetical
        # subdirectory under records is still a record.
        assert is_gate_record_path(".workflow/records/archive/old.json")

    def test_windows_separators_normalised(self) -> None:
        assert is_gate_record_path(r".workflow\records\1357-foo.json")

    def test_non_records_workflow_path_does_not_match(self) -> None:
        # ``.workflow/active``, ``.workflow/hooks/**`` and similar are the
        # actual governance config files — they must remain non-records.
        assert not is_gate_record_path(".workflow/active")
        assert not is_gate_record_path(".workflow/hooks/pre-commit.sh")

    def test_unrelated_path_does_not_match(self) -> None:
        assert not is_gate_record_path("src/scistudio/qa/governance/mod_guard.py")
        assert not is_gate_record_path("docs/adr/ADR-044.md")
        assert not is_gate_record_path("CHANGELOG.md")

    def test_patterns_exposed_for_callers(self) -> None:
        # ``GATE_RECORD_PATTERNS`` is exported so other modules can compose
        # patterns; the canonical entry must be present.
        assert ".workflow/records/**" in GATE_RECORD_PATTERNS


class TestCoreChangeGuardRecordsException:
    """``core_change_guard._is_protected`` short-circuits records paths.

    Regression for the gap that blocked PR #1359: a docs-only PR whose only
    ``.workflow/**`` change is its own gate record must not require
    ``admin-approved:core-change``.
    """

    def test_records_path_not_protected(self) -> None:
        assert not core_change_guard._is_protected(
            ".workflow/records/1357-foo.json",
            core_change_guard.PROTECTED_GLOBS,
        )

    def test_non_records_workflow_path_still_protected(self) -> None:
        # ``.workflow/active`` and ``.workflow/hooks/**`` remain protected —
        # only the records subtree is excluded.
        assert core_change_guard._is_protected(".workflow/active", core_change_guard.PROTECTED_GLOBS)
        assert core_change_guard._is_protected(
            ".workflow/hooks/pre-commit.sh",
            core_change_guard.PROTECTED_GLOBS,
        )

    def test_protected_source_path_still_protected(self) -> None:
        assert core_change_guard._is_protected(
            "src/scistudio/qa/governance/mod_guard.py",
            core_change_guard.PROTECTED_GLOBS,
        )

    def test_records_only_change_passes_check_without_label(self) -> None:
        report = core_change_guard.check(
            changed_files=[".workflow/records/1357-foo.json"],
            pr=None,
        )
        assert report.status.value == "pass"
        assert report.findings == []


class TestSentruxApplicabilityRecordsException:
    """``sentrux_gate.sentrux_applies_to_changes`` skips records paths."""

    def test_records_only_diff_does_not_require_sentrux(self) -> None:
        assert not sentrux_gate.sentrux_applies_to_changes([".workflow/records/1357-foo.json"])

    def test_non_records_workflow_path_still_requires_sentrux(self) -> None:
        assert sentrux_gate.sentrux_applies_to_changes([".workflow/hooks/pre-commit.sh"])

    def test_records_mixed_with_source_still_requires_sentrux(self) -> None:
        # The presence of any non-records architectural surface in the diff
        # still requires Sentrux — the records exception is per-file, not
        # per-PR.
        assert sentrux_gate.sentrux_applies_to_changes(
            [".workflow/records/1357-foo.json", "src/scistudio/blocks/io/io_block.py"]
        )

    def test_no_changes_still_requires_sentrux(self) -> None:
        # ``None``/empty inputs default to ``True`` (fail closed); the
        # records exception must not weaken this guard.
        assert sentrux_gate.sentrux_applies_to_changes(None)
        assert sentrux_gate.sentrux_applies_to_changes([])


class TestDocsLandingRecordsException:
    """``docs_landing._requires_landing`` skips records paths."""

    def test_records_only_does_not_require_landing(self) -> None:
        assert not docs_landing._requires_landing([".workflow/records/1357-foo.json"])

    def test_records_plus_changelog_does_not_require_landing(self) -> None:
        # ``CHANGELOG.md`` is already excluded by the existing rule; combined
        # with a records-only change the result must still be no landing
        # requirement.
        assert not docs_landing._requires_landing([".workflow/records/1357-foo.json", "CHANGELOG.md"])

    def test_records_plus_source_still_requires_landing(self) -> None:
        assert docs_landing._requires_landing(
            [".workflow/records/1357-foo.json", "src/scistudio/blocks/io/io_block.py"]
        )

    def test_non_records_workflow_path_still_requires_landing(self) -> None:
        # ``.workflow/hooks/**`` is genuine governance and must still require
        # the landing evidence.
        assert docs_landing._requires_landing([".workflow/hooks/pre-commit.sh"])


class TestGateRecordSentruxAppliesException:
    """``gate_record._sentrux_applies`` skips records paths.

    This is the gate-record-internal duplicate of
    ``sentrux_gate.sentrux_applies_to_changes`` and was carrying the same
    gap.
    """

    def test_records_path_not_applicable(self) -> None:
        assert not gate_record._sentrux_applies(".workflow/records/1357-foo.json")

    def test_non_records_workflow_path_still_applicable(self) -> None:
        assert gate_record._sentrux_applies(".workflow/active")
        assert gate_record._sentrux_applies(".workflow/hooks/pre-commit.sh")

    def test_protected_source_path_still_applicable(self) -> None:
        assert gate_record._sentrux_applies("src/scistudio/blocks/io/io_block.py")

    def test_unrelated_doc_path_not_applicable(self) -> None:
        # Non-ADR docs were already excluded and must remain so.
        assert not gate_record._sentrux_applies("docs/user/quickstart.md")
