"""Tests for conservative change-contract reachability helpers (#1620)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from scistudio.qa.audit.change_contract_reachability import (
    ReachabilityRequirement,
    build_frontend_import_graph,
    build_python_import_graph,
    collect_python_entry_points,
    evaluate_reachability,
)


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def test_python_module_reachable_from_declared_production_root(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app" / "__init__.py")
    _write(tmp_path / "src" / "app" / "main.py", "from app import feature")
    _write(tmp_path / "src" / "app" / "feature.py", "VALUE = 1")

    graph = build_python_import_graph(tmp_path)
    result = evaluate_reachability(
        tmp_path,
        [ReachabilityRequirement(kind="python_module", target="app.feature")],
        python_roots=("app.main",),
    )

    assert graph.reachable_path("app.feature", ("app.main",)) == ("app.main", "app.feature")
    assert result.findings == ()
    assert result.evidence[0].status == "reachable"


def test_python_module_imported_only_by_tests_is_unreachable(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app" / "__init__.py")
    _write(tmp_path / "src" / "app" / "main.py", "VALUE = 1")
    _write(tmp_path / "src" / "app" / "orphan.py", "VALUE = 2")
    _write(tmp_path / "tests" / "test_orphan.py", "from app import orphan")

    result = evaluate_reachability(
        tmp_path,
        [ReachabilityRequirement(kind="python_module", target="app.orphan")],
        python_roots=("app.main",),
    )

    assert [finding.rule_id for finding in result.findings] == [
        "change-contract.reachability.python-module-unreachable"
    ]
    assert result.findings[0].evidence == {"target": "app.orphan", "roots": ("app.main",)}


def test_frontend_component_reachable_from_declared_ui_root(tmp_path: Path) -> None:
    _write(tmp_path / "frontend" / "src" / "main.tsx", 'import App from "./App";')
    _write(tmp_path / "frontend" / "src" / "App.tsx", 'import { Feature } from "./components/Feature";')
    _write(tmp_path / "frontend" / "src" / "components" / "Feature.tsx", "export function Feature() { return null; }")

    graph = build_frontend_import_graph(tmp_path)
    result = evaluate_reachability(
        tmp_path,
        [
            ReachabilityRequirement(
                kind="frontend_component",
                target="frontend/src/components/Feature.tsx",
            )
        ],
        frontend_roots=("frontend/src/main.tsx",),
    )

    assert graph.reachable_path(
        "frontend/src/components/Feature.tsx",
        ("frontend/src/main.tsx",),
    ) == (
        "frontend/src/main.tsx",
        "frontend/src/App.tsx",
        "frontend/src/components/Feature.tsx",
    )
    assert result.findings == ()
    assert result.evidence[0].status == "reachable"


def test_frontend_component_imported_only_by_tests_is_unreachable(tmp_path: Path) -> None:
    _write(tmp_path / "frontend" / "src" / "main.tsx", 'import App from "./App";')
    _write(tmp_path / "frontend" / "src" / "App.tsx", "export function App() { return null; }")
    _write(tmp_path / "frontend" / "src" / "components" / "Orphan.tsx", "export function Orphan() { return null; }")
    _write(
        tmp_path / "frontend" / "src" / "__tests__" / "Orphan.test.tsx",
        'import { Orphan } from "../components/Orphan";',
    )

    result = evaluate_reachability(
        tmp_path,
        [
            ReachabilityRequirement(
                kind="frontend_component",
                target="frontend/src/components/Orphan.tsx",
            )
        ],
        frontend_roots=("frontend/src/main.tsx",),
    )

    assert [finding.rule_id for finding in result.findings] == [
        "change-contract.reachability.frontend-component-unreachable"
    ]
    assert result.findings[0].evidence == {
        "target": "frontend/src/components/Orphan.tsx",
        "roots": ("frontend/src/main.tsx",),
    }


def test_entry_point_registered_from_pyproject_satisfies_requirement(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        """
        [project]
        name = "demo"
        version = "0.1.0"

        [project.entry-points."scistudio.blocks"]
        feature = "app.feature:Feature"
        """,
    )

    records = collect_python_entry_points(tmp_path)
    result = evaluate_reachability(
        tmp_path,
        [
            ReachabilityRequirement(
                kind="entry_point",
                target="scistudio.blocks:feature",
                entry_point_value="app.feature:Feature",
            )
        ],
    )

    assert [record.key for record in records] == ["scistudio.blocks:feature"]
    assert result.findings == ()
    assert result.evidence[0].status == "declared_entry_point"
    assert result.evidence[0].entry_point == "scistudio.blocks:feature"


def test_missing_entry_point_reports_structured_finding(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        """
        [project]
        name = "demo"
        version = "0.1.0"

        [project.entry-points."scistudio.blocks"]
        present = "app.present:Present"
        """,
    )

    result = evaluate_reachability(
        tmp_path,
        [
            ReachabilityRequirement(
                kind="entry_point",
                target="scistudio.blocks:missing",
                entry_point_value="app.missing:Missing",
            )
        ],
    )

    assert [finding.rule_id for finding in result.findings] == ["change-contract.reachability.entry-point-missing"]
    assert result.findings[0].target == "scistudio.blocks:missing"
    assert result.findings[0].evidence == {"target": "scistudio.blocks:missing"}


def test_explicit_canary_override_satisfies_dynamic_surface(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app" / "__init__.py")
    _write(tmp_path / "src" / "app" / "main.py", "VALUE = 1")
    _write(tmp_path / "src" / "app" / "dynamic_feature.py", "VALUE = 2")

    result = evaluate_reachability(
        tmp_path,
        [
            ReachabilityRequirement(
                kind="python_module",
                target="app.dynamic_feature",
                roots=("app.main",),
                canaries=("tests/canaries/test_dynamic_feature.py::test_loads_runtime_plugin",),
            )
        ],
    )

    assert result.findings == ()
    assert result.evidence[0].status == "declared_canary"
    assert result.evidence[0].canaries == ("tests/canaries/test_dynamic_feature.py::test_loads_runtime_plugin",)
