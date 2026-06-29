#!/usr/bin/env python
"""hook_protect_data_dir.py — PreToolUse guard (ADR-040 §3.6 + Addendum 6).

Blocks the in-app agent (Claude Code / Codex) from DIRECTLY modifying files
under the project's ``data/`` tree. The intent is to stop the agent from
"hand-editing" the user's scientific data; it is NOT a sandbox.

Allowed (NOT blocked):
  - Reading anything under ``data/`` (Read/cat/head/ls ...).
  - Editing or deleting files OUTSIDE ``data/`` (e.g. ``workflows/``,
    ``blocks/``) — the agent may still ``rm`` an unrelated workflow.
  - The workflow runtime writing artifacts into ``data/`` — that happens in
    the backend, not through the agent's Edit/Write/Bash tools, so it never
    reaches this hook.

Blocked (exit 2):
  - ``Edit`` / ``Write`` / ``MultiEdit`` / ``apply_patch`` whose target file
    resolves under ``<project>/data/`` (reliable).
  - ``Bash`` commands that obviously write to or delete something under
    ``data/`` (``rm``/``mv``/redirect into ``data/`` ...). This is a
    best-effort textual check, not a shell parser; the file-tool matchers
    above are the reliable layer.

stdin: Claude Code / Codex hook JSON (``tool_name``, ``tool_input``, ``cwd``).
exit 2 + stderr blocks the call; exit 0 allows it.
"""

from __future__ import annotations

import json
import os
import re
import sys

_MESSAGE = (
    "The project's data/ directory is protected: the agent must not directly "
    "edit or delete files under data/. Produce or change data by running "
    "workflow blocks (mcp__scistudio__run_workflow), not by hand-editing files. "
    "Reading data/ and editing files outside data/ is fine."
)

# A ``data/`` path token: at a boundary (start / whitespace / quote / '=' / '(')
# with an optional ``./``, OR any ``/data/`` segment in an absolute path.
_DATA_TOKEN = re.compile(r"(?:(?:^|[\s='\"(])(?:\./)?|/)data/")
# A redirection (``>`` / ``>>``) whose target path lands under ``data/``.
_REDIR_INTO_DATA = re.compile(r">>?\s*['\"]?(?:[^\s|;&>'\"]*/)?data/")

# Verbs that always alter their data/ operand (delete / overwrite / move).
_ALWAYS_DESTRUCTIVE = {"rm", "rmdir", "shred", "truncate", "dd", "tee", "install", "mv"}
# Verbs where only the destination (last operand) writing into data/ matters.
_DEST_SENSITIVE = {"cp", "ln", "rsync"}
# Leading words to skip when finding the real command verb.
_PREFIX_WORDS = {"sudo", "env", "command", "nohup", "time", "exec", "builtin"}


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _project_root(payload: dict) -> str | None:
    for key in ("CLAUDE_PROJECT_DIR", "SCISTUDIO_PROJECT_DIR"):
        value = os.environ.get(key)
        if value:
            return os.path.normpath(value).replace("\\", "/")
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return os.path.normpath(cwd).replace("\\", "/")
    return None


def _under_data(path_str: str, root: str | None) -> bool:
    """True if ``path_str`` resolves to a file under ``<project>/data/``."""
    if not path_str:
        return False
    norm = path_str.replace("\\", "/")
    if root and not os.path.isabs(norm):
        joined = os.path.normpath(os.path.join(root, norm)).replace("\\", "/")
    else:
        joined = os.path.normpath(norm).replace("\\", "/")
    if root:
        try:
            rel = os.path.relpath(joined, root).replace("\\", "/")
        except ValueError:
            rel = None
        if rel is not None and rel != ".." and not rel.startswith("../"):
            return rel == "data" or rel.startswith("data/")
    # No known root (or path on another drive): fall back to a segment match.
    return bool(re.search(r"(?:^|/)data/", joined)) or joined == "data"


def _command_segments(command: str) -> list[str]:
    return [seg.strip() for seg in re.split(r"[;&|\n]+", command) if seg.strip()]


def _segment_verb(segment: str) -> str:
    toks = segment.split()
    i = 0
    while i < len(toks) and ("=" in toks[i] or toks[i] in _PREFIX_WORDS):
        i += 1
    if i >= len(toks):
        return ""
    return os.path.basename(toks[i].strip("\"'"))


def _bash_hits_data(command: str) -> bool:
    for seg in _command_segments(command):
        if not _DATA_TOKEN.search(seg):
            continue
        if _REDIR_INTO_DATA.search(seg):
            return True
        verb = _segment_verb(seg)
        if verb in _ALWAYS_DESTRUCTIVE:
            return True
        if verb in _DEST_SENSITIVE:
            toks = [t for t in seg.split() if not t.startswith("-")]
            if toks and _DATA_TOKEN.search(" " + toks[-1]):
                return True
    return False


def main() -> int:
    payload = _read_payload()
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    root = _project_root(payload)

    if tool_name == "Bash":
        command = str(tool_input.get("command") or "")
        if command and _bash_hits_data(command):
            print(_MESSAGE, file=sys.stderr)
            return 2
        return 0

    # File-editing tools. Edit/Write/MultiEdit expose ``file_path`` directly.
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    if file_path and _under_data(file_path, root):
        print(_MESSAGE, file=sys.stderr)
        return 2

    # Codex ``apply_patch`` carries its targets inside the patch text rather
    # than a single ``file_path``. Any data/ path in an apply_patch is a write
    # or delete (it is an edit tool), so block when one appears.
    if not file_path:
        blob = " ".join(str(v) for v in tool_input.values())
        if blob and _DATA_TOKEN.search(blob):
            print(_MESSAGE, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
