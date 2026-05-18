"""Tests for ScieasyRunnerCatalog directive — ADR-044 §11.5."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from docutils import nodes


class TestRunnerCatalogDirective:
    """Tests for ScieasyRunnerCatalog."""

    def _make_directive(self, options: dict | None = None):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import ScieasyRunnerCatalog

        return ScieasyRunnerCatalog(
            name="scieasy-runner-catalog",
            arguments=[],
            options=options or {},
            content=[],
            lineno=1,
            content_offset=0,
            block_text="",
            state=MagicMock(),
            state_machine=MagicMock(),
        )

    def test_run_returns_node_list(self):
        directive = self._make_directive()
        result = directive.run()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_with_real_entry_points(self):
        """With real scieasy.runners entry-points at least one runner row is present."""
        directive = self._make_directive()
        result = directive.run()
        assert not any(isinstance(n, nodes.warning) for n in result)

    def test_run_with_empty_group(self):
        """Empty group returns a warning node."""
        with patch("scieasy.qa.docs.directives.scieasy_runner_catalog.importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = []
            directive = self._make_directive(options={"entry-point-group": "nonexistent"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)

    def test_run_exception_on_eps_returns_warning(self):
        """If entry_points raises, a warning node is emitted."""
        with patch(
            "scieasy.qa.docs.directives.scieasy_runner_catalog.importlib.metadata.entry_points",
            side_effect=Exception("boom"),
        ):
            directive = self._make_directive(options={"entry-point-group": "fail"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)

    def test_raw_node_content(self):
        """The raw node contains list-table markup."""
        directive = self._make_directive()
        result = directive.run()
        raw_nodes = [n for n in result if isinstance(n, nodes.raw)]
        assert raw_nodes
        rst = raw_nodes[0].rawsource
        assert "list-table" in rst


class TestLoadRunnerSpecs:
    """Tests for _load_runner_specs helper."""

    def test_returns_list(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _load_runner_specs

        specs = _load_runner_specs("scieasy.runners")
        assert isinstance(specs, list)

    def test_has_required_keys(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _load_runner_specs

        specs = _load_runner_specs("scieasy.runners")
        for spec in specs:
            assert "name" in spec
            assert "language" in spec
            assert "executables" in spec
            assert "detected" in spec

    def test_sorted_by_name(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _load_runner_specs

        specs = _load_runner_specs("scieasy.runners")
        names = [s["name"] for s in specs]
        assert names == sorted(names)


class TestInferLanguage:
    """Tests for _infer_language helper."""

    def test_python_runner(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _infer_language

        assert _infer_language("python") == "Python"

    def test_r_runner(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _infer_language

        assert _infer_language("r") == "R"

    def test_julia_runner(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _infer_language

        assert _infer_language("julia") == "Julia"

    def test_unknown_runner(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _infer_language

        result = _infer_language("unknown_runner")
        assert isinstance(result, str)
        assert len(result) > 0


class TestDetectExecutable:
    """Tests for _detect_executable helper."""

    def test_finds_python(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _detect_executable

        result = _detect_executable(["python3", "python"])
        # Either found or "not found"
        assert isinstance(result, str)

    def test_not_found_for_nonexistent(self):
        from scieasy.qa.docs.directives.scieasy_runner_catalog import _detect_executable

        result = _detect_executable(["definitely_not_a_real_executable_xyz123"])
        assert result == "not found"
