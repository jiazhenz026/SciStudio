"""ADR-043 / FR-008, FR-016 — Bio-Formats handler tests.

The handlers themselves (``_load_czi`` / ``_load_nd2`` / ``_load_lif`` /
``_load_oir`` / ``_load_oib``) load real microscopy files via Bio-Formats
which requires:

1. ``python-bioformats`` + ``javabridge`` installed (the
   ``[bioformats]`` optional extras).
2. A Java Runtime Environment (JRE 8+) on PATH.
3. Sample microscopy fixtures.

Tests that exercise the real load path are gated by
``pytest.importorskip("bioformats")`` so they skip cleanly when the
extras / JVM are not available in the developer's environment. The
**missing-extras failure mode test** (which asserts the user-facing
:class:`ImportError` message) runs everywhere — it monkey-patches
``importlib.import_module`` to simulate the missing dependency, so it
does NOT depend on whether bioformats is actually installed.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Always-pass: missing-extras failure mode (mocked import).
# ---------------------------------------------------------------------------


def test_import_bioformats_raises_clear_error_when_extras_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``bioformats`` cannot be imported, the handler raises a clear
    :class:`ImportError` naming the install command (``imaging[bioformats]``).

    This exercises the FR-008 contract: lazy-import + clear missing-extras
    error. Mocks the import resolution path WITHOUT mocking the handler's
    own load path (so the assertion is on the handler's error message, not
    on the handler's load logic). Tests run regardless of whether
    bioformats is installed because we override ``__import__`` to force a
    failure for that exact name.
    """
    from scieasy_blocks_imaging.io import bioformats_handler

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "bioformats":
            raise ImportError("No module named 'bioformats'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError) as excinfo:
        bioformats_handler._import_bioformats()
    msg = str(excinfo.value)
    assert "scieasy-blocks-imaging[bioformats]" in msg
    assert "Java" in msg or "JVM" in msg or "JRE" in msg


def test_import_javabridge_raises_clear_error_when_extras_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror of ``_import_bioformats`` test but for the javabridge dep."""
    from scieasy_blocks_imaging.io import bioformats_handler

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "javabridge":
            raise ImportError("No module named 'javabridge'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError) as excinfo:
        bioformats_handler._import_javabridge()
    msg = str(excinfo.value)
    assert "scieasy-blocks-imaging[bioformats]" in msg


def test_missing_extras_hint_names_install_command() -> None:
    """The module-level hint constant names the canonical install command."""
    from scieasy_blocks_imaging.io.bioformats_handler import _MISSING_EXTRAS_HINT

    assert "pip install scieasy-blocks-imaging[bioformats]" in _MISSING_EXTRAS_HINT


def test_handler_module_is_importable_without_extras() -> None:
    """The handler module itself MUST import even when bioformats is not
    installed (lazy-import contract FR-008). This guards against
    top-level ``import bioformats`` slips."""
    import importlib

    # Reimport with cache miss to be sure.
    mod = importlib.import_module("scieasy_blocks_imaging.io.bioformats_handler")
    assert hasattr(mod, "_load_czi")
    assert hasattr(mod, "_load_nd2")
    assert hasattr(mod, "_load_lif")
    assert hasattr(mod, "_load_oir")
    assert hasattr(mod, "_load_oib")


def test_load_image_dispatch_to_missing_bioformats_yields_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LoadImage`` end-to-end: a ``.czi`` path when bioformats is absent
    surfaces the clear install-command error rather than a cryptic
    AttributeError or ModuleNotFoundError without context."""
    fake = tmp_path / "sample.czi"
    fake.write_bytes(b"\x00" * 16)  # content irrelevant; handler stops at import

    from scieasy_blocks_imaging.io.load_image import LoadImage

    from scieasy.blocks.base.config import BlockConfig

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "bioformats":
            raise ImportError("No module named 'bioformats'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError) as excinfo:
        LoadImage().load(BlockConfig(params={"path": str(fake)}))
    assert "scieasy-blocks-imaging[bioformats]" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Gated on bioformats availability — exercised only when [bioformats] +
# JVM are installed AND a fixture is provided.
# ---------------------------------------------------------------------------


# Note: pytest.importorskip at function scope so this module always loads.
def _require_bioformats() -> None:
    """Skip the calling test if the bioformats extras / JVM aren't present."""
    pytest.importorskip(
        "bioformats",
        reason=(
            "Requires the [bioformats] extra and a Java Runtime "
            "Environment; install via "
            "`pip install scieasy-blocks-imaging[bioformats]`."
        ),
    )


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "microscopy"


@pytest.mark.requires_bioformats
@pytest.mark.parametrize(
    "fmt,suffix",
    [
        ("czi", ".czi"),
        ("nd2", ".nd2"),
        ("lif", ".lif"),
        ("oir", ".oir"),
        ("oib", ".oib"),
    ],
)
def test_bioformats_load_populates_ome_physical_size_x(fmt: str, suffix: str) -> None:
    """For each Bio-Formats subset member: loading a committed fixture
    returns an :class:`Image` whose ``meta.ome.images[0].pixels.physical_size_x``
    is non-None (FR-008 / SC-002)."""
    _require_bioformats()

    candidates = sorted(_FIXTURE_DIR.glob(f"sample*{suffix}"))
    if not candidates:
        pytest.skip(
            f"No {suffix} fixture committed under {_FIXTURE_DIR}; "
            "SC-002 acceptance is exercised only when a fixture is available."
        )

    from scieasy_blocks_imaging.io.load_image import LoadImage

    from scieasy.blocks.base.config import BlockConfig

    fixture = candidates[0]
    loaded = LoadImage().load(BlockConfig(params={"path": str(fixture)}))
    # LoadImage returns a Collection[Image]; pick the first item.
    assert len(loaded) >= 1
    img = loaded[0]
    assert img.meta is not None
    assert img.meta.ome is not None, f"Bio-Formats {fmt} handler did not populate Image.Meta.ome"
    assert img.meta.ome.images, "Loaded OME has no images element"
    pixels = img.meta.ome.images[0].pixels
    assert pixels.physical_size_x is not None, f"Bio-Formats {fmt} handler returned ome with physical_size_x=None"


# ---------------------------------------------------------------------------
# Helper functions tested without invoking the JVM.
# ---------------------------------------------------------------------------


def test_axes_from_ome_extracts_x_y_for_minimal_input() -> None:
    """``_axes_from_ome`` returns the SciEasy axis labels in slowest-first
    order from a minimal OME with x/y only."""
    from ome_types.model import OME, Pixels, PixelType
    from ome_types.model import Image as OMEImage
    from scieasy_blocks_imaging.io.bioformats_handler import _axes_from_ome

    ome = OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=10,
                    size_y=20,
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.UINT8,
                )
            )
        ]
    )
    axes = _axes_from_ome(ome)
    # Slowest-first per SciEasy convention; XYCZT reversed is TZCYX.
    # With singleton C/Z/T dropped → ["y", "x"].
    assert axes == ["y", "x"]


def test_axes_from_ome_keeps_c_z_t_when_size_gt_one() -> None:
    """``_axes_from_ome`` keeps C/Z/T axes when their size is greater than 1."""
    from ome_types.model import OME, Pixels, PixelType
    from ome_types.model import Image as OMEImage
    from scieasy_blocks_imaging.io.bioformats_handler import _axes_from_ome

    ome = OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=10,
                    size_y=20,
                    size_c=3,
                    size_z=4,
                    size_t=2,
                    dimension_order="XYCZT",
                    type=PixelType.UINT8,
                )
            )
        ]
    )
    axes = _axes_from_ome(ome)
    # Slowest first: T, Z, C, Y, X
    assert axes == ["t", "z", "c", "y", "x"]
