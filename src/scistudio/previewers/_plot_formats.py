"""The formats a rendered plot is available in, and where they sit on disk.

A plot run promotes one ``<stem>.<suffix>`` file per allowed format beside the
preferred-format primary (#1918, "approach B"), so a reader can save the figure
as SVG, PDF, PNG, or JPEG without anything re-rendering it. Two surfaces need to
agree about that set: the compiled previewer, which globs it into its payload,
and the panel read layer, which has to offer the same choice from inside a
sandboxed frame. This module is the one place that knows the answer, so the two
cannot drift into offering different menus for the same figure.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.stability import internal

#: Suffixes a plot artifact may be written with.
PLOT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".pdf"})

#: Canonical export formats, in the order a Save-as menu offers them.
EXPORT_FORMAT_ORDER: tuple[str, ...] = ("svg", "pdf", "png", "jpeg")


@internal()
def canonical_format(suffix: str) -> str:
    """Fold a ``.ext`` or ``ext`` suffix to a canonical format (``jpg`` → ``jpeg``)."""
    ext = suffix.lower().lstrip(".")
    return "jpeg" if ext == "jpg" else ext


@internal()
def available_formats(primary: object) -> list[str]:
    """Formats this plot was actually rendered in, resolved from its siblings.

    Falls back to the primary's own format when the directory cannot be read, so
    a Save menu always offers at least the file the reader is looking at.
    """
    # Development references: #1918.
    path = primary if isinstance(primary, Path) else Path(str(primary))
    own = canonical_format(path.suffix)
    try:
        found = {
            canonical_format(sibling.suffix)
            for sibling in path.parent.glob(f"{path.stem}.*")
            if sibling.is_file() and sibling.suffix.lower() in PLOT_SUFFIXES
        }
    except OSError:
        found = set()
    found.add(own)
    return [fmt for fmt in EXPORT_FORMAT_ORDER if fmt in found]


@internal()
def sibling_for(primary: Path, fmt: str) -> Path | None:
    """The file holding *fmt* for this plot, or ``None`` when it was not rendered.

    Only a file beside *primary* with *primary*'s own stem can be returned, so a
    caller that passes a format name straight through from a panel cannot reach
    anything the plot run did not write. ``jpeg`` accepts either spelling of the
    suffix, which is the only place the two differ.
    """
    canonical = canonical_format(fmt)
    if canonical not in EXPORT_FORMAT_ORDER:
        return None
    suffixes = (".jpeg", ".jpg") if canonical == "jpeg" else (f".{canonical}",)
    for suffix in suffixes:
        candidate = primary.parent / f"{primary.stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None
