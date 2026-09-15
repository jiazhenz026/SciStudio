#!/usr/bin/env python3
"""Copy the architecture document into the shipped user documentation (#2469).

``docs/architecture/ARCHITECTURE.md`` is the single source. Users read the
architecture in two places that only see the packaged documentation tree
``src/scistudio/_user_guide/``:

  - the published documentation site (``build_site.py`` stages that tree as
    ``user-guide/``), and
  - SciStudio itself: the Learning Center's Reading tab (``/api/user-docs``),
    the ``user-guide/`` folder provisioned into every project, and the agent's
    ``search_docs`` / ``get_doc`` tools over that folder.

So the document ships as a generated copy, ``_user_guide/architecture.md``,
the same way the generated API reference ships inside that tree. The copy is
the source's body with its YAML front matter removed: the front matter is
repository metadata (owner, governing ADRs), and a reader that renders plain
Markdown would otherwise show it as a stray rule and paragraph above the title.
Everything after the front matter is byte-for-byte the source.

Never edit the copy. Edit the source, then regenerate::

    python scripts/docs/sync_architecture_doc.py          # write the copy
    python scripts/docs/sync_architecture_doc.py --check  # exit 1 if it drifted

``tests/docs/test_architecture_doc_copy.py`` runs the ``--check`` comparison in
CI, so a source change that is not regenerated fails the test job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md"
COPY = REPO_ROOT / "src" / "scistudio" / "_user_guide" / "architecture.md"

_FENCE = "---"


def render(source_text: str) -> str:
    """The shipped copy of ``source_text``: its body, front matter removed.

    Front matter is recognised only in the form the repository's documents use:
    a ``---`` line as the very first line, closed by the next ``---`` line.
    Text without that opening is returned unchanged.
    """
    lines = source_text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FENCE:
        return source_text
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == _FENCE:
            return "".join(lines[index + 1 :]).lstrip("\r\n")
    return source_text


def expected_copy() -> str:
    """What the committed copy must contain for the current source."""
    return render(SOURCE.read_text(encoding="utf-8"))


def is_current() -> bool:
    """Whether the committed copy matches the current source."""
    return COPY.is_file() and COPY.read_text(encoding="utf-8") == expected_copy()


def write() -> bool:
    """Regenerate the copy; return whether the file changed."""
    text = expected_copy()
    if COPY.is_file() and COPY.read_text(encoding="utf-8") == text:
        return False
    COPY.write_text(text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the shipped copy differs from the source instead of writing it.",
    )
    args = parser.parse_args(argv)
    copy_rel = COPY.relative_to(REPO_ROOT)
    if args.check:
        if is_current():
            print(f"{copy_rel} is up to date.")
            return 0
        print(
            f"{copy_rel} is out of date with {SOURCE.relative_to(REPO_ROOT)}; "
            "run `python scripts/docs/sync_architecture_doc.py`.",
            file=sys.stderr,
        )
        return 1
    changed = write()
    print(f"{'wrote' if changed else 'unchanged'}: {copy_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
