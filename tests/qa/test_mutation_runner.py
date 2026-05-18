"""Unit tests for the TC-1F.3 mutation runner (ADR-043 §4.5).

The runner shells out to ``mutmut``. Every subprocess call funnels
through :func:`scieasy.qa.test_quality.mutation_runner._run_capture`,
so the tests below patch that one symbol to drive synthetic mutation
results into the parser without needing ``mutmut`` installed.

Coverage target: ≥ 95% on
``src/scieasy/qa/test_quality/mutation_runner.py`` per ADR-043 §4.5 +
the cascade dispatch prompt's Definition of Done.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from scieasy.qa.schemas.report import Severity
from scieasy.qa.test_quality import mutation_runner as mr

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


class _Recorder:
    """Capture `_run_capture` invocations and return scripted results.

    Each entry in ``script`` is a ``(rc, stdout, stderr)`` triple
    returned in order. If the test issues more calls than the script
    has entries, the last entry is reused (mirrors mutmut's idempotent
    ``results`` invocation when called repeatedly).
    """

    def __init__(self, script: Sequence[tuple[int, str, str]]):
        self.script = list(script)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> tuple[int, str, str]:
        self.calls.append(tuple(args))
        if not self.script:
            return 0, "", ""
        if len(self.calls) <= len(self.script):
            return self.script[len(self.calls) - 1]
        return self.script[-1]


@pytest.fixture
def patch_capture(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_run_capture`` AND ``shutil.which('mutmut')`` to "installed"."""

    def install(script: Sequence[tuple[int, str, str]]) -> _Recorder:
        recorder = _Recorder(script)
        monkeypatch.setattr(mr, "_run_capture", recorder)
        # `run_targeted` queries `shutil.which("mutmut")` before
        # invoking the recorder. Stub the lookup to a non-None value
        # so the tool-missing branch only fires in tests that want it.
        monkeypatch.setattr(mr.shutil, "which", lambda name: f"/usr/bin/{name}")
        # Force Linux platform so the Windows guard does not short-circuit.
        monkeypatch.setattr(mr, "_is_windows", lambda: False)
        return recorder

    return install


# --------------------------------------------------------------------------- #
# Threshold resolution                                                        #
# --------------------------------------------------------------------------- #


class TestResolveThreshold:
    """`_resolve_threshold` returns the ADR-043 §4.5 path-target value."""

    def test_qa_exact_prefix_matches_0_90(self) -> None:
        assert mr._resolve_threshold("src/scieasy/qa") == 0.90

    def test_qa_subpath_inherits_0_90(self) -> None:
        # Behavior: a nested module under qa inherits the qa target.
        assert mr._resolve_threshold("src/scieasy/qa/test_quality/ast_lint.py") == 0.90

    def test_core_target_is_0_85(self) -> None:
        assert mr._resolve_threshold("src/scieasy/core/storage/zarr_backend.py") == 0.85

    def test_blocks_target_is_0_75(self) -> None:
        assert mr._resolve_threshold("src/scieasy/blocks/io/loaders/load_data.py") == 0.75

    def test_ai_target_is_0_70(self) -> None:
        assert mr._resolve_threshold("src/scieasy/ai/llm_client.py") == 0.70

    def test_unknown_path_returns_none(self) -> None:
        # Behavior: paths outside the named four families have NO target
        # per ADR-043 §4.5 "Other — no target" row.
        assert mr._resolve_threshold("scripts/audit/temp_review.py") is None

    def test_windows_backslash_normalises(self) -> None:
        # Behavior: callers passing Windows paths still resolve correctly.
        assert mr._resolve_threshold("src\\scieasy\\qa\\test_quality") == 0.90

    def test_leading_dot_slash_is_stripped(self) -> None:
        assert mr._resolve_threshold("./src/scieasy/qa") == 0.90

    def test_trailing_slash_ignored(self) -> None:
        assert mr._resolve_threshold("src/scieasy/qa/") == 0.90

    def test_prefix_collision_isolated(self) -> None:
        # A path that merely shares a prefix prefix (e.g. "src/scieasy/qa_other")
        # MUST NOT inherit the qa target — `_resolve_threshold` only
        # matches exact dir-boundaries.
        assert mr._resolve_threshold("src/scieasy/qa_other/foo.py") is None


# --------------------------------------------------------------------------- #
# Score computation                                                           #
# --------------------------------------------------------------------------- #


class TestComputeScore:
    """`_compute_score` returns ``(total, killed/total)`` with zero-safe."""

    def test_basic_division(self) -> None:
        total, score = mr._compute_score(killed=9, survived=1, timeout=0)
        assert total == 10
        assert score == pytest.approx(0.9)

    def test_zero_total_yields_score_one(self) -> None:
        # Behavior: a module with zero mutations is trivially "passing"
        # — there's nothing to kill. Documented in module docstring.
        total, score = mr._compute_score(0, 0, 0)
        assert total == 0
        assert score == 1.0

    def test_timeout_counts_against_score(self) -> None:
        # Behavior: timeouts increase the denominator without crediting
        # the kill count — they're "unkilled" for scoring purposes.
        total, score = mr._compute_score(killed=8, survived=1, timeout=1)
        assert total == 10
        assert score == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# Results-payload parsing                                                     #
# --------------------------------------------------------------------------- #


class TestParseResultsPayload:
    """Both JSON and plaintext mutmut result formats parse correctly."""

    def test_json_form_recognised(self) -> None:
        parsed = mr._parse_results_payload(json.dumps({"killed": 9, "survived": 1, "timeout": 0}))
        assert parsed == (9, 1, 0)

    def test_json_timed_out_alias(self) -> None:
        # Behavior: older mutmut JSON variant used "timed_out" instead
        # of "timeout"; the parser accepts either spelling.
        parsed = mr._parse_results_payload(json.dumps({"killed": 5, "survived": 0, "timed_out": 2}))
        assert parsed == (5, 0, 2)

    def test_plaintext_form_recognised(self) -> None:
        text = "Killed: 18\nSurvived: 2\nTimeout: 0\n"
        assert mr._parse_results_payload(text) == (18, 2, 0)

    def test_plaintext_with_timed_out_alias(self) -> None:
        text = "Killed: 4\nSurvived: 1\nTimed out: 1\n"
        assert mr._parse_results_payload(text) == (4, 1, 1)

    def test_empty_payload_returns_none(self) -> None:
        assert mr._parse_results_payload("") is None
        assert mr._parse_results_payload("   \n   \n") is None

    def test_unparseable_payload_returns_none(self) -> None:
        # Behavior: garbled output yields None so the caller emits a
        # ``TQMUT-parse-failed`` finding rather than crashing.
        assert mr._parse_results_payload("definitely not JSON\nnor counts\n") is None

    def test_plaintext_invalid_number_skipped(self) -> None:
        # Behavior: one malformed line does not poison the entire parse.
        text = "Killed: nope\nSurvived: 2\nTimeout: 0\n"
        assert mr._parse_results_payload(text) == (0, 2, 0)

    def test_plaintext_invalid_survived_skipped(self) -> None:
        # Behavior: same tolerance applied to the Survived: line — the
        # parser does not abandon counts that were already extracted.
        text = "Killed: 5\nSurvived: bogus\nTimeout: 0\n"
        assert mr._parse_results_payload(text) == (5, 0, 0)

    def test_plaintext_invalid_timeout_skipped(self) -> None:
        # Behavior: same tolerance applied to the Timeout: line.
        text = "Killed: 5\nSurvived: 1\nTimeout: notanumber\n"
        assert mr._parse_results_payload(text) == (5, 1, 0)

    def test_non_dict_json_falls_through(self) -> None:
        # Behavior: JSON list payload is not a valid results envelope;
        # parser falls back to plaintext scan and returns None.
        assert mr._parse_results_payload("[1, 2, 3]") is None


# --------------------------------------------------------------------------- #
# Baseline JSON loading                                                       #
# --------------------------------------------------------------------------- #


class TestLoadBaseline:
    """`_load_baseline` is tolerant: missing files yield empty dict."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert mr._load_baseline(tmp_path / "does-not-exist.json") == {}

    def test_flat_score_form(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"src/scieasy/qa": 0.92}))
        assert mr._load_baseline(path) == {"src/scieasy/qa": 0.92}

    def test_nested_score_form(self, tmp_path: Path) -> None:
        # Behavior: {"<mod>": {"score": 0.X}} form (matches ADR-043 §4.5).
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"src/scieasy/qa": {"score": 0.93, "captured_at": "now"}}))
        assert mr._load_baseline(path) == {"src/scieasy/qa": 0.93}

    def test_top_level_non_dict_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        path.write_text("[1, 2, 3]")
        assert mr._load_baseline(path) == {}

    def test_inner_value_non_numeric_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"a": "not-a-number", "b": 0.5}))
        assert mr._load_baseline(path) == {"b": 0.5}


# --------------------------------------------------------------------------- #
# Baseline-score lookup                                                       #
# --------------------------------------------------------------------------- #


class TestBaselineScoreFor:
    """`_baseline_score_for` matches exact key or longest prefix."""

    def test_exact_key_wins(self) -> None:
        baseline = {"src/scieasy/qa": 0.92, "src/scieasy": 0.80}
        assert mr._baseline_score_for("src/scieasy/qa", baseline) == 0.92

    def test_longest_prefix_wins(self) -> None:
        # Behavior: when the exact key is absent, the longest matching
        # prefix wins (so a deep module doesn't accidentally pick up
        # a shallow ancestor's lower bar).
        baseline = {"src/scieasy": 0.80, "src/scieasy/qa": 0.92}
        assert mr._baseline_score_for("src/scieasy/qa/test_quality", baseline) == 0.92

    def test_no_match_returns_none(self) -> None:
        baseline = {"src/scieasy/qa": 0.92}
        assert mr._baseline_score_for("scripts/audit", baseline) is None


# --------------------------------------------------------------------------- #
# `run_targeted` — end-to-end orchestration                                   #
# --------------------------------------------------------------------------- #


class TestRunTargeted:
    """The public entry point covers all branches of the orchestration."""

    def test_windows_short_circuits_with_one_finding(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Behavior: ADR-043 §4.5 confines mutation to Linux/macOS. The
        # runner emits one INFO finding under TQMUT-unavailable-platform
        # and SKIPS subprocess invocation entirely.
        monkeypatch.setattr(mr, "_is_windows", lambda: True)

        # Spy: assert _run_capture is never reached on Windows.
        called: list[Sequence[str]] = []
        monkeypatch.setattr(mr, "_run_capture", lambda args: called.append(args) or (0, "", ""))

        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "baseline.json")

        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_UNAVAILABLE_PLATFORM
        assert findings[0].severity is Severity.INFO
        assert called == []

    def test_tool_missing_short_circuits(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Behavior: when mutmut is absent from PATH, the runner emits one
        # INFO finding and skips the per-module loop.
        monkeypatch.setattr(mr, "_is_windows", lambda: False)
        monkeypatch.setattr(mr.shutil, "which", lambda name: None)

        called: list[Sequence[str]] = []
        monkeypatch.setattr(mr, "_run_capture", lambda args: called.append(args) or (0, "", ""))

        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "baseline.json")

        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_TOOL_MISSING
        assert findings[0].severity is Severity.INFO
        assert called == []

    def test_below_threshold_emits_warning(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a module scoring below its §4.5 target emits one
        # WARNING-level TQMUT-below-threshold finding citing the score
        # and the threshold.
        script = [
            (0, "ok", ""),  # mutmut run --paths-to-mutate
            (0, json.dumps({"killed": 8, "survived": 2, "timeout": 0}), ""),  # mutmut results
        ]
        patch_capture(script)

        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == mr._RULE_BELOW_THRESHOLD
        assert f.severity is Severity.WARNING
        assert f.file == "src/scieasy/qa"
        assert "0.800" in f.message  # score formatted to 3dp
        assert "0.90" in f.message  # target formatted to 2dp

    def test_at_or_above_threshold_emits_nothing(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a module meeting its target produces an empty finding
        # list — the silent-success case.
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 9, "survived": 1, "timeout": 0}), ""),
        ]
        patch_capture(script)

        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")
        assert findings == []

    def test_no_target_module_emits_info(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a module outside the §4.5 table emits one INFO
        # finding and SKIPS the mutmut invocation entirely.
        recorder = patch_capture([])
        findings = mr.run_targeted(["scripts/audit/temp_review.py"], tmp_path / "missing.json")
        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_NO_TARGET
        assert findings[0].severity is Severity.INFO
        assert recorder.calls == []  # mutmut never invoked

    def test_run_failed_emits_warning(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: when `mutmut run` returns an unexpected exit code
        # (e.g. 3 = config error), the runner emits TQMUT-run-failed
        # and moves on without invoking `mutmut results`.
        script = [(3, "", "config: missing setup.cfg")]
        recorder = patch_capture(script)

        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")
        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_RUN_FAILED
        assert findings[0].severity is Severity.WARNING
        assert "rc=3" in findings[0].message
        # Behavior: results invocation was NOT issued after the failure.
        assert len(recorder.calls) == 1
        assert recorder.calls[0][0:2] == ("mutmut", "run")

    def test_results_failure_emits_warning(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: `mutmut run` succeeds (rc=0 or 2) but `mutmut results`
        # exits non-zero — the parser path is skipped and the runner
        # emits TQMUT-run-failed for the results step.
        script = [
            (0, "ok", ""),  # run
            (5, "", "results: no cache"),  # results
        ]
        patch_capture(script)
        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")
        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_RUN_FAILED

    def test_parse_failed_emits_warning(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: `mutmut results` returns garbage that neither JSON
        # nor plaintext heuristics accept; runner emits a parse-failed
        # finding instead of crashing.
        script = [
            (0, "ok", ""),
            (0, "??? not real output ???", ""),
        ]
        patch_capture(script)
        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")
        assert len(findings) == 1
        assert findings[0].rule_id == mr._RULE_PARSE_FAILED

    def test_run_rc_2_is_accepted_as_success(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: mutmut historically returns 2 from `run` when some
        # mutants survive — both 0 and 2 must reach the parser.
        script = [
            (2, "some survived", ""),  # rc=2 from run
            (0, json.dumps({"killed": 9, "survived": 1, "timeout": 0}), ""),
        ]
        patch_capture(script)
        findings = mr.run_targeted(["src/scieasy/qa"], tmp_path / "missing.json")
        # Score 0.9 == target 0.90 → no below-threshold finding.
        assert findings == []

    def test_baseline_regression_emits_info(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a module that scored higher historically (baseline
        # 0.95) but now scores 0.92 — still ABOVE the §4.5 target of
        # 0.90 — emits a INFO-level TQMUT-baseline-regression finding.
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({"src/scieasy/qa": 0.95}))
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 92, "survived": 8, "timeout": 0}), ""),
        ]
        patch_capture(script)

        findings = mr.run_targeted(["src/scieasy/qa"], baseline_path)
        # Should be exactly one INFO regression finding; the score 0.92
        # is above the 0.90 target so no below-threshold finding.
        assert [f.rule_id for f in findings] == [mr._RULE_BASELINE_REGRESSION]
        assert findings[0].severity is Severity.INFO

    def test_baseline_below_target_emits_both_findings(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a score BELOW the target AND below baseline emits
        # both findings (below-threshold + regression) so dashboards
        # can distinguish "stable below target" from "still falling".
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({"src/scieasy/qa": 0.92}))
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 80, "survived": 20, "timeout": 0}), ""),
        ]
        patch_capture(script)

        findings = mr.run_targeted(["src/scieasy/qa"], baseline_path)
        ids = sorted(f.rule_id for f in findings)
        assert ids == sorted([mr._RULE_BELOW_THRESHOLD, mr._RULE_BASELINE_REGRESSION])

    def test_baseline_equal_or_better_no_regression(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: when current score matches or exceeds baseline, no
        # regression finding emitted (so the dashboard isn't spammed
        # by floor-level wiggles).
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({"src/scieasy/qa": 0.92}))
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 92, "survived": 8, "timeout": 0}), ""),
        ]
        patch_capture(script)
        findings = mr.run_targeted(["src/scieasy/qa"], baseline_path)
        # Same score 0.92 vs baseline 0.92 → no regression.
        assert findings == []

    def test_malformed_baseline_emits_parse_failed_then_continues(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: a malformed baseline JSON does NOT abort the run —
        # it emits a TQMUT-parse-failed finding for the baseline file
        # and continues with no regression check.
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text("{ this is not valid JSON")
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 9, "survived": 1, "timeout": 0}), ""),
        ]
        patch_capture(script)
        findings = mr.run_targeted(["src/scieasy/qa"], baseline_path)
        ids = [f.rule_id for f in findings]
        assert mr._RULE_PARSE_FAILED in ids
        # Module score 0.9 meets target 0.90 → no below-threshold finding.
        assert mr._RULE_BELOW_THRESHOLD not in ids

    def test_multiple_modules_each_assessed_independently(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: each module gets its own mutmut run + results pair
        # AND its own threshold lookup; the loop is independent.
        # Module A (qa, target 0.90, score 0.85) → below-threshold.
        # Module B (core, target 0.85, score 0.85) → exactly at target,
        #   no finding.
        script = [
            (0, "ok", ""),
            (0, json.dumps({"killed": 85, "survived": 15, "timeout": 0}), ""),  # qa: 0.85 < 0.90
            (0, "ok", ""),
            (0, json.dumps({"killed": 85, "survived": 15, "timeout": 0}), ""),  # core: 0.85 == 0.85
        ]
        patch_capture(script)
        findings = mr.run_targeted(
            ["src/scieasy/qa", "src/scieasy/core"],
            tmp_path / "missing.json",
        )
        # Exactly one finding (qa); core meets target.
        assert len(findings) == 1
        assert findings[0].file == "src/scieasy/qa"
        assert findings[0].rule_id == mr._RULE_BELOW_THRESHOLD

    def test_empty_modules_list_emits_no_findings(self, patch_capture, tmp_path: Path) -> None:
        # Behavior: empty input → empty output; not an error.
        recorder = patch_capture([])
        findings = mr.run_targeted([], tmp_path / "missing.json")
        assert findings == []
        assert recorder.calls == []


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #


class TestRuleIds:
    """`RULE_IDS` exposes every rule the module can emit."""

    def test_set_contains_all_internal_constants(self) -> None:
        # Behavior: keep RULE_IDS in sync with the private _RULE_*
        # constants so SARIF / annotation consumers can iterate
        # without re-importing names.
        expected = {
            mr._RULE_BELOW_THRESHOLD,
            mr._RULE_BASELINE_REGRESSION,
            mr._RULE_UNAVAILABLE_PLATFORM,
            mr._RULE_TOOL_MISSING,
            mr._RULE_RUN_FAILED,
            mr._RULE_PARSE_FAILED,
            mr._RULE_NO_TARGET,
        }
        assert expected == mr.RULE_IDS

    def test_every_id_uses_tqmut_namespace(self) -> None:
        # Behavior: matches the TQAST / TQTF / TQMUT namespace
        # convention established in ADR-043 §4 + Sub-PR 1.
        for rule_id in mr.RULE_IDS:
            assert rule_id.startswith("TQMUT-"), rule_id


# --------------------------------------------------------------------------- #
# Subprocess seam                                                             #
# --------------------------------------------------------------------------- #


class TestRunCapture:
    """`_run_capture` is the single subprocess seam."""

    def test_empty_args_returns_config_error(self) -> None:
        rc, stdout, stderr = mr._run_capture([])
        assert rc == 2
        assert stdout == ""
        assert "no command" in stderr

    def test_missing_executable_returns_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Behavior: command not on PATH → rc=2, descriptive stderr;
        # no subprocess actually spawned.
        monkeypatch.setattr(mr.shutil, "which", lambda name: None)
        rc, stdout, stderr = mr._run_capture(["nonexistent-tool-xyz", "--help"])
        assert rc == 2
        assert stdout == ""
        assert "not on PATH" in stderr

    def test_is_windows_returns_bool(self) -> None:
        # Behavior: the platform helper exists primarily as a
        # monkeypatch seam; smoke-test the un-patched form so the
        # line is exercised on real runners.
        import sys as _sys

        result = mr._is_windows()
        assert isinstance(result, bool)
        assert result == (_sys.platform == "win32")

    def test_real_subprocess_smoke(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Smoke: verify the wrapper actually shells out when PATH ok.
        # Use ``python -c`` since python is always present in CI.
        import sys as _sys

        monkeypatch.setattr(mr.shutil, "which", lambda name: _sys.executable)
        rc, stdout, _stderr = mr._run_capture([_sys.executable, "-c", "print('hello')"])
        assert rc == 0
        assert stdout.strip() == "hello"
