"""Tests for ``scripts/semantic_dup_scan.py``.

Covers the pure-Python pieces (AST extraction, docstring stripping,
union-find clustering, ratchet violation detection, JSON baseline
schema). The embedding model itself is not invoked from unit tests;
CI exercises the end-to-end embedding path on real source via the
ratchet-check workflow.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "semantic_dup_scan.py"


@pytest.fixture(scope="module")
def scan_mod():
    spec = importlib.util.spec_from_file_location("semantic_dup_scan", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["semantic_dup_scan"] = module
    spec.loader.exec_module(module)
    return module


def _write_py(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


class TestExtractFunctions:
    def test_extracts_top_level_function(self, scan_mod, tmp_path):
        _write_py(
            tmp_path,
            "a.py",
            "def foo(x):\n    y = x + 1\n    z = y * 2\n    return z\n    return z\n",
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=5, repo_root=tmp_path)
        assert len(funcs) == 1
        assert funcs[0].qualname == "foo"
        assert funcs[0].loc == 5

    def test_filters_below_min_loc(self, scan_mod, tmp_path):
        _write_py(tmp_path, "a.py", "def tiny():\n    return 1\n")
        funcs = scan_mod.extract_functions(tmp_path, min_loc=5, repo_root=tmp_path)
        assert funcs == []

    def test_extracts_methods_with_class_qualname(self, scan_mod, tmp_path):
        _write_py(
            tmp_path,
            "a.py",
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            x = 1\n"
            "            y = 2\n"
            "            z = 3\n"
            "            return x + y + z\n",
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=5, repo_root=tmp_path)
        assert len(funcs) == 1
        assert funcs[0].qualname == "Outer.Inner.method"

    def test_skips_pycache(self, scan_mod, tmp_path):
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        _write_py(
            cache_dir,
            "a.py",
            "def foo():\n    return 1\n    return 1\n    return 1\n    return 1\n",
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=5, repo_root=tmp_path)
        assert funcs == []

    def test_handles_unparseable_file(self, scan_mod, tmp_path):
        _write_py(tmp_path, "bad.py", "this is not valid python (\n")
        _write_py(
            tmp_path,
            "good.py",
            "def good():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n",
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=5, repo_root=tmp_path)
        assert [f.qualname for f in funcs] == ["good"]

    def test_path_is_relative_to_repo_root(self, scan_mod, tmp_path):
        sub = tmp_path / "src" / "pkg"
        sub.mkdir(parents=True)
        _write_py(
            sub,
            "mod.py",
            "def f():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n",
        )
        funcs = scan_mod.extract_functions(sub, min_loc=5, repo_root=tmp_path)
        assert funcs[0].path == Path("src/pkg/mod.py") or funcs[0].path.as_posix() == "src/pkg/mod.py"


class TestStripDocstring:
    def test_strips_docstring_from_source(self, scan_mod, tmp_path):
        _write_py(
            tmp_path,
            "a.py",
            'def foo():\n    """A docstring that should be excluded."""\n    a = 1\n    b = 2\n    return a + b\n',
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=4, repo_root=tmp_path)
        assert len(funcs) == 1
        assert "docstring that should be excluded" not in funcs[0].source
        assert "a = 1" in funcs[0].source

    def test_keeps_string_constant_that_is_not_first_statement(self, scan_mod, tmp_path):
        _write_py(
            tmp_path,
            "a.py",
            'def foo():\n    a = 1\n    msg = "not a docstring"\n    b = 2\n    return a + b\n',
        )
        funcs = scan_mod.extract_functions(tmp_path, min_loc=4, repo_root=tmp_path)
        assert "not a docstring" in funcs[0].source


class TestCluster:
    def test_isolates_dissimilar_pairs(self, scan_mod):
        sim = np.array(
            [
                [0.0, 0.5, 0.4],
                [0.5, 0.0, 0.3],
                [0.4, 0.3, 0.0],
            ]
        )
        clusters = scan_mod._cluster(sim, threshold=0.9)
        assert clusters == []

    def test_groups_above_threshold(self, scan_mod):
        sim = np.array(
            [
                [0.0, 0.95, 0.10],
                [0.95, 0.0, 0.20],
                [0.10, 0.20, 0.0],
            ]
        )
        clusters = scan_mod._cluster(sim, threshold=0.9)
        assert len(clusters) == 1
        assert sorted(clusters[0]) == [0, 1]

    def test_transitive_merging(self, scan_mod):
        sim = np.array(
            [
                [0.0, 0.95, 0.30],
                [0.95, 0.0, 0.95],
                [0.30, 0.95, 0.0],
            ]
        )
        clusters = scan_mod._cluster(sim, threshold=0.9)
        assert len(clusters) == 1
        assert sorted(clusters[0]) == [0, 1, 2]


class TestRatchetCheck:
    def _baseline(self, **overrides):
        b = {
            "schema_version": 1,
            "current": {
                "clusters": 60,
                "duplicate_pct": 10.0,
                "max_cluster_size": 9,
                "duplicate_loc": 3474,
            },
            "ratchet": {
                "max_clusters": 63,
                "max_duplicate_pct": 10.5,
                "max_cluster_size": 9,
                "max_duplicate_loc": 3647,
            },
        }
        for k, v in overrides.items():
            b["ratchet"][k] = v
        return b

    def test_pass_when_under_all_ratchets(self, scan_mod):
        baseline = self._baseline()
        metrics = {
            "clusters": 60,
            "duplicate_pct": 10.0,
            "max_cluster_size": 9,
            "duplicate_loc": 3474,
        }
        assert scan_mod._check_against_baseline(baseline, metrics) == []

    def test_fail_on_cluster_count_regression(self, scan_mod):
        baseline = self._baseline()
        metrics = {
            "clusters": 64,
            "duplicate_pct": 10.0,
            "max_cluster_size": 9,
            "duplicate_loc": 3474,
        }
        violations = scan_mod._check_against_baseline(baseline, metrics)
        assert len(violations) == 1
        assert "cluster count" in violations[0]

    def test_fail_on_cluster_size_regression(self, scan_mod):
        baseline = self._baseline()
        metrics = {
            "clusters": 60,
            "duplicate_pct": 10.0,
            "max_cluster_size": 10,
            "duplicate_loc": 3474,
        }
        violations = scan_mod._check_against_baseline(baseline, metrics)
        assert len(violations) == 1
        assert "largest cluster" in violations[0]

    def test_fail_reports_all_simultaneous_violations(self, scan_mod):
        baseline = self._baseline()
        metrics = {
            "clusters": 64,
            "duplicate_pct": 11.0,
            "max_cluster_size": 10,
            "duplicate_loc": 3700,
        }
        violations = scan_mod._check_against_baseline(baseline, metrics)
        assert len(violations) == 4

    def test_pass_at_exact_ratchet_limit(self, scan_mod):
        baseline = self._baseline()
        metrics = {
            "clusters": 63,
            "duplicate_pct": 10.5,
            "max_cluster_size": 9,
            "duplicate_loc": 3647,
        }
        assert scan_mod._check_against_baseline(baseline, metrics) == []


class TestBaselineJsonSchema:
    def test_build_baseline_has_required_top_level_keys(self, scan_mod):
        class Args:
            root = Path("src/scistudio")
            model = "BAAI/bge-base-en-v1.5"
            threshold = 0.92
            min_loc = 5

        metrics = {
            "functions_scanned": 1248,
            "clusters": 60,
            "duplicate_loc": 3474,
            "total_loc": 34636,
            "duplicate_pct": 10.03,
            "max_cluster_size": 9,
        }
        baseline = scan_mod._build_baseline(Args(), metrics)
        for key in ("schema_version", "captured_at", "config", "current", "ratchet", "ratchet_policy"):
            assert key in baseline
        for key in ("max_clusters", "max_duplicate_pct", "max_cluster_size", "max_duplicate_loc"):
            assert key in baseline["ratchet"]
        # ratchet should have headroom on count + loc, no headroom on size
        assert baseline["ratchet"]["max_clusters"] >= metrics["clusters"]
        assert baseline["ratchet"]["max_cluster_size"] == metrics["max_cluster_size"]
        # round-trip JSON to confirm serialisable
        assert json.loads(json.dumps(baseline)) == baseline
