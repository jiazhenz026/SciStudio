"""Issue #1079 — AppBlock._bin_outputs_by_extension typed reconstruction.

ADR-028 §D8: the binner now consults the materialisation helper
``reconstruct_from_file`` to reconstruct each output port's payload
according to the port's declared target type, instead of silently
downgrading every non-``Artifact`` declared type to ``Artifact``.

These tests pin down the three intended outcomes:

1. **Typed reconstruction**: when the port declares a concrete core
   type (e.g. ``DataFrame``) and ``BlockRegistry`` exposes a loader for
   the resolved ``(target_type, extension)`` pair, the binner returns a
   typed ``DataFrame`` instance — *not* an ``Artifact`` with a warning.
2. **Legacy ``Artifact`` port**: when the port declares ``Artifact``,
   the binner still returns an ``Artifact`` for any extension (the
   ``reconstruct_from_file`` Artifact-fallback path applies — no
   regression).
3. **Missing loader for non-Artifact port**: when the port declares a
   concrete non-Artifact type and no loader is registered for the
   ``(declared_type, extension)`` pair, the binner propagates a
   ``LookupError`` from ``reconstruct_from_file``. This is the new,
   *intentional* contract: the declared port type is honored or the
   run fails — no silent downgrade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.dataframe import DataFrame


def _make_block_with_ports(port_dicts: list[dict[str, Any]]) -> AppBlock:
    """Construct an ``AppBlock`` with editor-style output port dicts.

    Mirrors the helper from ``tests/blocks/test_app_block.py::TestAppBlockExtensionBinner``
    so the new typed-reconstruction tests stay self-contained in this
    file (per the #1079 dispatch's owned-files whitelist).
    """
    return AppBlock(config={"params": {"output_ports": port_dicts}})


class TestTypedReconstruction:
    """#1079: ``reconstruct_from_file`` produces typed outputs for the binner."""

    def test_typed_dataframe_port_returns_dataframe_instance(self, tmp_path: Path) -> None:
        """FijiBlock-style scenario, but with core ``DataFrame`` + ``.csv``.

        ``LoadData`` is registered as the loader for ``(DataObject, .csv)``
        and produces a ``DataFrame`` when ``core_type="DataFrame"`` is
        resolved from the target. ``reconstruct_from_file`` routes
        through the dynamic-port fallback to construct a typed
        ``DataFrame`` — exactly the contract the
        FijiBlock→Image→SaveImage edge needs (#1079 issue body).
        """
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

        block = _make_block_with_ports([{"name": "tables", "types": ["DataFrame"], "extension": "csv"}])
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "tables", "types": ["DataFrame"], "extension": "csv"},
                ]
            }
        )

        result = block._bin_outputs_by_extension([csv_path], config)

        coll = result["tables"]
        assert coll.length == 1
        item = next(iter(coll))
        # The key contract: typed DataFrame, NOT Artifact.
        assert isinstance(item, DataFrame), (
            f"Expected typed DataFrame from reconstruct_from_file, got {type(item).__name__}"
        )
        assert not isinstance(item, Artifact), "Pre-#1079 silent downgrade to Artifact must not occur for typed ports"
        # The collection's item_type tracks the actual constructed item.
        assert coll.item_type is DataFrame

    def test_no_warning_emitted_for_typed_reconstruction(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The pre-#1079 "not constructible from a file path" warning is gone.

        Even when the declared port type is non-Artifact, the binner
        must not log that warning anymore — typed reconstruction
        succeeds via ``reconstruct_from_file`` and the Artifact fallback
        (when it happens) is an intentional documented path.
        """
        import logging

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

        block = _make_block_with_ports([{"name": "tables", "types": ["DataFrame"], "extension": "csv"}])
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "tables", "types": ["DataFrame"], "extension": "csv"},
                ]
            }
        )

        with caplog.at_level(logging.WARNING, logger="scieasy.blocks.app.app_block"):
            block._bin_outputs_by_extension([csv_path], config)

        # The pre-#1079 warning text must never appear.
        for record in caplog.records:
            assert "not constructible from a file path" not in record.message, (
                f"Removed pre-#1079 warning re-appeared: {record.message}"
            )


class TestLegacyArtifactPort:
    """#1079: declared-Artifact ports keep their pre-existing behavior."""

    def test_legacy_artifact_port_returns_artifact(self, tmp_path: Path) -> None:
        """A port declaring ``Artifact`` still yields ``Artifact`` per the
        Artifact-fallback path inside ``reconstruct_from_file``.

        This preserves the #690 audit guarantee that
        ``Collection.item_type`` is homogeneous and matches the actual
        constructed items.
        """
        pdf_path = tmp_path / "report.pdf"
        pdf_path.write_text("x", encoding="utf-8")

        block = _make_block_with_ports([{"name": "reports", "types": ["Artifact"], "extension": "pdf"}])
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "reports", "types": ["Artifact"], "extension": "pdf"},
                ]
            }
        )

        result = block._bin_outputs_by_extension([pdf_path], config)

        coll = result["reports"]
        assert coll.length == 1
        item = next(iter(coll))
        assert isinstance(item, Artifact)
        assert coll.item_type is Artifact
        # Pre-#1079 binner set Artifact.file_path / description; the
        # ``reconstruct_from_file`` Artifact fallback preserves these.
        assert getattr(item, "file_path", None) is not None


class TestMissingLoaderForConcreteType:
    """#1079: missing loader for non-Artifact target now raises, not downgrades."""

    def test_no_loader_for_concrete_type_raises(self, tmp_path: Path) -> None:
        """When the declared port type is concrete non-Artifact and no
        loader is registered for ``(declared_type, extension)``,
        ``_bin_outputs_by_extension`` must propagate the ``LookupError``
        from ``reconstruct_from_file``.

        Pre-#1079 the binner silently downgraded to ``Artifact`` and
        emitted a warning. The new contract is: declare a concrete type
        only when a matching loader is registered; otherwise the run
        fails fast.
        """
        # Use a deliberately-unregistered extension so no loader matches
        # (DataFrame, .no_loader_for_this_xyz).
        f = tmp_path / "data.no_loader_for_this_xyz"
        f.write_text("x", encoding="utf-8")

        block = _make_block_with_ports(
            [
                {
                    "name": "tables",
                    "types": ["DataFrame"],
                    "extension": "no_loader_for_this_xyz",
                }
            ]
        )
        config = BlockConfig(
            params={
                "output_ports": [
                    {
                        "name": "tables",
                        "types": ["DataFrame"],
                        "extension": "no_loader_for_this_xyz",
                    },
                ]
            }
        )

        with pytest.raises(LookupError):
            block._bin_outputs_by_extension([f], config)
