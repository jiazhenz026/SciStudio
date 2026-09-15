"""Workflow run identity derived from the workflow file.

A workflow is identified at run time by the file it lives in, never by the
``id:`` written inside the YAML. The same identity keys the running-workflow
guard, the scheduler's event filter, the process registry, the lineage
``runs.workflow_id`` column, the pause checkpoint directory, the
``data/zarr/<identity>/`` output directory, and the ``workflow_id`` carried on
engine and ``workflow.changed`` events.

Two forms exist:

* ``workflows/<stem>.yaml`` — the canonical home of a project workflow — is
  identified by its stem, so ``workflows/main.yaml`` is ``main``. Existing
  lineage rows, checkpoints and output directories of correctly named
  workflows keep their values.
* Any other workflow file (a subworkflow under ``subworkflows/``, a nested
  file, a ``.yml`` file) is identified by its project-relative path, written
  as ``@`` followed by the path components joined with ``@``:
  ``subworkflows/qc.yaml`` is ``@subworkflows@qc.yaml``. Inside a component
  ``%`` is written ``%25`` and ``@`` is written ``%40``.

The path form is a single path segment, so it works unchanged as a directory
name, a checkpoint file name and a URL path parameter. A stem never contains
``/``, and a top-level stem that itself starts with ``@`` is given the path
form, so no two files share an identity.
"""

# Maintainer context (kept outside generated API documentation):
# Owner decision A3 on #2394: one canonical run identity derived from the
# workflow file. The YAML ``id:`` no longer participates in run identity.
# Development references: #2394, #1910, #1836, ADR-044.

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

__all__ = [
    "WORKFLOW_SUFFIXES",
    "declared_id_for_file_name",
    "is_path_identity",
    "project_relative_path_for_identity",
    "rewrite_workflow_id_text",
    "workflow_identity_for_path",
    "workflow_identity_for_relative_path",
]

#: File suffixes a workflow YAML may carry.
WORKFLOW_SUFFIXES: tuple[str, ...] = (".yaml", ".yml")

_PATH_MARKER = "@"
_TOP_LEVEL_DIR = "workflows"
_CANONICAL_SUFFIX = ".yaml"
_UNESCAPE = re.compile(r"%(25|40)")


def _escape(component: str) -> str:
    return component.replace("%", "%25").replace("@", "%40")


def _unescape(component: str) -> str:
    return _UNESCAPE.sub(lambda match: "%" if match.group(1) == "25" else "@", component)


def workflow_identity_for_relative_path(relative_path: str | PurePosixPath) -> str:
    """Return the run identity of a workflow file at *relative_path*.

    *relative_path* is relative to the project root and uses ``/`` separators.
    """
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Not a project-relative workflow path: {relative_path!r}")
    if len(parts) == 2 and parts[0] == _TOP_LEVEL_DIR and parts[1].endswith(_CANONICAL_SUFFIX):
        stem = parts[1][: -len(_CANONICAL_SUFFIX)]
        if stem and not stem.startswith(_PATH_MARKER):
            return stem
    return _PATH_MARKER + _PATH_MARKER.join(_escape(part) for part in parts)


def workflow_identity_for_path(project_root: str | Path, path: str | Path) -> str:
    """Return the run identity of the workflow file *path* inside *project_root*.

    Raises ``ValueError`` when *path* is not inside the project.
    """
    root = Path(project_root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Workflow file is outside the project: {path}") from exc
    return workflow_identity_for_relative_path(PurePosixPath(relative.as_posix()))


def is_path_identity(identity: str) -> bool:
    """Whether *identity* is the path form (a file outside ``workflows/<stem>.yaml``)."""
    return _decode_path_identity(identity) is not None


def _decode_path_identity(identity: str) -> PurePosixPath | None:
    if not identity.startswith(_PATH_MARKER):
        return None
    raw_parts = identity[len(_PATH_MARKER) :].split(_PATH_MARKER)
    parts = [_unescape(part) for part in raw_parts]
    for part in parts:
        if part in ("", ".", "..") or "/" in part or "\\" in part:
            return None
    if not parts[-1].lower().endswith(WORKFLOW_SUFFIXES):
        return None
    return PurePosixPath(*parts)


def project_relative_path_for_identity(identity: str) -> PurePosixPath:
    """Return the project-relative file path a run identity names.

    The inverse of :func:`workflow_identity_for_relative_path`. An identity that
    is not a valid path form names ``workflows/<identity>.yaml``, which keeps
    every existing stem (including one that starts with ``@``) addressable.
    """
    decoded = _decode_path_identity(identity)
    if decoded is not None:
        return decoded
    return PurePosixPath(_TOP_LEVEL_DIR) / f"{identity}{_CANONICAL_SUFFIX}"


def declared_id_for_file_name(name: str) -> str:
    """Return the ``id:`` a workflow file named *name* should declare.

    The file name without its YAML suffix, and without the ``.swf`` marker the
    subworkflow import convention allows (``qc.swf.yaml`` declares ``qc``).
    """
    stem = name
    for suffix in WORKFLOW_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if stem.lower().endswith(".swf"):
        stem = stem[: -len(".swf")]
    return stem or name


_WORKFLOW_KEY = re.compile(r"^workflow:[ \t]*(#.*)?$")
_INDENTED_KEY = re.compile(r"^(?P<indent>[ \t]+)(?P<key>[A-Za-z_][\w-]*)[ \t]*:(?P<rest>.*)$")
_TOP_LEVEL_LINE = re.compile(r"^\S")


def _quote_scalar(value: str) -> str:
    import yaml

    dumped = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).strip()
    # ``safe_dump`` of a plain scalar ends with a document-end marker line.
    if dumped.endswith("..."):
        dumped = dumped[: -len("...")].strip()
    return dumped


def rewrite_workflow_id_text(text: str, new_id: str) -> str | None:
    """Return *text* with its ``workflow.id`` set to *new_id*.

    Only the ``id:`` line is touched, so comments, key order and formatting of
    the rest of the file are kept. A file without an ``id:`` gets one as the
    first key under ``workflow:``. Returns ``None`` when the text has no
    top-level ``workflow:`` mapping this function can edit safely; the caller
    then falls back to a full re-serialisation.
    """
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if _WORKFLOW_KEY.match(line.rstrip("\r\n"))), None)
    if start is None:
        return None
    body_indent: str | None = None
    insert_at: int | None = None
    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    for index in range(start + 1, len(lines)):
        line = lines[index].rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _TOP_LEVEL_LINE.match(line):
            break
        match = _INDENTED_KEY.match(line)
        if body_indent is None:
            if match is None:
                return None
            body_indent = match.group("indent")
            insert_at = index
        if match is None or match.group("indent") != body_indent:
            continue
        if match.group("key") == "id":
            rest = match.group("rest")
            comment = ""
            comment_match = re.search(r"[ \t]+#.*$", rest)
            if comment_match is not None:
                comment = comment_match.group(0)
            lines[index] = f"{body_indent}id: {_quote_scalar(new_id)}{comment}{newline}"
            return "".join(lines)
    if body_indent is None or insert_at is None:
        return None
    lines.insert(insert_at, f"{body_indent}id: {_quote_scalar(new_id)}{newline}")
    return "".join(lines)
