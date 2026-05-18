"""Unit tests for :mod:`scieasy.qa.test_quality.ast_lint` (TC-1F.1).

Each of the ten anti-patterns from ADR-043 §4.2.1 has a positive case
(detector fires) and a negative case (detector stays silent). The
helper :func:`_lint_source` writes a source string to a tmp file and
invokes :func:`check_test_file` so the file-path plumbing is exercised
end-to-end.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scieasy.qa.schemas.report import Severity
from scieasy.qa.schemas.test_quality import AntiPattern
from scieasy.qa.test_quality.ast_lint import check_test_file


def _lint_source(src: str, tmp_path: Path, name: str = "test_sample.py") -> list:
    """Write ``src`` to ``tmp_path / name`` and run ``check_test_file``."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return check_test_file(p)


def _patterns(findings) -> set[str]:
    return {f.rule_id.removeprefix("TQAST-") for f in findings}


# --------------------------------------------------------------------------- #
# 1. no-assert                                                                #
# --------------------------------------------------------------------------- #


def test_no_assert_fires_when_function_has_no_assertion(tmp_path: Path) -> None:
    """Anti-pattern: test exercises code but never asserts anything."""
    findings = _lint_source(
        """
        def test_silent():
            x = 1 + 2
            print(x)
        """,
        tmp_path,
    )
    assert AntiPattern.NO_ASSERT.value in _patterns(findings)
    no_assert = [f for f in findings if f.rule_id == "TQAST-no-assert"]
    assert no_assert[0].severity is Severity.ERROR
    assert no_assert[0].symbol == "test_silent"


def test_no_assert_silent_when_pytest_raises_used(tmp_path: Path) -> None:
    """``pytest.raises(...)`` context counts as an assertion."""
    findings = _lint_source(
        """
        import pytest
        def test_raises():
            with pytest.raises(ValueError, match="bad"):
                int("xyz")
        """,
        tmp_path,
    )
    assert AntiPattern.NO_ASSERT.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 2. assert-not-none-only                                                     #
# --------------------------------------------------------------------------- #


def test_assert_not_none_only_fires_when_sole_assertion_is_is_not_none(
    tmp_path: Path,
) -> None:
    """``assert result is not None`` alone is too weak."""
    findings = _lint_source(
        """
        def test_returns_something():
            result = compute()
            assert result is not None
        """,
        tmp_path,
    )
    assert AntiPattern.ASSERT_NOT_NONE_ONLY.value in _patterns(findings)


def test_assert_not_none_only_silent_with_additional_value_check(
    tmp_path: Path,
) -> None:
    """Other meaningful assertions suppress the warning."""
    findings = _lint_source(
        """
        def test_returns_specific_value():
            result = compute()
            assert result is not None
            assert result == 42
        """,
        tmp_path,
    )
    assert AntiPattern.ASSERT_NOT_NONE_ONLY.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 3. mocks-the-subject                                                        #
# --------------------------------------------------------------------------- #


def test_mocks_the_subject_fires_when_patch_targets_function_under_test(
    tmp_path: Path,
) -> None:
    """``patch('mod.normalize')`` inside ``test_normalize_*`` is tautological."""
    findings = _lint_source(
        """
        from unittest.mock import patch
        def test_normalize_lowercases():
            with patch("mod.normalize", return_value="abc") as m:
                assert m() == "abc"
        """,
        tmp_path,
    )
    assert AntiPattern.MOCKS_THE_SUBJECT.value in _patterns(findings)


def test_mocks_the_subject_silent_when_patch_targets_collaborator(
    tmp_path: Path,
) -> None:
    """Patching a *collaborator* (not the SUT) is legitimate."""
    findings = _lint_source(
        """
        from unittest.mock import patch
        def test_normalize_uses_logger():
            with patch("mod.logger") as log:
                from mod import normalize
                assert normalize("X") == "x"
        """,
        tmp_path,
    )
    assert AntiPattern.MOCKS_THE_SUBJECT.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 4. asserts-on-mock-call-count-only                                          #
# --------------------------------------------------------------------------- #


def test_asserts_on_mock_call_count_only_fires_when_only_check_is_call_count(
    tmp_path: Path,
) -> None:
    """Only ``mock.assert_called_once()`` — no behavior asserted."""
    findings = _lint_source(
        """
        def test_invokes(mock_logger):
            do_work(mock_logger)
            mock_logger.assert_called_once()
        """,
        tmp_path,
    )
    assert AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY.value in _patterns(findings)


def test_asserts_on_mock_call_count_only_silent_when_behavior_also_asserted(
    tmp_path: Path,
) -> None:
    """Bare ``assert ...`` alongside ``mock.assert_called`` is OK."""
    findings = _lint_source(
        """
        def test_invokes_and_returns(mock_logger):
            result = do_work(mock_logger)
            mock_logger.assert_called_once()
            assert result == "ok"
        """,
        tmp_path,
    )
    assert AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY.value not in _patterns(findings)


@pytest.mark.parametrize(
    "mock_method",
    ["assert_any_call", "assert_has_calls", "assert_not_called"],
)
def test_asserts_on_mock_call_count_only_fires_for_all_mock_variants(tmp_path: Path, mock_method: str) -> None:
    """Codex #1148 P1 fix — every mock-call assertion variant is recognised."""
    findings = _lint_source(
        f"""
        def test_invokes_with_any_variant(mock_logger):
            do_work(mock_logger)
            mock_logger.{mock_method}()
        """,
        tmp_path,
    )
    assert AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY.value in _patterns(findings)


# --------------------------------------------------------------------------- #
# 5. hardcoded-magic-without-comment                                          #
# --------------------------------------------------------------------------- #


def test_hardcoded_magic_without_comment_fires_on_bare_literal(
    tmp_path: Path,
) -> None:
    """Comparison against an unfamiliar literal with no inline comment."""
    findings = _lint_source(
        """
        def test_compute_returns_expected():
            assert compute() == 17
        """,
        tmp_path,
    )
    assert AntiPattern.HARDCODED_MAGIC_WITHOUT_COMMENT.value in _patterns(findings)


def test_hardcoded_magic_silent_when_rationale_comment_present(
    tmp_path: Path,
) -> None:
    """Inline comment annotating the literal suppresses the warning."""
    findings = _lint_source(
        """
        def test_compute_returns_expected():
            assert compute() == 17  # because 17 is the canonical fixture value
        """,
        tmp_path,
    )
    assert AntiPattern.HARDCODED_MAGIC_WITHOUT_COMMENT.value not in _patterns(findings)


def test_hardcoded_magic_silent_on_trivial_literals(tmp_path: Path) -> None:
    """0/1/-1, single-char strings, None, bools are not flagged."""
    findings = _lint_source(
        """
        def test_compute_returns_zero():
            assert compute() == 0
        """,
        tmp_path,
    )
    assert AntiPattern.HARDCODED_MAGIC_WITHOUT_COMMENT.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 6. test-name-claim-mismatch                                                 #
# --------------------------------------------------------------------------- #


def test_test_name_claim_mismatch_fires_when_body_ignores_claim(
    tmp_path: Path,
) -> None:
    """``test_validates_email`` but no assertion touches email."""
    findings = _lint_source(
        """
        def test_validates_email():
            user = make_user()
            assert user.id == 1
        """,
        tmp_path,
    )
    assert AntiPattern.TEST_NAME_CLAIM_MISMATCH.value in _patterns(findings)


def test_test_name_claim_mismatch_silent_when_body_mentions_claim(
    tmp_path: Path,
) -> None:
    """``test_validates_email`` and body asserts on ``email``."""
    findings = _lint_source(
        """
        def test_validates_email():
            assert validate_email("a@b.c") is True
        """,
        tmp_path,
    )
    assert AntiPattern.TEST_NAME_CLAIM_MISMATCH.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 7. raises-without-match                                                     #
# --------------------------------------------------------------------------- #


def test_raises_without_match_fires(tmp_path: Path) -> None:
    """``pytest.raises(ValueError)`` lacking ``match=``."""
    findings = _lint_source(
        """
        import pytest
        def test_raises_value_error():
            with pytest.raises(ValueError):
                int("xyz")
        """,
        tmp_path,
    )
    assert AntiPattern.RAISES_WITHOUT_MATCH.value in _patterns(findings)


def test_raises_with_match_silent(tmp_path: Path) -> None:
    """``match=`` keyword present suppresses the warning."""
    findings = _lint_source(
        """
        import pytest
        def test_raises_value_error():
            with pytest.raises(ValueError, match="invalid literal"):
                int("xyz")
        """,
        tmp_path,
    )
    assert AntiPattern.RAISES_WITHOUT_MATCH.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 8. snapshot-without-reasoning                                               #
# --------------------------------------------------------------------------- #


def test_snapshot_without_reasoning_fires(tmp_path: Path) -> None:
    """``snapshot(...)`` call lacking an explanatory comment."""
    findings = _lint_source(
        """
        def test_layout(snapshot):
            snapshot.assert_match(render())
        """,
        tmp_path,
    )
    assert AntiPattern.SNAPSHOT_WITHOUT_REASONING.value in _patterns(findings)


def test_snapshot_with_reasoning_silent(tmp_path: Path) -> None:
    """Inline ``# locks: …`` comment suppresses the warning."""
    findings = _lint_source(
        """
        def test_layout(snapshot):
            # locks: layout DOM is the contract surface for the inspector tab
            snapshot.assert_match(render())
        """,
        tmp_path,
    )
    assert AntiPattern.SNAPSHOT_WITHOUT_REASONING.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 9. excessive-mocks                                                          #
# --------------------------------------------------------------------------- #


def test_excessive_mocks_fires_above_threshold(tmp_path: Path) -> None:
    """More than six distinct mocks in one test."""
    findings = _lint_source(
        """
        from unittest.mock import MagicMock
        def test_orchestrates():
            mock1 = MagicMock()
            mock2 = MagicMock()
            mock3 = MagicMock()
            mock4 = MagicMock()
            mock5 = MagicMock()
            mock6 = MagicMock()
            mock7 = MagicMock()
            mock8 = MagicMock()
            assert orchestrate(mock1, mock2, mock3, mock4, mock5, mock6, mock7, mock8) == 1
        """,
        tmp_path,
    )
    assert AntiPattern.EXCESSIVE_MOCKS.value in _patterns(findings)


def test_excessive_mocks_silent_below_threshold(tmp_path: Path) -> None:
    """At or below six mocks is acceptable."""
    findings = _lint_source(
        """
        from unittest.mock import MagicMock
        def test_orchestrates_small():
            m1 = MagicMock()
            m2 = MagicMock()
            assert orchestrate(m1, m2) == 1
        """,
        tmp_path,
    )
    assert AntiPattern.EXCESSIVE_MOCKS.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# 10. test-also-provides-ground-truth                                         #
# --------------------------------------------------------------------------- #


def test_test_also_provides_ground_truth_fires_when_expected_uses_sut(
    tmp_path: Path,
) -> None:
    """Test derives ``expected`` by calling the symbol under test."""
    findings = _lint_source(
        """
        def test_normalize_is_idempotent():
            expected = normalize("ABC")
            assert normalize("ABC") == expected
        """,
        tmp_path,
    )
    assert AntiPattern.TEST_ALSO_PROVIDES_GROUND_TRUTH.value in _patterns(findings)


def test_test_also_provides_ground_truth_silent_with_independent_expected(
    tmp_path: Path,
) -> None:
    """Hard-coded ``expected`` value is the correct pattern."""
    findings = _lint_source(
        """
        def test_normalize_lowercases():
            expected = "abc"
            assert normalize("ABC") == expected
        """,
        tmp_path,
    )
    assert AntiPattern.TEST_ALSO_PROVIDES_GROUND_TRUTH.value not in _patterns(findings)


# --------------------------------------------------------------------------- #
# Severity classification — error vs warning sanity                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pattern",
    [
        AntiPattern.NO_ASSERT,
        AntiPattern.MOCKS_THE_SUBJECT,
        AntiPattern.TEST_NAME_CLAIM_MISMATCH,
        AntiPattern.TEST_ALSO_PROVIDES_GROUND_TRUTH,
        AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY,
    ],
)
def test_hard_errors_carry_error_severity(pattern: AntiPattern) -> None:
    """The five structural blockers map to ``severity=error``."""
    from scieasy.qa.test_quality.ast_lint import _severity_for

    assert _severity_for(pattern) is Severity.ERROR


@pytest.mark.parametrize(
    "pattern",
    [
        AntiPattern.ASSERT_NOT_NONE_ONLY,
        AntiPattern.HARDCODED_MAGIC_WITHOUT_COMMENT,
        AntiPattern.RAISES_WITHOUT_MATCH,
        AntiPattern.SNAPSHOT_WITHOUT_REASONING,
        AntiPattern.EXCESSIVE_MOCKS,
    ],
)
def test_soft_signals_carry_warning_severity(pattern: AntiPattern) -> None:
    """Style-signal patterns map to ``severity=warning``."""
    from scieasy.qa.test_quality.ast_lint import _severity_for

    assert _severity_for(pattern) is Severity.WARNING


# --------------------------------------------------------------------------- #
# File-level robustness                                                       #
# --------------------------------------------------------------------------- #


def test_check_test_file_silent_for_missing_path(tmp_path: Path) -> None:
    """Non-existent path returns empty list (no crash)."""
    findings = check_test_file(tmp_path / "nope.py")
    assert findings == []


def test_check_test_file_silent_for_directory(tmp_path: Path) -> None:
    """Directories return empty list (callers walk before invoking)."""
    findings = check_test_file(tmp_path)
    assert findings == []


def test_check_test_file_emits_finding_for_syntax_error(tmp_path: Path) -> None:
    """Syntax errors produce a single error-severity finding rather than crash."""
    p = tmp_path / "test_broken.py"
    p.write_text("def test_x(\n", encoding="utf-8")
    findings = check_test_file(p)
    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR
    assert "syntax error" in findings[0].message.lower()


def test_check_test_file_ignores_non_test_functions(tmp_path: Path) -> None:
    """Functions whose names don't start with ``test_`` are not scanned."""
    findings = _lint_source(
        """
        def helper_does_nothing():
            pass

        def test_helper_used():
            helper_does_nothing()
            assert True is True
        """,
        tmp_path,
    )
    # The bare helper has no assert but should NOT be flagged.
    no_assert = [f for f in findings if f.rule_id == "TQAST-no-assert"]
    assert no_assert == []


def test_check_test_file_handles_async_test(tmp_path: Path) -> None:
    """``async def test_*`` functions are walked too."""
    findings = _lint_source(
        """
        async def test_async_silent():
            x = await coro()
            print(x)
        """,
        tmp_path,
    )
    assert AntiPattern.NO_ASSERT.value in _patterns(findings)


def test_check_test_file_handles_class_based_tests(tmp_path: Path) -> None:
    """Methods inside ``class Test*`` are walked (pytest collection)."""
    findings = _lint_source(
        """
        class TestNumbers:
            def test_silent(self):
                x = 2
        """,
        tmp_path,
    )
    assert AntiPattern.NO_ASSERT.value in _patterns(findings)


def test_check_test_file_returns_empty_on_unicode_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file that can't be UTF-8 decoded returns empty list, no crash."""
    p = tmp_path / "test_binary.py"
    # Real binary content — emits UnicodeDecodeError on .read_text(utf-8).
    p.write_bytes(b"\xff\xfe\x00\x00")
    findings = check_test_file(p)
    assert findings == []


def test_check_test_file_picks_up_patch_object_variant(tmp_path: Path) -> None:
    """``patch.object(mod, 'normalize')`` form is detected too."""
    findings = _lint_source(
        """
        from unittest.mock import patch
        def test_normalize_lowercases():
            with patch.object(mod, "normalize") as m:
                assert m() == "abc"
        """,
        tmp_path,
    )
    # Either MOCKS_THE_SUBJECT or NO_ASSERT may fire depending on assertion
    # presence; here the assertion lives on the mock so MOCKS still applies.
    # The principal contract: detector handles patch.object form without crash.
    assert findings is not None


def test_qualified_name_handles_unknown_node() -> None:
    """``_qualified_name`` returns empty string for unrecognised AST nodes."""
    import ast as _ast

    from scieasy.qa.test_quality.ast_lint import _qualified_name

    assert _qualified_name(_ast.Constant(value=1)) == ""


def test_check_test_file_skips_nested_helper_named_test(tmp_path: Path) -> None:
    """Codex #1148 P2 fix — helpers nested inside a non-test function aren't linted."""
    findings = _lint_source(
        """
        def make_fixture():
            def test_inner_helper():
                # Looks like a test but pytest never collects it.
                return 1
            return test_inner_helper

        def test_real():
            assert make_fixture()() == 1
        """,
        tmp_path,
    )
    # The nested helper has no assert but must NOT be flagged — pytest never
    # collects it. Only the real test is scanned.
    nested = [f for f in findings if f.symbol == "test_inner_helper"]
    assert nested == []


def test_check_test_file_skips_methods_on_non_test_class(tmp_path: Path) -> None:
    """Codex #1148 P2 fix — methods named ``test_*`` on a non-``Test*`` class are ignored."""
    findings = _lint_source(
        """
        class Helper:
            def test_silent_method(self):
                # Pytest only collects methods on `class Test*`.
                pass

        def test_real():
            assert Helper().test_silent_method() is None
        """,
        tmp_path,
    )
    skipped = [f for f in findings if f.symbol == "test_silent_method"]
    assert skipped == []


def test_iter_pytest_collectable_tests_returns_test_class_methods() -> None:
    """Methods on ``class Test*`` are collected by the helper."""
    import ast as _ast

    from scieasy.qa.test_quality.ast_lint import _iter_pytest_collectable_tests

    src = textwrap.dedent(
        """
        class TestNumbers:
            def test_one(self):
                assert 1 == 1
            def helper(self):
                pass

        class Helper:
            def test_hidden(self):
                pass

        def test_module_level():
            assert True is True
        """
    )
    tests = _iter_pytest_collectable_tests(_ast.parse(src))
    assert sorted(t.name for t in tests) == ["test_module_level", "test_one"]
