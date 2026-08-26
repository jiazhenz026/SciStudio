#!/usr/bin/env python
"""hook_check_panel_contract.py — PostToolUse (ADR-040 §3.6, ADR-051, #2196).

After a write touched an interactive block's panel module — a ``.js`` or
``.mjs`` file — check it against the ``PanelModule`` contract the frontend panel
host enforces, and stderr-warn so the next turn corrects it.

**Why this hook exists.** The other write-time block hook matches
``(?:^|/)blocks/[^/]+\\.py$`` (``hook_enforce_list_blocks_before_block_write.py``),
so a hand-written panel module was touched by no hook at all. Every way of
getting a panel wrong therefore travelled all the way to the user as a modal
that opened and immediately errored, with the reason visible only in the
browser. Each finding below names the same failure code
``panelModuleLoader.ts`` would show, so the author's vocabulary and the user's
error text agree.

**Why the rules are transcribed rather than imported.** Every provisioned hook
script runs under the *base* interpreter and imports the standard library and
nothing else — that is what makes
``scistudio.agent_provisioning.hooks.hook_interpreter`` safe to freeze into a
command that must outlive the venv it was written in. A hook that imported
``scistudio`` would die, silently and fail-open, wherever that interpreter
cannot see the package. So the source checks are transcribed from
``scistudio.blocks.base.panel_contract`` and
``tests/agent_provisioning/test_hook_panel_contract_parity.py`` fails if the
two ever disagree on a fixture — the transcription cannot drift unnoticed.

**What is not checked here.** The manifest half — ``module_url`` shape,
``asset_root``, whether the file the URL names is on disk — lives in the Python
block class, not in the file that was just written, so the registry scan and the
workflow validator own it. This hook sees only the module's text.

**What cannot be checked at all.** Whether a confirm control is actually bound
to a DOM element needs a JavaScript runtime; the backend depends on none and
this hook introduces none. ``host.confirm`` / ``host.cancel`` / ``unmount``
findings are therefore advisory. That is a stated limit of static checking, not
deferred work — the host-owned escape hatch (#2195) is the guarantee that
covers it.

Always exits 0 (PostToolUse cannot block).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Mirrors ``scistudio.blocks.base.interactive.PANEL_API_VERSION``. The parity
# test asserts the two are equal.
PANEL_API_VERSION = "1"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

CODE_IMPORT_FAILED = "import_failed"
CODE_EXPORT_MISSING = "export_missing"
CODE_NOT_A_PANEL_MODULE = "not_a_panel_module"
CODE_API_VERSION_MISMATCH = "api_version_mismatch"
CODE_MOUNT_FAILED = "mount_failed"
CODE_PANEL_CONTROL_MISSING = "panel_control_missing"

_REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "file:")

_PANEL_SUFFIXES = (".js", ".mjs")

#: A written ``.js``/``.mjs`` file is treated as a panel when its path says so.
#: Paired with the ``apiVersion`` content test below, this keeps the hook off
#: ordinary project JavaScript that happens to declare a ``mount`` function.
_PANEL_PATH_RE = re.compile(r"panel", re.IGNORECASE)

_API_VERSION_LITERAL_RE = re.compile(r"""\bapiVersion\b\s*[:=]\s*(['"])([^'"]*)\1""")
_API_VERSION_KEY_RE = re.compile(r"\bapiVersion\b")
_MOUNT_RE = re.compile(r"\bmount\b\s*[:(=]")
_MOUNT_HOST_PARAM_RE = re.compile(
    r"\bmount\b\s*[:=]?\s*(?:async\s+)?(?:function\s*\*?\s*)?\(\s*[A-Za-z_$][\w$]*\s*,\s*([A-Za-z_$][\w$]*)"
)
_UNMOUNT_RE = re.compile(r"\bunmount\b")
_EXPORT_STAR_RE = re.compile(r"\bexport\s*\*")
_EXPORT_DEFAULT_RE = re.compile(r"\bexport\s+default\b")
_STATIC_IMPORT_RE = re.compile(r"""\bimport\b(?:[^;'"()]*?\bfrom\b\s*)?(['"])([^'"]+)\1""")
_DYNAMIC_IMPORT_RE = re.compile(r"""\bimport\s*\(\s*(['"])([^'"]+)\1""")
_EXPORT_FROM_RE = re.compile(r"""\bexport\b[^;'"]*?\bfrom\b\s*(['"])([^'"]+)\1""")


def _read_payload() -> dict:
    """Read the hook payload, degrading to ``{}`` instead of ever crashing.

    #1994: this used to guard only ``OSError``. When a CLI starts a hook with
    no usable stdin, Python sets ``sys.stdin`` to ``None``, so
    ``sys.stdin.read()`` raised ``AttributeError`` — which nothing caught. The
    hook died with **exit 1** before evaluating anything, which the CLI reports
    as a failed hook and then proceeds, so the guard silently did not guard.
    It reproduced identically for all seven hooks, because they all share this
    function.

    An unreadable payload is indistinguishable from an empty one: in both cases
    the hook cannot tell what the agent is about to do. It returns ``{}`` and
    the caller allows the call, which is the behaviour an empty payload already
    had — and blocking every tool call on a stdin quirk would be far worse than
    the exposure it removes. ``BaseException`` is deliberately not caught; only
    the ways reading a missing or closed stream can fail.
    """
    stream = sys.stdin
    if stream is None:
        return {}
    try:
        raw = stream.read()
    except (OSError, ValueError, AttributeError):
        # ValueError: reading a closed file. AttributeError: a replaced stdin
        # that is not a stream at all.
        return {}
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _target_file(payload: dict) -> Path | None:
    """The ``.js``/``.mjs`` file this tool call wrote, if it wrote one."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    candidate = str(tool_input.get("file_path") or "")
    if not candidate:
        return None
    if not candidate.replace("\\", "/").lower().endswith(_PANEL_SUFFIXES):
        return None

    path = Path(candidate)
    if not path.is_absolute():
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("QODER_PROJECT_DIR")
        if project_dir:
            path = Path(project_dir) / candidate
    if not path.is_file():
        return None
    return path


def _is_panel_module(path: Path, source: str) -> bool:
    """Whether this file is plausibly an interactive panel module.

    Either the path says so (a panel lives in a ``panels/`` directory or is
    named ``panel.mjs`` — both are what the scaffolding and the docs produce),
    or the text declares the ``apiVersion`` no other kind of module carries.
    A file that is neither is ordinary project JavaScript and is left alone;
    warning about it would train the author to ignore this hook.
    """
    if _PANEL_PATH_RE.search(str(path).replace("\\", "/")):
        return True
    return bool(_API_VERSION_KEY_RE.search(source))


def strip_js_comments(source: str) -> str:
    """Remove ``//`` and ``/* */`` comments from JavaScript *source*.

    Transcribed from ``scistudio.blocks.base.panel_contract.strip_js_comments``.
    """
    out: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char == "/" and index + 1 < length:
            following = source[index + 1]
            if following == "/" and not (index > 0 and source[index - 1] == ":"):
                newline = source.find("\n", index)
                if newline == -1:
                    break
                index = newline
                continue
            if following == "*":
                end = source.find("*/", index + 2)
                index = length if end == -1 else end + 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _major(version: str) -> str:
    return version.split(".")[0].strip()


def _is_remote_url(url: str) -> bool:
    lowered = url.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _REMOTE_PREFIXES)


def _named_export_re(export_name: str) -> re.Pattern:
    name = re.escape(export_name)
    return re.compile(
        r"\bexport\s+(?:async\s+)?(?:const|let|var|function\s*\*?|class)\s+" + name + r"\b"
        r"|\bexport\s*\{[^}]*\b" + name + r"\b[^}]*\}"
    )


def _has_export(source: str, export_name: str) -> bool:
    if _EXPORT_STAR_RE.search(source):
        return True
    if export_name == "default":
        if _EXPORT_DEFAULT_RE.search(source):
            return True
        return bool(re.search(r"\bexport\s*\{[^}]*\bas\s+default\b[^}]*\}", source))
    return bool(_named_export_re(export_name).search(source))


def _host_binding_names(source: str) -> set:
    names = {"host"}
    names.update(match.group(1) for match in _MOUNT_HOST_PARAM_RE.finditer(source))
    return names


def _references_host_control(source: str, control: str) -> bool:
    escaped = re.escape(control)
    for binding in _host_binding_names(source):
        name = re.escape(binding)
        if re.search(r"\b" + name + r"\s*\.\s*" + escaped + r"\b", source):
            return True
        if re.search(r"\{[^{}]*\b" + escaped + r"\b[^{}]*\}\s*=\s*" + name + r"\b", source):
            return True
    return False


def _remote_import_specifiers(source: str) -> list[str]:
    found: list[str] = []
    for pattern in (_STATIC_IMPORT_RE, _DYNAMIC_IMPORT_RE, _EXPORT_FROM_RE):
        for match in pattern.finditer(source):
            specifier = match.group(2)
            if _is_remote_url(specifier) and specifier not in found:
                found.append(specifier)
    return found


def check_panel_module_source(
    source: str,
    export_name: str = "default",
    api_version: str = PANEL_API_VERSION,
) -> list[tuple[str, str, str, str]]:
    """Return ``(code, severity, message, fix)`` for each finding in *source*.

    A stdlib transcription of
    ``scistudio.blocks.base.panel_contract.check_panel_module_source``. The
    parity test compares the two tuple-for-tuple over a fixture corpus, so the
    strings below must stay byte-identical to the ones there.
    """
    stripped = strip_js_comments(source)
    findings: list[tuple[str, str, str, str]] = []
    name = export_name or "default"

    if not _has_export(stripped, name) and not _has_export(source, name):
        findings.append(
            (
                CODE_EXPORT_MISSING,
                SEVERITY_ERROR,
                f"the module declares no export named {name!r}, which is what the host imports.",
                (
                    "Add `export default { apiVersion, mount }`, or set export_name on the "
                    "PanelManifest to a name the module does export."
                    if name == "default"
                    else f"Add `export const {name} = {{ apiVersion, mount }}`, or set export_name "
                    "on the PanelManifest to a name the module does export."
                ),
            )
        )

    has_api_version = bool(_API_VERSION_KEY_RE.search(stripped) or _API_VERSION_KEY_RE.search(source))
    has_mount = bool(_MOUNT_RE.search(stripped) or _MOUNT_RE.search(source))
    if not has_api_version or not has_mount:
        missing = " and ".join(
            part for part, present in (("apiVersion", has_api_version), ("mount", has_mount)) if not present
        )
        findings.append(
            (
                CODE_NOT_A_PANEL_MODULE,
                SEVERITY_ERROR,
                f"the module never mentions {missing}; the host refuses an export that is not a PanelModule.",
                (
                    'Export an object carrying both, e.g. `export default { apiVersion: "'
                    + api_version
                    + '", mount(container, host) { ... } }`.'
                ),
            )
        )

    literal = _API_VERSION_LITERAL_RE.search(stripped) or _API_VERSION_LITERAL_RE.search(source)
    if literal is not None:
        declared = literal.group(2)
        if _major(declared) != _major(api_version):
            findings.append(
                (
                    CODE_API_VERSION_MISMATCH,
                    SEVERITY_ERROR,
                    (
                        f"the module declares apiVersion {declared!r}, whose major does not match "
                        f"the host's {api_version!r}."
                    ),
                    f'Set apiVersion to "{api_version}" (or a matching major).',
                )
            )

    if not _UNMOUNT_RE.search(stripped):
        findings.append(
            (
                CODE_MOUNT_FAILED,
                SEVERITY_WARNING,
                "no `unmount` appears in the module; mount() must return an object carrying one.",
                "Return `{ unmount() { ... } }` from mount() so the host can tear the panel down.",
            )
        )

    missing_controls = [control for control in ("confirm", "cancel") if not _references_host_control(stripped, control)]
    if missing_controls:
        joined = " or ".join(f"host.{control}" for control in missing_controls)
        findings.append(
            (
                CODE_PANEL_CONTROL_MISSING,
                SEVERITY_WARNING,
                f"the module never references {joined}, so the run may have no way to resume or stop.",
                "Call host.confirm(response) from the panel's confirm control and host.cancel() from its cancel control.",
            )
        )

    for specifier in _remote_import_specifiers(stripped):
        findings.append(
            (
                CODE_IMPORT_FAILED,
                SEVERITY_ERROR,
                f"the module imports {specifier!r} from off-origin; the panel host loads same-origin code only.",
                "Vendor the dependency into the panel's asset_root and import it by a relative path.",
            )
        )

    return findings


def _format_message(target: Path, code: str, severity: str, message: str, fix: str) -> str:
    label = "ERROR" if severity == SEVERITY_ERROR else "warning"
    return f"Panel {label} [{code}] {target}: {message} Fix: {fix}"


def main() -> int:
    target = _target_file(_read_payload())
    if target is None:
        return 0
    try:
        source = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    if not _is_panel_module(target, source):
        return 0
    for code, severity, message, fix in check_panel_module_source(source):
        print(_format_message(target, code, severity, message, fix), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
