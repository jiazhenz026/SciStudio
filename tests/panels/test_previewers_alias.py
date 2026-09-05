"""The retired ``scistudio.previewers`` import path still resolves (D-001).

ADR-054 spec 1 T-001 renames the subsystem to ``scistudio.panels``. FR-045 and
FR-020 require the ``scistudio.previewers`` entry-point group and its
``get_previewers()`` factory to keep being discovered for the duration of the
migration, and a package or on-disk drop-in that supplies that factory imports
its declaration types from ``scistudio.previewers`` /
``scistudio.previewers.models``. The alias package is what keeps those imports
resolving, so this asserts the re-exports resolve and are the renamed objects
themselves rather than copies.

**One symbol is deliberately not the renamed object.** ``PreviewerSpec`` is a
translating subclass, not a re-export (#2229). These tests originally asserted
``previewers.PreviewerSpec is panels.PanelSpec``, and that identity was itself
the defect: FR-051 renamed ``capabilities`` to ``features`` and D-007 inserted
``target_types`` ahead of ``supports_collection``, so re-exporting the renamed
class made the alias package refuse the keyword a pre-rename author copied out
of its own docstring and silently mis-bind a positional call. The identity
assertions are replaced by the two properties the identity was standing in for —
that the alias resolves, and that a spec built through it is a live
``PanelSpec`` — with the translation itself covered by
``test_unmigrated_author_surface.py``.
"""

from __future__ import annotations

import scistudio.panels as panels
import scistudio.panels.data_access as panels_data_access
import scistudio.panels.helpers as panels_helpers
import scistudio.panels.models as panels_models
import scistudio.previewers as previewers
import scistudio.previewers.data_access as previewers_data_access
import scistudio.previewers.helpers as previewers_helpers
import scistudio.previewers.models as previewers_models


def test_package_alias_reexports_the_renamed_symbols() -> None:
    """``scistudio.previewers`` names the renamed objects under the old names."""
    assert previewers.PreviewerSpec is previewers_models.PreviewerSpec
    assert issubclass(previewers.PreviewerSpec, panels.PanelSpec)
    assert previewers.PreviewerEntryPoint is panels.PanelEntryPoint
    assert previewers.PreviewerRegistry is panels.PanelRegistry
    assert previewers.UnknownPreviewerError is panels.UnknownPanelError
    assert previewers.PREVIEWER_API_VERSION == panels.PANEL_API_VERSION
    assert previewers.load_project_previewers is panels.load_project_panels
    assert previewers.load_user_previewers is panels.load_user_panels


def test_models_alias_reexports_the_author_root() -> None:
    """``scistudio.previewers.models`` is the ADR-048 author root, still importable."""
    assert issubclass(previewers_models.PreviewerSpec, panels_models.PanelSpec)
    assert previewers_models.PreviewerSpecList is panels_models.PanelSpecList
    assert previewers_models.DuplicatePreviewerIdError is panels_models.DuplicatePanelIdError
    assert previewers_models.FrontendManifest is panels_models.FrontendManifest
    assert previewers_models.OwnerKind is panels_models.OwnerKind
    assert previewers_models.PreviewEnvelope is panels_models.PreviewEnvelope


def test_data_access_and_helpers_aliases_resolve() -> None:
    """The other two canonical author roots resolve through the alias too."""
    assert previewers_data_access.PreviewDataAccess is panels_data_access.PreviewDataAccess
    assert previewers_helpers.sanitize_svg is panels_helpers.sanitize_svg


def test_a_spec_built_through_the_alias_is_a_panel_spec() -> None:
    """An unmigrated ``get_previewers()`` factory still builds a live spec."""
    spec = previewers_models.PreviewerSpec(
        previewer_id="alias.probe",
        owner_kind=previewers_models.OwnerKind.PACKAGE,
        owner_name="alias",
        target_type="Array",
    )
    assert isinstance(spec, panels_models.PanelSpec)
    assert spec.to_dict()["previewer_id"] == "alias.probe"
