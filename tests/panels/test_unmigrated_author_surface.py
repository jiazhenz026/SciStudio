"""What a panel author's *already written* code sees after the rename (#2229).

FIVE OF THESE TESTS ARE RED ON PURPOSE. They are not broken tests and they are
not waiting to be fixed by editing them. Each one reproduces a behaviour that
``origin/main`` had and this branch does not, measured on both trees; the fix
is a decision about the product, recorded in
``docs/audit/2026-09-03-panel-migration-regression.md``. Softening one to green
would certify the difference rather than report it. If the decision is that the
break is accepted, delete the test and say so in the ADR — do not weaken it.

``scistudio.previewers`` survives as an alias package whose own docstring states
its purpose: the ``scistudio.previewers`` entry-point group and its
``get_previewers()`` factory must keep being discovered, and "the user-library
and project tiers still read ``~/.scistudio/previewers`` and
``<project>/previewers``, whose drop-in modules import from here".

That promise is about code that already exists on someone's disk and is not
going to be edited before the next time they open SciStudio. So the thing to
test is not that the *names* still import — ``test_previewers_alias.py`` covers
that — but that a spec **constructed the way the pre-rename API documented**
still produces a registered panel.

``test_previewers_alias.py::test_a_spec_built_through_the_alias_is_a_panel_spec``
is the nearest existing test and it passes only the four required fields, all
of which are unchanged by the rename; it therefore cannot see the one field the
rename moved. These tests supply the optional fields too.

Each test states which tree it was checked against. The pre-rename behaviour
was read off ``origin/main`` directly, not off anybody's description of it.
"""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path

import pytest

import scistudio.previewers as previewers
import scistudio.previewers.models as previewers_models
from scistudio.panels import build_preview_service

# The verbatim text ``tests/api/test_previewer_discovery.py`` wrote into
# ``<project>/previewers/`` on origin/main and asserted registered. Nothing here
# is invented: this is a pre-rename drop-in exactly as the old suite authored
# one, and it is the shape the panel-authoring docs taught.
PRE_RENAME_DROPIN = textwrap.dedent(
    """\
    from scistudio.previewers.models import OwnerKind, PreviewerSpec


    def get_previewers():
        return [
            PreviewerSpec(
                previewer_id="probe.project",
                owner_kind=OwnerKind.PROJECT,
                owner_name="probe",
                target_type="Array",
                priority=50,
                capabilities=("probe",),
            ),
        ]
    """
)


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway user library, so no real ``~/.scistudio`` is read or written."""
    fake = tmp_path / "home"
    (fake / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


# ---------------------------------------------------------------------------
# The declaration a pre-rename author wrote
# ---------------------------------------------------------------------------


def test_a_pre_rename_spec_still_accepts_the_capabilities_keyword() -> None:
    """The advertised-features field was renamed with no keyword alias.

    ``capabilities`` is the spelling the pre-rename ``PreviewerSpec`` docstring
    used in its own worked example, so it is the spelling an author copied. On
    origin/main::

        PreviewerSpec(..., capabilities=("slice", "lut")).capabilities
        ('slice', 'lut')

    The field is now ``features``. Because the alias re-exports the *same class*
    rather than a wrapper, there is nothing left to translate the old keyword,
    and the constructor raises ``TypeError``. Renaming a field of a type that a
    compatibility package exists to keep constructible is the break this test
    exists to catch.
    """
    spec = previewers_models.PreviewerSpec(
        previewer_id="probe",
        owner_kind=previewers_models.OwnerKind.PACKAGE,
        owner_name="acme",
        target_type="Image",
        capabilities=("slice", "lut"),
    )
    assert spec.features == ("slice", "lut")


def test_the_field_order_a_positional_caller_relied_on_is_unchanged() -> None:
    """A positional caller is mis-bound rather than refused, which is worse.

    ``target_types`` was inserted as the fifth field, ahead of
    ``supports_collection``. A pre-rename caller writing the fields positionally
    therefore gets no error at all: on origin/main this spec is
    ``supports_collection=True, priority=10``; now it is
    ``target_types=True, supports_collection=10, priority=('slice',)``.

    A ``TypeError`` a person can read is recoverable. Silently binding a bool to
    a tuple field and a tuple to an int field is not, so this is asserted
    separately from the keyword case even though one change causes both.
    """
    spec = previewers_models.PreviewerSpec(
        "probe",
        previewers_models.OwnerKind.PACKAGE,
        "acme",
        "Image",
        True,  # positional is the point of this test
        10,
    )
    assert spec.supports_collection is True
    assert spec.priority == 10


# ---------------------------------------------------------------------------
# The module paths a pre-rename author imported
# ---------------------------------------------------------------------------


def test_the_retired_fallbacks_reexport_still_resolves() -> None:
    """#1823 promised this exact path to out-of-tree packages.

    ``scistudio.previewers.fallbacks`` was kept as a back-compat re-export of
    ``sanitize_svg`` specifically "so out-of-tree packages do not hard-break
    before migrating" — that sentence is the docstring of the test that guarded
    it, ``test_sanitize_svg_back_compat_reexport_from_fallbacks``. That test
    still exists and still carries that sentence, but its subject was rewritten
    to ``scistudio.panels.fallbacks``, which is the *new* path and needs no
    back-compat promise. The promise #1823 made is now unguarded, and the path
    it named no longer imports.
    """
    fallbacks = importlib.import_module("scistudio.previewers.fallbacks")
    helpers = importlib.import_module("scistudio.previewers.helpers")
    assert fallbacks.sanitize_svg is helpers.sanitize_svg


def test_the_alias_package_still_exposes_load_choices() -> None:
    """``scistudio.previewers.load_choices`` resolved on origin/main.

    The pre-rename package imported ``load_choices`` into its own namespace, so
    ``from scistudio.previewers import load_choices`` worked. The alias package
    does not re-export it.
    """
    assert hasattr(previewers, "load_choices")


# ---------------------------------------------------------------------------
# The drop-in already sitting in someone's project
# ---------------------------------------------------------------------------


def test_a_pre_rename_dropin_on_disk_still_registers(home: Path, tmp_path: Path) -> None:
    """The end-to-end case, and the one that costs a person a working panel.

    A project containing ``previewers/probe.py`` is not a hypothetical: it is
    what the pre-rename docs told people to write and what the pre-rename suite
    itself wrote. Building the service over that project on origin/main
    registers ``probe.project``; here the scan records a diagnostic and the
    panel is silently absent from the palette.

    The scan surviving the error is the right behaviour and is not what this
    asserts. What it asserts is that the panel is still there.
    """
    project = tmp_path / "project"
    (project / "previewers").mkdir(parents=True)
    (project / "previewers" / "probe.py").write_text(PRE_RENAME_DROPIN, encoding="utf-8")

    service = build_preview_service(project_dir=project)

    registered = {spec.previewer_id for spec in service.registry.all_specs()}
    assert "probe.project" in registered, service.registry.diagnostics


def test_the_project_dropin_directory_is_still_the_one_on_disk(home: Path, tmp_path: Path) -> None:
    """``<project>/previewers`` is a path in people's projects, not an identifier.

    The subsystem was renamed but this directory was deliberately not, and the
    alias package's docstring says so. The suite that used to pin this now
    reaches it only through ``panel_scan_dirs``, so a change to the constant
    would move the tests with it. This names the literal.
    """
    from scistudio.core.dropins import panel_scan_dirs

    project = tmp_path / "project"
    project.mkdir()
    assert project / "previewers" in tuple(panel_scan_dirs(project))


# ---------------------------------------------------------------------------
# The registration door a pre-rename package came through
# ---------------------------------------------------------------------------


def test_the_previewer_entry_point_group_is_still_the_group_scanned() -> None:
    """An installed package's metadata is frozen at install time.

    A package declaring ``scistudio.previewers`` cannot re-declare itself
    without being reinstalled, so the group name is a compatibility surface in
    the same way a file path is. Named literally rather than through the
    constant, because the constant moving is exactly the failure.
    """
    from scistudio.panels.registry import PREVIEWER_ENTRY_POINT_GROUP

    assert PREVIEWER_ENTRY_POINT_GROUP == "scistudio.previewers"
