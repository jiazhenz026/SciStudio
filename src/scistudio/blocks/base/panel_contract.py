"""Static validation of an interactive block's panel contract (ADR-051, #2196).

An interactive block declares a :class:`~scistudio.blocks.base.interactive.PanelManifest`
naming a JavaScript module the frontend panel host imports and mounts. Nothing
checked that module or the manifest that points at it, so every way of getting
it wrong reached the user as a modal that opened and immediately errored — with
the reason living only in the browser. Every one of those failures is decidable
without running the module, and this is where that decision is made once.

**One implementation, three surfaces.** The registry scan
(:func:`scistudio.blocks.registry._capability._validate_interactive_capability`)
refuses a hard-invalid block and reports why through ``reload_blocks``;
:func:`scistudio.workflow.validator.validate_workflow` refuses a workflow whose
interactive block is hard-invalid before the run reaches a pause; and the
provisioned ``check_panel_contract`` PostToolUse hook warns right after a panel
module is written. The hook is the one that cannot import this module — every
provisioned hook script runs under the *base* interpreter and imports the
standard library and nothing else (see
:func:`scistudio.agent_provisioning.hooks.hook_interpreter`) — so it carries a
stdlib transcription of the source checks below, and
``tests/agent_provisioning/test_hook_panel_contract_parity.py`` fails if the two
ever disagree on a fixture.

**Placement.** This module sits beside :mod:`scistudio.blocks.base.interactive`,
which owns :class:`PanelManifest` and :data:`PANEL_API_VERSION` — the contract
being validated. It imports that module and the standard library, nothing else,
so the registry, the workflow validator, and the tests can all import it without
a cycle: ``blocks.base.interactive`` imports neither the registry nor the
workflow package. It deliberately does **not** import
:mod:`scistudio.previewers.assets` for the asset-suffix allowlist, because that
would drag the whole preview subsystem (registry, router, sessions) into the
block-scan path for one frozen set; :data:`_ALLOWED_ASSET_SUFFIXES` is copied
here and ``tests/blocks/test_panel_contract.py`` asserts the copy still equals
the original.

**Vocabulary.** Every diagnostic names the failure code the panel host would
show the user (``frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts``),
so the authoring agent reads the same word the user's error text will say. The
one exception is :data:`CODE_PANEL_CONTROL_MISSING`, which has no frontend
counterpart because the frontend cannot detect it either — a panel that never
calls ``host.confirm`` strands the user rather than failing.

**Two severities.** A hard error is a failure that is certain: the manifest or
the file it names cannot produce a mountable module. An advisory (``warning``)
is a heuristic: a text search cannot prove a control is wired to a button, so
those never block. The module is never executed — the backend depends on no
JavaScript runtime and this does not introduce one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.blocks.base.interactive import PANEL_API_VERSION

# --------------------------------------------------------------------------
# Vocabulary shared with the frontend panel host.
# --------------------------------------------------------------------------

SEVERITY_ERROR = "error"
"""A certain runtime failure. Rejects the block and invalidates the workflow."""

SEVERITY_WARNING = "warning"
"""A heuristic finding. Reported, never blocking."""

CODE_INVALID_MODULE_URL = "invalid_module_url"
CODE_REMOTE_URL_REJECTED = "remote_url_rejected"
CODE_IMPORT_FAILED = "import_failed"
CODE_EXPORT_MISSING = "export_missing"
CODE_NOT_A_PANEL_MODULE = "not_a_panel_module"
CODE_API_VERSION_MISMATCH = "api_version_mismatch"
CODE_MOUNT_FAILED = "mount_failed"
CODE_PANEL_CONTROL_MISSING = "panel_control_missing"
"""Advisory-only. No frontend counterpart: a panel with no confirm/cancel
control does not fail to mount, it strands the user. The host-owned escape
hatch (#2195) is the guarantee that covers it."""

#: URL prefixes that are off-origin and refused before any import is attempted.
#: Mirrors ``_REMOTE_PREFIXES`` in :mod:`scistudio.previewers.assets`.
_REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "file:")

#: Asset suffixes the panel route will serve. Copy of
#: ``scistudio.previewers.assets._ALLOWED_ASSET_SUFFIXES``; the copy is checked
#: against the original by test rather than imported (see the module docstring).
_ALLOWED_ASSET_SUFFIXES = frozenset({".js", ".mjs", ".css", ".map", ".json", ".svg", ".woff", ".woff2"})

#: Router prefix + route of ``serve_panel_asset``
#: (``src/scistudio/api/routes/blocks.py``). A ``module_url`` that does not take
#: this shape resolves to no route at all and 404s.
_PANEL_ROUTE_TEMPLATE = "/api/blocks/panels/{panel_id}/"

#: Panel ids the app ships and the frontend resolves from its built-in registry
#: (``InteractiveModals.tsx``) rather than by importing a module. They carry no
#: ``module_url`` by design.
_CORE_PANEL_ID_PREFIX = "core."


@dataclass(frozen=True)
class PanelDiagnostic:
    """One finding about an interactive block's panel contract.

    ``code`` is the frontend failure code the same fault would surface as, so a
    diagnostic and the user's error text use the same word.
    """

    code: str
    """Frontend failure code (see the module docstring)."""
    severity: str
    """:data:`SEVERITY_ERROR` or :data:`SEVERITY_WARNING`."""
    message: str
    """What is wrong, in one line."""
    fix: str
    """What to change to make it right."""

    @property
    def is_error(self) -> bool:
        """Whether this finding is a certain failure that must block."""
        return self.severity == SEVERITY_ERROR

    def render(self) -> str:
        """One-line rendering carrying the code, the fault, and the repair."""
        return f"panel {self.code}: {self.message} Fix: {self.fix}"


def has_errors(diagnostics: Iterable[PanelDiagnostic]) -> bool:
    """Whether *diagnostics* contains at least one blocking finding."""
    return any(diagnostic.is_error for diagnostic in diagnostics)


# --------------------------------------------------------------------------
# Manifest and filesystem checks — deterministic.
# --------------------------------------------------------------------------


def is_remote_url(url: str) -> bool:
    """Whether *url* points off-origin and is refused by the panel host."""
    lowered = url.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _REMOTE_PREFIXES)


def _major(version: str) -> str:
    return version.split(".")[0].strip()


def _resolve_asset(asset_root: str, relative_path: str) -> Path | None:
    """Resolve *relative_path* under *asset_root*, or ``None`` if it escapes.

    Mirrors :func:`scistudio.previewers.assets.resolve_asset`'s confinement so
    this check and the route that serves the file agree about which paths exist.
    """
    root = Path(asset_root).resolve()
    candidate = (root / relative_path.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _check_asset_url(
    *,
    url: str,
    panel_id: str,
    asset_root: str | None,
    label: str,
    missing_severity: str,
) -> tuple[list[PanelDiagnostic], Path | None]:
    """Check one declared asset URL, returning findings and the resolved file.

    Shared by ``module_url`` and each ``css`` entry: both must be site-relative,
    take the panel route's shape, and resolve to an allowed file confined under
    ``asset_root``. They differ only in what a missing file means, which is
    *missing_severity* — a module that is not there cannot mount, while the host
    injects a stylesheet best-effort and mounts the panel without it
    (``injectManifestCss`` in ``panelModuleLoader.ts``).
    """
    if is_remote_url(url):
        return (
            [
                PanelDiagnostic(
                    code=CODE_REMOTE_URL_REJECTED,
                    severity=SEVERITY_ERROR,
                    message=f"{label} {url!r} is not same-origin; the panel host refuses remote code.",
                    fix=(
                        "Ship the file inside the package and point the URL at "
                        f"{_PANEL_ROUTE_TEMPLATE.format(panel_id=panel_id)}<file>."
                    ),
                )
            ],
            None,
        )

    expected_prefix = _PANEL_ROUTE_TEMPLATE.format(panel_id=panel_id)
    if not url.startswith(expected_prefix) or url == expected_prefix:
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=SEVERITY_ERROR,
                    message=(
                        f"{label} {url!r} does not match this panel's asset route "
                        f"{expected_prefix}<file>, so it resolves to no route and 404s."
                    ),
                    fix=f"Set it to {expected_prefix}<file>, using the manifest's own panel_id.",
                )
            ],
            None,
        )

    relative_path = url[len(expected_prefix) :]
    if not asset_root:
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=SEVERITY_ERROR,
                    message=f"{label} is declared but the manifest sets no asset_root, so nothing can be served.",
                    fix=(
                        "Set asset_root on the PanelManifest to the directory holding the panel's files, "
                        "e.g. asset_root=str(Path(__file__).resolve().parent / 'panel')."
                    ),
                )
            ],
            None,
        )

    root = Path(asset_root)
    if not root.is_dir():
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=SEVERITY_ERROR,
                    message=f"asset_root {asset_root!r} is not a directory, so {label} cannot be served.",
                    fix="Point asset_root at a directory that ships with the package.",
                )
            ],
            None,
        )

    resolved = _resolve_asset(asset_root, relative_path)
    if resolved is None:
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=SEVERITY_ERROR,
                    message=f"{label} {url!r} escapes the asset_root confinement and is refused.",
                    fix="Keep the file inside asset_root; the route never serves a path outside it.",
                )
            ],
            None,
        )

    suffix = resolved.suffix.lower()
    if suffix not in _ALLOWED_ASSET_SUFFIXES:
        allowed = ", ".join(sorted(_ALLOWED_ASSET_SUFFIXES))
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=SEVERITY_ERROR,
                    message=f"{label} names a {suffix or '<no suffix>'} file, which the asset route will not serve.",
                    fix=f"Use one of the allowed asset suffixes: {allowed}.",
                )
            ],
            None,
        )

    if not resolved.is_file():
        return (
            [
                PanelDiagnostic(
                    code=CODE_IMPORT_FAILED,
                    severity=missing_severity,
                    message=f"{label} {url!r} names a file that is not on disk under asset_root.",
                    fix=f"Create {relative_path!r} under asset_root, or correct the URL.",
                )
            ],
            None,
        )

    return [], resolved


# --------------------------------------------------------------------------
# Panel module source checks — static, never executed.
# --------------------------------------------------------------------------

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


def strip_js_comments(source: str) -> str:
    """Remove ``//`` and ``/* */`` comments from JavaScript *source*.

    A deliberately small scanner: it does not track string or regex literals,
    so text that merely looks like a comment inside a template literal is
    dropped too. That direction is the safe one — every hard-error check below
    re-tests the raw source before reporting, so stripping can only ever cost an
    advisory, never invent a blocking finding. ``//`` preceded by ``:`` is left
    alone so a URL inside a string survives for the remote-import check.
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


def _named_export_re(export_name: str) -> re.Pattern[str]:
    name = re.escape(export_name)
    return re.compile(
        r"\bexport\s+(?:async\s+)?(?:const|let|var|function\s*\*?|class)\s+" + name + r"\b"
        r"|\bexport\s*\{[^}]*\b" + name + r"\b[^}]*\}"
    )


def _has_export(source: str, export_name: str) -> bool:
    """Whether *source* plausibly declares an export named *export_name*."""
    if _EXPORT_STAR_RE.search(source):
        # ``export * from ...`` re-exports names this scanner cannot enumerate;
        # absence is unprovable, so never claim the export is missing.
        return True
    if export_name == "default":
        if _EXPORT_DEFAULT_RE.search(source):
            return True
        return bool(re.search(r"\bexport\s*\{[^}]*\bas\s+default\b[^}]*\}", source))
    return bool(_named_export_re(export_name).search(source))


def _host_binding_names(source: str) -> set[str]:
    """Names the module may be calling the host API by.

    ``mount(container, host)`` is the documented signature, but the second
    parameter is the author's to name and ``mount(el, h)`` is just as correct.
    Reading the binding out of the signature is what keeps the advisory below
    from firing on a perfectly good panel — and a false advisory is the one
    outcome a non-blocking check cannot afford, because it teaches the author to
    ignore the check.
    """
    names = {"host"}
    names.update(match.group(1) for match in _MOUNT_HOST_PARAM_RE.finditer(source))
    return names


def _references_host_control(source: str, control: str) -> bool:
    """Whether *source* calls ``<host>.<control>``, destructured or not."""
    escaped = re.escape(control)
    for binding in _host_binding_names(source):
        name = re.escape(binding)
        if re.search(r"\b" + name + r"\s*\.\s*" + escaped + r"\b", source):
            return True
        # ``const { confirm, cancel } = host`` is the other common spelling.
        if re.search(r"\{[^{}]*\b" + escaped + r"\b[^{}]*\}\s*=\s*" + name + r"\b", source):
            return True
    return False


def _remote_import_specifiers(source: str) -> list[str]:
    """Return every off-origin module specifier *source* imports."""
    found: list[str] = []
    for pattern in (_STATIC_IMPORT_RE, _DYNAMIC_IMPORT_RE, _EXPORT_FROM_RE):
        for match in pattern.finditer(source):
            specifier = match.group(2)
            if is_remote_url(specifier) and specifier not in found:
                found.append(specifier)
    return found


def check_panel_module_source(
    source: str,
    *,
    export_name: str = "default",
    api_version: str = PANEL_API_VERSION,
) -> list[PanelDiagnostic]:
    """Check a panel module's *source* text against the ``PanelModule`` contract.

    Never executes the module. Hard errors are only raised for evidence that is
    absent from both the comment-stripped and the raw source, so the comment
    scanner cannot manufacture one.

    ``host.confirm`` / ``host.cancel`` / ``unmount`` are advisory by design: a
    text search finds the name, not the binding, so it cannot prove the control
    is attached to a DOM element. Proving that needs a JavaScript runtime, which
    the backend deliberately does not have; the host-owned escape hatch (#2195)
    is what actually guarantees the user can always leave the panel. This is a
    stated limit of static checking, not deferred work.
    """
    stripped = strip_js_comments(source)
    diagnostics: list[PanelDiagnostic] = []
    name = export_name or "default"

    if not _has_export(stripped, name) and not _has_export(source, name):
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_EXPORT_MISSING,
                severity=SEVERITY_ERROR,
                message=f"the module declares no export named {name!r}, which is what the host imports.",
                fix=(
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
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_NOT_A_PANEL_MODULE,
                severity=SEVERITY_ERROR,
                message=f"the module never mentions {missing}; the host refuses an export that is not a PanelModule.",
                fix=(
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
            diagnostics.append(
                PanelDiagnostic(
                    code=CODE_API_VERSION_MISMATCH,
                    severity=SEVERITY_ERROR,
                    message=(
                        f"the module declares apiVersion {declared!r}, whose major does not match "
                        f"the host's {api_version!r}."
                    ),
                    fix=f'Set apiVersion to "{api_version}" (or a matching major).',
                )
            )

    if not _UNMOUNT_RE.search(stripped):
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_MOUNT_FAILED,
                severity=SEVERITY_WARNING,
                message="no `unmount` appears in the module; mount() must return an object carrying one.",
                fix="Return `{ unmount() { ... } }` from mount() so the host can tear the panel down.",
            )
        )

    missing_controls = [control for control in ("confirm", "cancel") if not _references_host_control(stripped, control)]
    if missing_controls:
        joined = " or ".join(f"host.{control}" for control in missing_controls)
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_PANEL_CONTROL_MISSING,
                severity=SEVERITY_WARNING,
                message=f"the module never references {joined}, so the run may have no way to resume or stop.",
                fix="Call host.confirm(response) from the panel's confirm control and host.cancel() from its cancel control.",
            )
        )

    for specifier in _remote_import_specifiers(stripped):
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_IMPORT_FAILED,
                severity=SEVERITY_ERROR,
                message=f"the module imports {specifier!r} from off-origin; the panel host loads same-origin code only.",
                fix="Vendor the dependency into the panel's asset_root and import it by a relative path.",
            )
        )

    return diagnostics


# --------------------------------------------------------------------------
# Whole-manifest entry points.
# --------------------------------------------------------------------------


#: Source-check results keyed by ``(path, mtime_ns, size, export_name,
#: api_version)``. The workflow validator runs the whole check set on every
#: editor autosave, so a panel bundle would otherwise be re-read and re-scanned
#: for every keystroke-driven save. The key changes the moment the file does, so
#: a stale entry cannot outlive an edit — which is the whole point of checking
#: the module at run start rather than only at scan time.
_SOURCE_DIAGNOSTIC_CACHE: dict[tuple[str, int, int, str, str], tuple[PanelDiagnostic, ...]] = {}

#: Bound on the cache. Panels are few; this only stops an unbounded process
#: lifetime from accumulating one entry per edit of every panel ever opened.
_SOURCE_DIAGNOSTIC_CACHE_MAX = 256


def _cached_module_source_diagnostics(
    module_path: Path,
    *,
    export_name: str,
    api_version: str,
) -> list[PanelDiagnostic]:
    """Read and check a panel module, reusing the last result for an unchanged file."""
    try:
        stat = module_path.stat()
        key = (str(module_path), stat.st_mtime_ns, stat.st_size, export_name, api_version)
    except OSError:
        key = None
    if key is not None:
        cached = _SOURCE_DIAGNOSTIC_CACHE.get(key)
        if cached is not None:
            return list(cached)

    try:
        source = module_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [
            PanelDiagnostic(
                code=CODE_IMPORT_FAILED,
                severity=SEVERITY_ERROR,
                message=f"the panel module could not be read as UTF-8 text ({type(exc).__name__}).",
                fix="Ship the panel module as a UTF-8 encoded ES module.",
            )
        ]

    diagnostics = check_panel_module_source(source, export_name=export_name, api_version=api_version)
    if key is not None:
        if len(_SOURCE_DIAGNOSTIC_CACHE) >= _SOURCE_DIAGNOSTIC_CACHE_MAX:
            _SOURCE_DIAGNOSTIC_CACHE.clear()
        _SOURCE_DIAGNOSTIC_CACHE[key] = tuple(diagnostics)
    return diagnostics


def validate_panel(
    *,
    panel_id: str,
    module_url: str = "",
    export_name: str = "default",
    css: Sequence[str] = (),
    api_version: str = PANEL_API_VERSION,
    asset_root: str | None = None,
) -> list[PanelDiagnostic]:
    """Validate one panel manifest and, when it resolves, its module source.

    A core panel — one the app bundles and the frontend resolves from its
    built-in registry — carries no ``module_url`` and no ``asset_root`` by
    design, so there is nothing here to check and the result is empty. A panel
    id outside the ``core.`` namespace that still declares no ``module_url``
    gets an advisory instead: it is far more likely to be a package author who
    forgot the URL than a new built-in.
    """
    diagnostics: list[PanelDiagnostic] = []
    url = (module_url or "").strip()

    if not panel_id:
        return [
            PanelDiagnostic(
                code=CODE_INVALID_MODULE_URL,
                severity=SEVERITY_ERROR,
                message="the panel manifest has an empty panel_id, so no panel can be resolved.",
                fix="Give the PanelManifest a stable panel_id, e.g. '<package>.<block>'.",
            )
        ]

    if not url:
        if asset_root:
            return [
                PanelDiagnostic(
                    code=CODE_INVALID_MODULE_URL,
                    severity=SEVERITY_ERROR,
                    message="the manifest declares an asset_root but no module_url, so nothing is ever imported.",
                    fix=(
                        "Set module_url to "
                        f"{_PANEL_ROUTE_TEMPLATE.format(panel_id=panel_id)}<file> naming the module under asset_root."
                    ),
                )
            ]
        if not panel_id.startswith(_CORE_PANEL_ID_PREFIX):
            return [
                PanelDiagnostic(
                    code=CODE_INVALID_MODULE_URL,
                    severity=SEVERITY_WARNING,
                    message=(
                        f"panel {panel_id!r} declares no module_url, so the frontend will look for a built-in "
                        "panel registered under that id; a package-provided panel must ship a module."
                    ),
                    fix=(
                        "Set module_url and asset_root on the PanelManifest, or use a 'core.' panel id "
                        "that the app actually bundles."
                    ),
                )
            ]
        return []

    if api_version and _major(api_version) != _major(PANEL_API_VERSION):
        diagnostics.append(
            PanelDiagnostic(
                code=CODE_API_VERSION_MISMATCH,
                severity=SEVERITY_ERROR,
                message=(
                    f"the manifest declares api_version {api_version!r}, whose major does not match "
                    f"the host's {PANEL_API_VERSION!r}; the host refuses before importing."
                ),
                fix=f'Set api_version="{PANEL_API_VERSION}" on the PanelManifest.',
            )
        )

    module_findings, module_path = _check_asset_url(
        url=url,
        panel_id=panel_id,
        asset_root=asset_root,
        label="module_url",
        missing_severity=SEVERITY_ERROR,
    )
    diagnostics.extend(module_findings)

    for css_url in css:
        css_findings, _ = _check_asset_url(
            url=(css_url or "").strip(),
            panel_id=panel_id,
            asset_root=asset_root,
            # A stylesheet that is not on disk is the one asset fault the host
            # survives: injectManifestCss appends the <link>, the request 404s,
            # and the panel still mounts. Reported, never blocking.
            label="css entry",
            missing_severity=SEVERITY_WARNING,
        )
        diagnostics.extend(css_findings)

    if module_path is not None:
        diagnostics.extend(
            _cached_module_source_diagnostics(
                module_path,
                export_name=export_name,
                api_version=api_version or PANEL_API_VERSION,
            )
        )

    return diagnostics


def diagnostics_for_manifest(manifest: Any) -> list[PanelDiagnostic]:
    """Validate a :class:`PanelManifest` instance (the block-class side)."""
    return validate_panel(
        panel_id=getattr(manifest, "panel_id", "") or "",
        module_url=getattr(manifest, "module_url", "") or "",
        export_name=getattr(manifest, "export_name", "default") or "default",
        css=tuple(getattr(manifest, "css", ()) or ()),
        api_version=getattr(manifest, "api_version", PANEL_API_VERSION) or PANEL_API_VERSION,
        asset_root=getattr(manifest, "asset_root", None),
    )


def diagnostics_for_spec(spec: Any) -> list[PanelDiagnostic]:
    """Validate the panel a registered :class:`BlockSpec` carries.

    The spec keeps the manifest's wire form (``panel_manifest``) and the
    backend-only ``panel_asset_root`` separately, because ``to_dict()`` drops
    the root before it goes to the browser. A spec with no panel manifest is not
    an interactive block and yields nothing.

    This is the run-start half of the check, and it is not redundant with the
    scan-time half: editing a panel's ``.js`` file changes nothing the registry
    watches — Tier-1 hot reload keys on the block's ``.py`` mtime — so a block
    that registered cleanly can be pointing at a module that has since been
    broken or deleted.
    """
    manifest = getattr(spec, "panel_manifest", None)
    if not isinstance(manifest, dict):
        return []
    css = manifest.get("css") or ()
    return validate_panel(
        panel_id=str(manifest.get("panel_id") or ""),
        module_url=str(manifest.get("module_url") or ""),
        export_name=str(manifest.get("export_name") or "default"),
        css=tuple(str(entry) for entry in css),
        api_version=str(manifest.get("api_version") or PANEL_API_VERSION),
        asset_root=getattr(spec, "panel_asset_root", None),
    )


__all__ = [
    "CODE_API_VERSION_MISMATCH",
    "CODE_EXPORT_MISSING",
    "CODE_IMPORT_FAILED",
    "CODE_INVALID_MODULE_URL",
    "CODE_MOUNT_FAILED",
    "CODE_NOT_A_PANEL_MODULE",
    "CODE_PANEL_CONTROL_MISSING",
    "CODE_REMOTE_URL_REJECTED",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "PanelDiagnostic",
    "check_panel_module_source",
    "diagnostics_for_manifest",
    "diagnostics_for_spec",
    "has_errors",
    "is_remote_url",
    "strip_js_comments",
    "validate_panel",
]
