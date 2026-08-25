"""Serve the shipped user documentation to the in-app reader (#2157).

SciStudio already writes a complete user documentation set: ``scistudio/_user_guide/``
— the guide pages plus the generated, self-contained API reference. It ships in
the wheel, provisioning copies it into every project, and the published site is
that same tree (site = Home + this tree + the repo-only package development
guide). Until now the product gave a reader no way to open it without leaving
for the browser.

These two endpoints are what the Learning Center's Reading tab reads:

* ``GET /api/user-docs/nav``          — the navigation tree
* ``GET /api/user-docs/pages/{path}`` — one file's text

**The packaged tree, not a project's copy.** The reader is served from
``importlib.resources``, so the documentation opens with no project on screen and
can never disagree with the code it was generated from. A project's provisioned
``user-guide/`` is a copy for the in-project human and the embedded agent; it is
not a second source of truth.

**The navigation is the site's own.** The owner asked for the web version's left
menu, so the tree here is not an editorial re-listing: it reproduces the rules
MkDocs applies when it generates a nav from a directory (MkDocs 1.6,
``mkdocs.structure.files.get_files`` and ``mkdocs.utils.nest_paths``), which are
the rules that produced the published sidebar. :func:`_nav_of` documents each one
against the behaviour it mirrors. Package Development is absent because it is a
developer document that lives in the repository rather than in this tree — it was
never part of what ships.

**The page path is a request parameter, and is treated as one** (#2160). It is
split into plain names by :func:`_segments` — no separator of *either* platform,
no ``..``, nothing absolute or drive-lettered — and :func:`_contained` checks the
resolved real path against the tree root behind that. Two locks, because the
first version had one and it was the wrong one: splitting on ``/`` alone left a
backslash inside a single segment, where it passed the ``..`` refusal and then
became a separator the moment ``Path`` joined it on Windows.

The tree is read once per process and cached: it is packaged data, so it cannot
change under a running server.
"""

from __future__ import annotations

import importlib.resources
import os
import posixpath
import re
from functools import lru_cache
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

#: The package the documentation tree sits in, and the tree's directory name.
#: ``_user_guide`` holds no Python and so is not an importable package of its
#: own; reaching it through its parent is what ``agent_provisioning.docs`` does
#: to copy it into a project, and it yields a real directory (rather than a
#: ``MultiplexedPath``) whose containment can be checked.
_DOCS_PACKAGE = "scistudio"
_DOCS_DIR = "_user_guide"

#: Extensions rendered as prose. MkDocs builds its nav from Markdown pages only;
#: every other file is copied verbatim beside them and reachable by link.
_PAGE_SUFFIX = ".md"

#: A directory link (``examples/``) means that directory's index page, and
#: MkDocs accepts either spelling as one.
_INDEX_STEMS = ("index", "README")

#: MkDocs' extracted page title: the document's *first* block element, and only
#: when that element is an ``h1``. A file that opens with anything else — the
#: generated reference opens with a provenance comment — takes the filename
#: title instead, which is why the site's sidebar says "Index" there.
_H1 = re.compile(r"^#[^#\S]*\s*(.+?)\s*#*\s*$")

#: A link, reduced to its text; then the emphasis and code markers, dropped.
#: MkDocs takes a title off the *rendered* heading and keeps only its text, so
#: the site's sidebar reads "a custom .npy loader" where the source says
#: ``a custom `.npy` loader``. A menu that kept the backticks would not match it.
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"(\*\*|__|[*`_])")

router = APIRouter(prefix="/api/user-docs", tags=["user-docs"])


class DocsNavItem(BaseModel):
    """One row of the navigation tree.

    A row is either a page (has ``path``) or a section (has ``children``).
    Sections carry no path because MkDocs generates them from a directory name
    and gives them nothing to open — in the published sidebar they are headings
    that expand, not links.
    """

    kind: str = Field(description="``page`` or ``section``.")
    title: str
    #: Tree-relative POSIX path of the file this row opens; sections have none.
    path: str | None = None
    children: list[DocsNavItem] = Field(default_factory=list)


class DocsNavResponse(BaseModel):
    """The navigation tree, and where the reader starts."""

    #: The caption the published sidebar prints above this group.
    title: str
    #: The entry page: the user guide's front page.
    root: str
    items: list[DocsNavItem] = Field(default_factory=list)


class DocsPageResponse(BaseModel):
    """One documentation file, as text."""

    path: str
    title: str
    #: ``markdown`` for a guide page; ``source`` for a file the guide links to
    #: as a worked example (``block.py``, ``accucor.R``), which the site serves
    #: verbatim beside the page that links it.
    kind: str
    text: str


def _dirname_title(name: str) -> str:
    """A directory's section title, by MkDocs' rule (``utils.dirname_to_title``).

    Separators become spaces, and an all-lowercase name is capitalised — which
    is where the sidebar's "Api reference" and "App fiji" come from. A name that
    already carries capitals is left alone.
    """
    title = name.replace("-", " ").replace("_", " ")
    return title.capitalize() if title.lower() == title else title


def _filename_title(name: str) -> str:
    """A page's fallback title, by MkDocs' rule (``Page._get_title_from_filename``).

    Same transformation as a directory's, applied to the stem. This is what the
    site shows for a page whose first element is not a heading.
    """
    stem = name[: -len(_PAGE_SUFFIX)] if name.endswith(_PAGE_SUFFIX) else name
    return _dirname_title(stem)


def _title_of(name: str, text: str) -> str:
    """The title MkDocs would print for this page in the sidebar.

    MkDocs reads the title off the rendered document's first element, using it
    only when that element is an ``h1``; anything else in front of the heading —
    a comment, a paragraph, a table — and the page falls back to its filename.
    Reproducing that is the difference between the reader's menu matching the
    published one and merely resembling it.
    """
    for line in text.lstrip("﻿").splitlines():
        if not line.strip():
            continue
        heading = _H1.match(line)
        if not heading:
            return _filename_title(name)
        return _MARKUP.sub("", _LINK.sub(r"\1", heading.group(1))).strip()
    return _filename_title(name)


def _sort_key(name: str, *, is_dir: bool) -> tuple[int, int, str]:
    """Order one directory's entries the way MkDocs walks them.

    Three rules, in order: a directory's own files come before its
    subdirectories (``os.walk`` is top-down); ``index``/``README`` leads the
    files (``files._file_sort_key``); everything else is alphabetical.
    """
    if is_dir:
        return (1, 1, name)
    stem = name[: -len(_PAGE_SUFFIX)] if name.endswith(_PAGE_SUFFIX) else name
    return (0, 0 if stem in _INDEX_STEMS else 1, name)


def _nav_of(directory: Traversable, prefix: str) -> list[DocsNavItem]:
    """Build the navigation for one directory, recursively.

    Only Markdown files become rows. The example directories' ``block.py`` and
    ``accucor.R`` are absent here for the same reason they are absent from the
    published sidebar: MkDocs navigates pages and copies everything else, so
    those files are reached through the page that links them, not through the
    menu.
    """
    entries = sorted(
        ((child.name, child) for child in directory.iterdir() if not child.name.startswith((".", "__"))),
        key=lambda pair: _sort_key(pair[0], is_dir=pair[1].is_dir()),
    )
    items: list[DocsNavItem] = []
    for name, child in entries:
        path = posixpath.join(prefix, name) if prefix else name
        if child.is_dir():
            children = _nav_of(child, path)
            if children:
                items.append(DocsNavItem(kind="section", title=_dirname_title(name), children=children))
            continue
        if not name.endswith(_PAGE_SUFFIX):
            continue
        text = child.read_text(encoding="utf-8")
        items.append(DocsNavItem(kind="page", title=_title_of(name, text), path=path))
    return items


def _root() -> Traversable:
    """The documentation tree's directory."""
    return importlib.resources.files(_DOCS_PACKAGE) / _DOCS_DIR


@lru_cache(maxsize=1)
def _nav() -> DocsNavResponse:
    """The whole tree's navigation, read once — packaged data does not change."""
    root = _root()
    return DocsNavResponse(
        # The caption the published sidebar prints above this group. It comes
        # from the site's staging directory name, not from this tree.
        title=_dirname_title("user-guide"),
        root="README.md",
        items=_nav_of(root, ""),
    )


def _segments(path: str) -> list[str] | None:
    """Split a tree-relative path into plain names, or return ``None`` to refuse.

    The rules are ``tutorials.actions.validate_relative_path``'s, for its
    reasons. A backslash is rejected outright rather than treated as an ordinary
    character, because it is a separator on Windows and a filename character
    elsewhere: splitting a request path on ``/`` alone leaves ``..\\version.py``
    as one segment that passes a ``..`` test and then escapes the tree the
    moment ``Path`` joins it. Absolute and drive-lettered forms go the same way.

    What survives is a list of plain names — no separator of either platform, no
    ``..``, nothing empty — which is the only shape a documentation path is ever
    written in.
    """
    trimmed = path.strip("/")
    if not trimmed or "\\" in trimmed:
        return None
    if PurePosixPath(trimmed).is_absolute() or PureWindowsPath(trimmed).drive:
        return None
    segments = [segment for segment in trimmed.split("/") if segment != "."]
    if not segments or any(segment in ("", "..") for segment in segments):
        return None
    return segments


def _filesystem_path(item: Traversable) -> str | None:
    """``item`` as a real filesystem path, or ``None`` when it has none.

    A ``Traversable`` is not required to be on a filesystem — a tree read out
    of a zip is not — so this narrows rather than assumes.
    """
    if not isinstance(item, os.PathLike):
        return None
    resolved: str | bytes = os.fspath(item)
    return resolved if isinstance(resolved, str) else None


def _contained(candidate: Traversable) -> bool:
    """Whether ``candidate`` really sits beneath the documentation tree.

    :func:`_segments` already refuses every path that could name something
    outside, so this is the second lock rather than the first: it is what a
    symbolic link planted inside the tree would have to defeat, and it is
    checked on the *real* paths for that reason. A tree loaded from a zip
    exposes no filesystem path and needs none — the segment rules govern there,
    and a zip has no symbolic links to follow.
    """
    root = _filesystem_path(_root())
    target = _filesystem_path(candidate)
    if root is None or target is None:
        return True
    return os.path.realpath(target).startswith(os.path.realpath(root) + os.sep)


def _resolve(path: str) -> Traversable:
    """Resolve a tree-relative path, or refuse.

    A directory resolves to its index page, which is what a link like
    ``examples/`` means.
    """
    refused = HTTPException(status_code=404, detail=f"No such documentation page: {path!r}")
    segments = _segments(path)
    if segments is None:
        raise refused
    current: Traversable = _root()
    for segment in segments:
        try:
            current = current / segment
            if not (current.is_file() or current.is_dir()):
                raise FileNotFoundError(segment)
        except (FileNotFoundError, NotADirectoryError, OSError, ValueError):
            raise refused from None
    if not _contained(current):
        raise refused
    if current.is_dir():
        for stem in _INDEX_STEMS:
            candidate = current / f"{stem}{_PAGE_SUFFIX}"
            if candidate.is_file():
                return candidate
        raise refused
    return current


@router.get("/nav", response_model=DocsNavResponse)
async def get_nav() -> DocsNavResponse:
    """Return the documentation navigation tree."""
    return _nav()


@router.get("/pages/{path:path}", response_model=DocsPageResponse)
async def get_page(path: str) -> DocsPageResponse:
    """Return one documentation file's text."""
    resolved = _resolve(path)
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # A file that is not text is not something the reader can show. The
        # tree holds none today; a future binary asset should not 500.
        raise HTTPException(status_code=415, detail=f"Not a readable document: {path!r}") from None
    name = resolved.name
    markdown = name.endswith(_PAGE_SUFFIX)
    return DocsPageResponse(
        path=path.strip("/"),
        title=_title_of(name, text) if markdown else name,
        kind="markdown" if markdown else "source",
        text=text,
    )
