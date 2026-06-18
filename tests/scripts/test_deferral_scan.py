"""Tests for ``scripts/deferral_scan.py``.

Covers the pure-Python pieces: per-line hit detection, tracking-reference
exemption, central EXCLUSIONS, whole-repo ratchet check, baseline schema,
and the unified-diff parser / diff gate (git shelled out, monkeypatched).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deferral_scan.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("deferral_scan", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["deferral_scan"] = module
    spec.loader.exec_module(module)
    return module


class TestHitDetection:
    def test_untracked_deferral_flagged(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# just fix this for now")
        assert [h.phrase for h in hits] == ["for_now"]
        assert hits[0].tracked is False

    def test_tracked_when_issue_ref_present(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# placeholder, real impl later -- TODO(#1602)")
        assert hits and all(h.tracked for h in hits)

    def test_word_boundary_skips_identifiers(self, mod):
        # ``placeholder_text`` / ``compute_later_value`` are identifiers, not prose.
        assert mod._hits_in_line("a.py", 1, "placeholder_text = compute_later_value()") == []

    def test_bare_todo_is_untracked(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# TODO: implement")
        assert [h.phrase for h in hits] == ["todo"]
        assert hits[0].tracked is False

    def test_todo_with_issue_is_tracked(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# TODO(#42): implement")
        assert hits[0].phrase == "todo"
        assert hits[0].tracked is True

    def test_adr_reference_counts_as_tracked(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# placeholder -- out of scope per ADR-040 section 3")
        assert hits and all(h.tracked for h in hits)


class TestExclusions:
    def test_tempfile_collocation_excluded(self, mod):
        assert mod._hits_in_line("a.py", 1, "with tempfile.NamedTemporaryFile() as f:") == []

    def test_temporary_prose_still_flagged(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# temporary overflow, just surface it")
        assert [h.phrase for h in hits] == ["temporary"]

    def test_placeholder_kwarg_excluded(self, mod):
        assert mod._hits_in_line("a.py", 1, 'field(placeholder="Enter name")') == []

    def test_placeholder_prose_flagged(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# this is a placeholder, real body lands later")
        assert "placeholder" in [h.phrase for h in hits]

    def test_api_v1_path_excluded(self, mod):
        assert mod._hits_in_line("a.py", 1, '@router.get("/api/v1/workflows")') == []

    def test_v1_prose_flagged(self, mod):
        hits = mod._hits_in_line("a.py", 1, "# fine for v1; a real impl can replace it")
        assert "v1" in [h.phrase for h in hits]


class TestRatchetCheck:
    @staticmethod
    def _baseline(total, by_phrase):
        return {
            "current": {"untracked_total": total},
            "ratchet": {"max_untracked_total": total, "max_by_phrase": dict(by_phrase)},
        }

    def test_pass_when_equal(self, mod):
        b = self._baseline(2, {"later": 2})
        m = {"untracked_total": 2, "by_phrase": {"later": 2}}
        assert mod._check_against_baseline(b, m) == []

    def test_pass_when_below(self, mod):
        b = self._baseline(5, {"later": 5})
        m = {"untracked_total": 3, "by_phrase": {"later": 3}}
        assert mod._check_against_baseline(b, m) == []

    def test_fail_on_total_growth(self, mod):
        b = self._baseline(2, {"later": 2})
        m = {"untracked_total": 3, "by_phrase": {"later": 3}}
        violations = mod._check_against_baseline(b, m)
        assert any("untracked deferrals" in v for v in violations)

    def test_fail_on_new_phrase_even_when_total_flat(self, mod):
        # total unchanged (2) but a never-seen phrase appears -> per-phrase cap 0.
        b = self._baseline(2, {"later": 2})
        m = {"untracked_total": 2, "by_phrase": {"later": 1, "hack": 1}}
        violations = mod._check_against_baseline(b, m)
        assert any("hack" in v for v in violations)


class TestBaselineSchema:
    def test_build_baseline_shape(self, mod):
        metrics = {"untracked_total": 7, "tracked_total": 3, "by_phrase": {"later": 4, "v1": 3}}
        baseline = mod._build_baseline(Path("src/scistudio"), metrics)
        for key in ("schema_version", "captured_at", "config", "current", "ratchet", "ratchet_policy"):
            assert key in baseline
        # No headroom: the ceiling equals current (debt may shrink, never grow).
        assert baseline["ratchet"]["max_untracked_total"] == metrics["untracked_total"]
        assert baseline["ratchet"]["max_by_phrase"] == metrics["by_phrase"]
        assert json.loads(json.dumps(baseline)) == baseline


class TestScanTree:
    def test_counts_tracked_and_untracked(self, mod, tmp_path):
        (tmp_path / "a.py").write_text(
            "# this is a placeholder for now\n# tracked later TODO(#1)\n",
            encoding="utf-8",
        )
        metrics = mod._metrics(mod.scan_tree(tmp_path, tmp_path))
        assert metrics["untracked_total"] >= 1
        assert metrics["tracked_total"] >= 1


class TestDiffGate:
    _DIFF = (
        "diff --git a/src/scistudio/x.py b/src/scistudio/x.py\n"
        "--- a/src/scistudio/x.py\n"
        "+++ b/src/scistudio/x.py\n"
        "@@ -10,0 +11,2 @@\n"
        "+# placeholder for now\n"
        "+# TODO(#1602): real impl\n"
    )

    def test_diff_added_lines_parses_paths_and_linenos(self, mod, monkeypatch):
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=self._DIFF))
        added = mod._diff_added_lines("origin/main", Path("."))
        assert added == [
            ("src/scistudio/x.py", 11, "# placeholder for now"),
            ("src/scistudio/x.py", 12, "# TODO(#1602): real impl"),
        ]

    def test_diff_gate_fails_on_new_untracked(self, mod, monkeypatch, capsys):
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=self._DIFF))
        rc = mod._run_diff_gate("origin/main", Path("."), "src/scistudio/")
        assert rc == 1
        err = capsys.readouterr().err
        assert "placeholder" in err or "for_now" in err

    def test_diff_gate_passes_when_only_tracked(self, mod, monkeypatch):
        diff = "+++ b/src/scistudio/x.py\n@@ -1,0 +1,1 @@\n+# TODO(#1602): tracked deferral later\n"
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=diff))
        assert mod._run_diff_gate("origin/main", Path("."), "src/scistudio/") == 0

    def test_diff_gate_ignores_paths_outside_root(self, mod, monkeypatch):
        diff = "+++ b/scripts/x.py\n@@ -1,0 +1,1 @@\n+# placeholder for now\n"
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=diff))
        assert mod._run_diff_gate("origin/main", Path("."), "src/scistudio/") == 0
