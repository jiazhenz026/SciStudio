"""The plot reads a panel needs to offer the Save-as choice the viewer offered.

A plot run writes one file per rendered format beside its primary (#1918). The
compiled viewer globbed them into its payload and resolved the chosen one
through an export resource. A panel can do neither from inside a sandboxed
frame, so ``artifact.info`` reports the set and ``artifact.file`` takes the
format name — and the format name is the only thing a panel controls, so what it
can reach is what these tests are mostly about.
"""

from __future__ import annotations

import pytest
from tests.panels.conftest import make_runtime

from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.panels.contexts import read_access
from scistudio.panels.reads import read_context
from scistudio.panels.targets import PanelError, freeze_target, plot_variant_target

SVG_WITH_SCRIPT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<script>fetch("https://example.test")</script>'
    '<rect width="10" height="10" onload="steal()" />'
    "</svg>"
)


@pytest.fixture
def plot_runtime(tmp_path):
    """A runtime whose catalog holds one plot rendered in three formats."""
    runtime, store = make_runtime(tmp_path)
    # The isolated fixture registers one lab panel; the plot reads are reached
    # through the core plot panel, so install the shipped set too.
    from scistudio.panels.registry import discover_panels

    runtime.get_preview_service().registry.install_panels(discover_panels())
    plots = tmp_path / "plots"
    plots.mkdir()
    (plots / "current.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (plots / "current.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 32)
    (plots / "current.svg").write_text(SVG_WITH_SCRIPT)
    # A neighbour that is not part of this figure, to prove the stem is what
    # bounds the set rather than the directory.
    (plots / "other.jpg").write_bytes(b"\xff\xd8\xff")
    record = DataRecord(
        "data-plot",
        StorageReference(backend="filesystem", path=str(plots / "current.png")),
        "PlotArtifact",
        {"plot_artifact": True},
        ["DataObject", "Artifact", "PlotArtifact"],
    )
    runtime.data_catalog["data-plot"] = record
    return runtime, store, plots


def context_for(store, ref="data-plot"):
    return store.create({"kind": "preview", "target": {"ref": ref}})


class TestAvailableFormats:
    def test_info_reports_every_format_the_run_rendered(self, plot_runtime):
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        info = read_context(store, context, "data-plot", "artifact.info", {})

        # Canonical Save-menu order, and only this figure's own siblings —
        # `other.jpg` shares the directory but not the stem.
        assert info["formats"] == ["svg", "pdf", "png"]

    def test_a_plain_artifact_reports_no_format_menu(self, panel_runtime):
        _runtime, store = panel_runtime
        context = store.create({"kind": "preview", "target": {"ref": "data-a"}})
        info = read_context(store, context, "data-a", "artifact.info", {})

        # Only a plot is rendered more than once; offering a menu for anything
        # else would promise formats that do not exist.
        assert "formats" not in info

    def test_the_menu_does_not_change_with_the_format_being_shown(self, plot_runtime):
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        primary = read_context(store, context, "data-plot", "artifact.info", {})
        as_pdf = read_context(store, context, "data-plot", "artifact.file", {"variant": "pdf"})

        assert as_pdf["formats"] == primary["formats"]


class TestVariantGrants:
    def test_a_variant_grants_that_format_s_own_file(self, plot_runtime):
        _runtime, store, plots = plot_runtime
        context = context_for(store)
        result = read_context(store, context, "data-plot", "artifact.file", {"variant": "pdf"})

        assert result["name"] == "current.pdf"
        assert result["path"] == str(plots / "current.pdf")
        assert result["mime_type"] == "application/pdf"
        assert "/artifact/" in result["url"]

    def test_the_primary_is_served_when_no_variant_is_named(self, plot_runtime):
        _runtime, store, plots = plot_runtime
        context = context_for(store)
        result = read_context(store, context, "data-plot", "artifact.file", {})

        assert result["path"] == str(plots / "current.png")

    def test_a_format_the_run_did_not_render_is_refused(self, plot_runtime):
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        with pytest.raises(PanelError) as caught:
            read_context(store, context, "data-plot", "artifact.file", {"variant": "jpeg"})

        assert caught.value.status == 404

    @pytest.mark.parametrize(
        "variant",
        [
            "../../../../etc/passwd",
            "png/../../secret",
            "exe",
            "PNG.",
            "./png",
        ],
    )
    def test_a_format_name_cannot_reach_beyond_the_figure(self, plot_runtime, variant):
        """The format name is panel-controlled, so it must not be a path."""
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        with pytest.raises(PanelError):
            read_context(store, context, "data-plot", "artifact.file", {"variant": variant})

    def test_an_empty_format_name_means_no_choice_was_made(self, plot_runtime):
        """Empty is "no variant", which is the primary — not an error and not a path."""
        _runtime, store, plots = plot_runtime
        context = context_for(store)
        result = read_context(store, context, "data-plot", "artifact.file", {"variant": ""})

        assert result["path"] == str(plots / "current.png")

    def test_a_neighbour_with_another_stem_is_not_reachable(self, plot_runtime):
        """`other.jpg` sits beside the figure but is not part of it."""
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        with pytest.raises(PanelError):
            read_context(store, context, "data-plot", "artifact.file", {"variant": "jpeg"})

    def test_asking_twice_reuses_one_grant(self, plot_runtime):
        _runtime, store, _plots = plot_runtime
        context = context_for(store)
        first = read_context(store, context, "data-plot", "artifact.file", {"variant": "pdf"})
        second = read_context(store, context, "data-plot", "artifact.file", {"variant": "pdf"})

        assert first["url"] == second["url"]

    def test_a_variant_target_stays_a_child_of_the_plot(self, plot_runtime):
        runtime, _store, plots = plot_runtime
        parent = freeze_target(runtime, "data-plot")
        child = plot_variant_target(parent, "svg")

        # The parent is re-validated with the child, so a plot whose primary was
        # deleted cannot keep serving its siblings.
        assert child.parent is parent
        assert child.stamp is not None
        child.validate(runtime)
        (plots / "current.png").unlink()
        with pytest.raises(PanelError):
            child.validate(runtime)


class TestServedSvg:
    def test_an_svg_artifact_is_scrubbed_before_it_is_served(self, plot_runtime):
        """The compiled Save wrote scrubbed SVG; these bytes are what a panel saves."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from scistudio.api.routes.panels import install_panels

        runtime, store, _plots = plot_runtime
        context = context_for(store)
        granted = read_context(store, context, "data-plot", "artifact.file", {"variant": "svg"})

        app = FastAPI()
        app.state.runtime = runtime
        install_panels(app)
        with TestClient(app) as client:
            response = client.get(granted["url"])

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        body = response.text
        assert "<script" not in body
        assert "onload" not in body
        # The figure itself survives the scrub.
        assert "<rect" in body

    def test_a_non_svg_artifact_is_served_as_it_is(self, plot_runtime):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from scistudio.api.routes.panels import install_panels

        runtime, store, plots = plot_runtime
        context = context_for(store)
        granted = read_context(store, context, "data-plot", "artifact.file", {"variant": "pdf"})

        app = FastAPI()
        app.state.runtime = runtime
        install_panels(app)
        with TestClient(app) as client:
            response = client.get(granted["url"])

        assert response.status_code == 200
        assert response.content == (plots / "current.pdf").read_bytes()


def test_read_access_is_the_only_file_authority(plot_runtime):
    """A sanity anchor: the sibling resolution runs off the frozen storage ref."""
    runtime, _store, plots = plot_runtime
    parent = freeze_target(runtime, "data-plot")
    assert read_access().artifact_file(parent.storage) == (plots / "current.png").resolve()
