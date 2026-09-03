"""The ADR-048 previewer compatibility shim (FR-042, FR-043, FR-044).

**Delete this file to remove the shim.** It is one module on purpose: ADR-054
§9.4 says a shim with no removal condition is a second implementation with a
friendly name, ADR-048 addendum 1 §5 states the condition, and FR-044 asks that
meeting it be a deletion rather than a redesign. The complete removal is listed
at the bottom of this docstring so a future reader does not have to hunt.

**What it does.** A previewer written against the ADR-048 module form is an ES
module at a same-origin URL, exporting a named symbol, carrying its own
``apiVersion``, and mounted with a read-only host API. The two loaders that
mounted such a module are deleted (T-007, SC-002); nothing here restores one.
Instead this module *wraps* the retired form into the shape the new mechanism
already mounts: a **panel directory** — ``panel.json`` plus a self-contained
entry document — served through the merged asset route (D-007, D-008, FR-021).
The frame, the per-mount token, the handshake and the D-017 message contract
are the ones every other panel gets, unchanged, because they are the only ones
there are.

**Where the wrapping happens, and why here rather than in the host.** The other
possibility was a second mount path in ``frontend/src/panels/`` that imported an
ES module beside the frame. That is a second loader with a different name, and
SC-001 (one API version definition) and SC-002 (one loader) are the two success
criteria it would break; Story 5 — a maintainer a year from now finds one
mechanism — is what those criteria are for. Wrapping on this side costs the
frontend nothing at all: the host cannot tell a shimmed previewer from a
migrated panel, because by the time it sees one there is no difference left.

**What it must not do (FR-043, SC-009).** The shim grants nothing new. The
generated declaration is ``capability: "displaying"``, so the host's capability
gate drops ``emit`` structurally (``panelCapability.ts``); ``init.bindings`` is
whatever the mounting surface passes for a displaying mount, which is ``null``;
and the adapter in the generated document constructs no emission path at all. A
package obtains the producing capability and the session bindings by migrating,
not by waiting.

**Removal — the exact list.** When ADR-048 addendum 1 §5's three clauses hold:

* this file, ``src/scistudio/panels/compat.py``;
* its test, ``tests/panels/test_compat_shim.py``;
* its host-side proof, ``frontend/src/panels/panelCompat.test.tsx``;
* the two places in ``src/scistudio/panels/__init__.py`` marked ``ADR-048
  compatibility shim``: the import of :func:`install_compat_panels`, and the
  call to it in :func:`scistudio.panels.build_preview_service` together with the
  comment above that call;
* the fixture previewer the test mounts, and its bundle,
  ``tests/fixtures/scistudio-blocks-fixture/src/scistudio_blocks_fixture/previewers/``;

and, in the same change but owned by the addendum rather than by this file, the
four alias modules under ``src/scistudio/previewers/``, the
``scistudio.previewers`` entry-point group, the two retained asset routes, and
the retired drop-in directory names.
"""

from __future__ import annotations

import atexit
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from scistudio.core.panels import PanelCapability, PanelManifest, PanelTier
from scistudio.panels.assets import is_allowed_asset_suffix, is_safe_panel_id, validate_manifest
from scistudio.panels.discovery import DiscoveredPanel, PanelDiscovery
from scistudio.panels.models import FrontendManifest, PanelSpec
from scistudio.stability import internal

if TYPE_CHECKING:
    from scistudio.panels.registry import PanelRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "COMPAT_SHIM_ENTRY",
    "COMPAT_SHIM_MAX_BUNDLE_BYTES",
    "COMPAT_SHIM_MAX_BUNDLE_FILES",
    "CompatShimError",
    "build_compat_panel",
    "compat_shim_document",
    "compat_shim_root",
    "install_compat_panels",
    "is_compat_panel",
    "module_entry_path",
    "shimmable_specs",
]

#: The generated document's file name inside a shim panel directory. It is not
#: ``index.html`` because the bundle being wrapped is copied in beside it and
#: may well ship an ``index.html`` of its own.
COMPAT_SHIM_ENTRY = "__panel_compat__.html"

#: The declaration file the generated directory carries, so a person looking at
#: a shim panel sees the same two files every other panel directory holds.
COMPAT_SHIM_DECLARATION = "panel.json"

#: Bounds on the bundle copied in beside the document. A previewer bundle is a
#: viewer module and its assets; anything past these is a package doing
#: something the shim was not written for, and it is refused with a diagnostic
#: rather than copied.
COMPAT_SHIM_MAX_BUNDLE_FILES = 200
COMPAT_SHIM_MAX_BUNDLE_BYTES = 32 * 1024 * 1024

#: Marker written into the generated declaration so a reader — and
#: :func:`is_compat_panel` — can tell a wrapped previewer from a real panel.
COMPAT_SHIM_FEATURE = "adr048-compat-shim"

_shim_root: Path | None = None


class CompatShimError(RuntimeError):
    """One previewer could not be wrapped. Carries the diagnostic to record."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# The generated document
# ---------------------------------------------------------------------------

#: The shim's adapter document, with ``"__SCISTUDIO_COMPAT__"`` standing in for
#: the JSON configuration :func:`compat_shim_document` substitutes.
#:
#: It is a panel document like any other — markup, styles and script in one file
#: (FR-002, A-004) — whose body happens to be an adapter rather than a renderer.
#: It speaks the D-017 contract to the host and the retired ADR-048
#: ``PreviewHostApi`` to the module it wraps, and the mapping between the two is
#: the table in ``mountWrappedModule`` below.
_COMPAT_DOCUMENT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Compatibility panel &mdash; SciStudio</title>
<!--
  ADR-054 spec 1, T-012 (#2229) - the ADR-048 previewer compatibility shim
  (FR-042, FR-043).

  GENERATED. Written by src/scistudio/panels/compat.py at registry build time
  and served from a disposable directory; editing it edits nothing that
  survives a reload. The previewer it wraps is the ES module copied in beside
  it, and the way to change what you see here is to migrate that previewer to
  the panel contract.

  What this document grants the module it mounts is exactly the ADR-048
  read-only host API and nothing else (FR-043). There is no emit path in this
  file and no variable bindings are read: a package obtains those by migrating.
-->
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: transparent;
    color: #1c211b;
    font: 12px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  body { padding: 8px; }
  .muted { color: rgba(28, 33, 27, 0.6); }
  #root { min-height: 24px; }
</style>
</head>
<body>
<div id="root"><p class="muted">Waiting for the host&hellip;</p></div>

<script type="module">
(function () {
  "use strict";

  /* The D-011 envelope. Duplicated per FR-034; do not factor it out. */
  var PANEL_MESSAGE_MARKER = 1;

  /* Written by src/scistudio/panels/compat.py. Standing alone it is a string,
     which is what keeps this template openable in a browser. */
  var COMPAT = "__SCISTUDIO_COMPAT__";

  var token = null;
  var context = null;
  var requestSeq = 0;
  var pending = Object.create(null);
  var torndown = false;
  var instance = null;
  var envelope = null;

  function post(type, payload) {
    if (token === null || torndown) return false;
    try {
      window.parent.postMessage(
        { scistudio_panel: PANEL_MESSAGE_MARKER, token: token, type: type, payload: payload },
        "*"
      );
      return true;
    } catch (err) {
      return false;
    }
  }

  /*
   * Every failure before `ready` is the same failure (FR-014). The host treats
   * a pre-handshake `error` as a handshake failure, which is what draws its own
   * error surface naming the panel and mounts the backend-named fallback so the
   * data stays visible. After `ready` the same message is a diagnostic, which
   * is the right severity for a module that mounted and then misbehaved.
   */
  function fail(message, detail) {
    post("error", { message: String(message), detail: detail || null });
  }

  function request(type, body) {
    return new Promise(function (resolve, reject) {
      requestSeq += 1;
      var id = "r" + requestSeq;
      pending[id] = { resolve: resolve, reject: reject };
      var payload = { request_id: id };
      Object.keys(body).forEach(function (key) { payload[key] = body[key]; });
      if (!post(type, payload)) {
        delete pending[id];
        reject(new Error("the host could not be reached"));
      }
    });
  }

  function settle(id, value) {
    var waiting = pending[id];
    if (!waiting) return false;
    delete pending[id];
    waiting.resolve(value);
    return true;
  }

  function failRequest(id, message) {
    var waiting = pending[id];
    if (!waiting) return false;
    delete pending[id];
    waiting.reject(new Error(message));
    return true;
  }

  function envelopeOf(value) {
    if (value && typeof value === "object") return value;
    return { payload: {}, metadata: {}, resources: [], diagnostics: [], error: null, kind: "" };
  }

  function adopt(value) {
    if (value && typeof value === "object") envelope = value;
    return envelope;
  }

  /*
   * The retired ADR-048 `PreviewHostApi`, expressed in the D-017 contract.
   *
   *   apiVersion        <- init.api_version (the backend's, D-010)
   *   previewSessionId  <- the envelope's own `session_id`, or null
   *   envelope / kind   <- init.target, then update.changed.target
   *   provider          <- init.panel_id and the descriptor's feature tags
   *   session.refresh   -> `read` with an empty query patch
   *   session.patchQuery-> `read` with the patch
   *   session.getResource-> `resource`
   *   session.resources <- the current envelope's own resource descriptors
   *   assetUrl          <- init.asset_base_url, no message at all
   *   exportArtifact    -> `host_action` with action "export"
   *   saveArtifact      -> `host_action` with action "download"
   *   reportError       -> `error`
   *
   * `emit` appears nowhere, and no binding is read (FR-043, SC-009).
   */
  function hostApi() {
    return {
      apiVersion: context.api_version,
      previewSessionId: envelope && typeof envelope.session_id === "string" ? envelope.session_id : null,
      get envelope() { return envelope; },
      get kind() { return envelope && envelope.kind ? envelope.kind : ""; },
      provider: {
        panelId: context.panel_id,
        features: COMPAT.features || [],
        source: envelope && envelope.target ? envelope.target.source || null : null
      },
      session: {
        refresh: function () { return request("read", { query: {} }).then(adopt); },
        patchQuery: function (query) {
          return request("read", { query: query || {} }).then(adopt);
        },
        getResource: function (resourceId, params) {
          return request("resource", { resource_id: String(resourceId), params: params || null });
        },
        get resources() {
          return envelope && Array.isArray(envelope.resources) ? envelope.resources : [];
        }
      },
      assetUrl: function (assetPath) {
        return context.asset_base_url + String(assetPath === undefined ? "" : assetPath).replace(/^\\/+/, "");
      },
      exportArtifact: function (req) {
        return request("host_action", { action: "export", params: req || null }).then(function () {});
      },
      saveArtifact: function (req) {
        return request("host_action", { action: "download", params: req || null }).then(function () {});
      },
      reportError: function (message, detail) {
        fail(message, detail);
      }
    };
  }

  function mountWrappedModule() {
    var root = document.getElementById("root");
    root.textContent = "";
    return import(COMPAT.entry_url).then(function (mod) {
      var wrapped = mod ? mod[COMPAT.export_name] : null;
      if (!wrapped || typeof wrapped.mount !== "function") {
        throw new Error(
          "the previewer module exports no mountable " + JSON.stringify(COMPAT.export_name)
        );
      }
      instance = wrapped.mount(root, hostApi());
      if (!instance || typeof instance.unmount !== "function") {
        throw new Error("the previewer module's mount() returned no unmountable instance");
      }
    });
  }

  function onMessage(event) {
    var data = event.data;
    if (!data || typeof data !== "object") return;
    if (data.scistudio_panel !== PANEL_MESSAGE_MARKER) return;
    if (typeof data.type !== "string") return;
    var payload = data.payload && typeof data.payload === "object" ? data.payload : {};

    if (token === null) {
      if (data.type !== "init" || typeof data.token !== "string" || data.token === "") return;
      token = data.token;
      context = payload;
      envelope = envelopeOf(payload.target);
      /*
       * `ready` is answered only once the wrapped module has mounted. A module
       * that fails to load, exports nothing mountable, or throws on mount
       * therefore leaves the handshake unanswered and reports why, which is the
       * one load-failure behaviour of FR-014 rather than a second one.
       */
      mountWrappedModule().then(
        function () {
          post("ready", { api_version: COMPAT.api_version });
        },
        function (err) {
          fail("the previewer module could not be mounted: " + (err && err.message ? err.message : err), {
            entry_url: COMPAT.entry_url,
            export_name: COMPAT.export_name
          });
        }
      );
      return;
    }

    if (data.token !== token) return;

    switch (data.type) {
      case "update":
        if (payload.changed && typeof payload.changed === "object" && "target" in payload.changed) {
          adopt(envelopeOf(payload.changed.target));
          if (instance && typeof instance.update === "function") {
            try {
              instance.update(envelope);
            } catch (err) {
              fail("the previewer module failed to take an update: " + (err && err.message ? err.message : err));
            }
          }
        }
        break;
      case "read_result":
        settle(payload.request_id, payload.window);
        break;
      case "resource_result":
        settle(payload.request_id, payload.resource);
        break;
      case "host_action_result":
        if (payload.ok === false) {
          failRequest(payload.request_id, typeof payload.detail === "string" ? payload.detail : "the host declined");
        } else {
          settle(payload.request_id, payload.detail);
        }
        break;
      case "error":
        /* The retired form has no inbound error channel of its own, so a host
           error that does not end a request has nowhere to go but the host's
           own diagnostics, where it already is. */
        if (typeof payload.request_id === "string") {
          failRequest(payload.request_id, String(payload.message || "the request failed"));
        }
        break;
      case "state_request":
        /* The retired form has no state hook, so there is never a snapshot to
           carry across a remount (FR-031). Answering keeps the host from
           waiting out its bounded timeout. */
        post("state", { state: null });
        break;
      case "teardown":
        torndown = true;
        window.removeEventListener("message", onMessage);
        if (instance && typeof instance.unmount === "function") {
          try {
            instance.unmount();
          } catch (err) {
            /* The frame is going away; a failed teardown is not actionable. */
          }
        }
        instance = null;
        break;
      default:
        break;
    }
  }

  window.addEventListener("message", onMessage);
})();
</script>
</body>
</html>
"""

_COMPAT_CONFIG_PLACEHOLDER = '"__SCISTUDIO_COMPAT__"'


@internal()
def compat_shim_document(
    *,
    entry_url: str,
    export_name: str,
    api_version: str,
    features: tuple[str, ...] = (),
) -> str:
    """Return the generated document for one wrapped previewer.

    Args:
        entry_url: The URL the document imports the wrapped module from. It is
            relative to the document, so it resolves onto the merged asset route
            under this panel's own id — which is what makes the module reachable
            from a frame at an opaque origin (FR-021, D-008).
        export_name: The named export the ADR-048 manifest declared.
        api_version: The version the *wrapped previewer* declares, echoed at
            the handshake so the host's version gate judges the module rather
            than the wrapper around it (FR-004).
        features: The spec's free-form feature tags, handed to the module as the
            ``provider.features`` the retired host API promised it.

    Returns:
        The complete HTML document.
    """
    config = json.dumps(
        {
            "api_version": api_version,
            "entry_url": entry_url,
            "export_name": export_name,
            "features": list(features),
        },
        sort_keys=True,
    )
    return _COMPAT_DOCUMENT_TEMPLATE.replace(_COMPAT_CONFIG_PLACEHOLDER, config)


# ---------------------------------------------------------------------------
# Selecting what to wrap
# ---------------------------------------------------------------------------


@internal()
def module_entry_path(manifest: FrontendManifest) -> str:
    """Return the bundle-relative path of the module ``manifest`` names.

    An ADR-048 ``module_url`` is one of the two retained asset routes' paths —
    ``/api/previews/assets/<previewer_id>/<path>`` or
    ``/api/blocks/panels/<panel_id>/<path>`` — and the part after the id is the
    path under the manifest's ``asset_root``. When the id does not appear (a
    manifest written against a route this repository does not serve), the last
    segment is used, which is the only reading left that names a file.

    Raises:
        CompatShimError: When no file name can be read out of the URL at all.
    """
    path = urlsplit(manifest.module_url).path
    segments = [unquote(segment) for segment in path.split("/") if segment not in ("", ".")]
    if not segments:
        raise CompatShimError(
            f"previewer {manifest.previewer_id!r} declares a module_url with no file to serve: {manifest.module_url!r}"
        )
    if manifest.previewer_id in segments:
        index = segments.index(manifest.previewer_id)
        remainder = segments[index + 1 :]
        if remainder:
            return "/".join(remainder)
    return segments[-1]


@internal()
def shimmable_specs(specs: list[PanelSpec], discovered: set[str]) -> list[PanelSpec]:
    """Return the specs that need wrapping, in registration order.

    A spec qualifies when it carries an ADR-048 ``frontend_manifest`` and no
    panel *directory* has claimed its id. The second half is what makes
    migration take effect the moment a package ships one: a directory in any
    tier shadows the shim for that id (FR-019), so a package that has migrated
    stops being wrapped without anybody withdrawing anything.
    """
    return [spec for spec in specs if spec.frontend_manifest is not None and spec.previewer_id not in discovered]


@internal()
def is_compat_panel(panel: DiscoveredPanel | PanelManifest) -> bool:
    """Is this panel a wrapped ADR-048 previewer rather than a real directory?"""
    manifest = panel.manifest if isinstance(panel, DiscoveredPanel) else panel
    return COMPAT_SHIM_FEATURE in manifest.features


# ---------------------------------------------------------------------------
# Generating the panel directory
# ---------------------------------------------------------------------------


def compat_shim_root() -> Path:
    """Return the process's shim output root, creating it on first use.

    A temporary directory rather than a place in the user library, and the
    choice is deliberate: everything under it is *derived* from a package's
    bundle and is rewritten on every registry rebuild, so it must not look like
    something a person edits, must not survive an uninstall, and must not need a
    cache-invalidation story of its own.
    """
    global _shim_root
    if _shim_root is None or not _shim_root.is_dir():
        _shim_root = Path(tempfile.mkdtemp(prefix="scistudio-panel-compat-"))
        atexit.register(shutil.rmtree, _shim_root, True)
    return _shim_root


@dataclass(frozen=True)
class _CopiedBundle:
    files: int
    bytes_copied: int


def _copy_bundle(asset_root: Path, destination: Path, *, panel_id: str) -> _CopiedBundle:
    """Copy the allowlisted files under *asset_root* into *destination*.

    The whole bundle rather than only the entry module, because the retired host
    API's ``assetUrl`` promised a package that everything beside its module
    stays reachable, and a module that imports a sibling is ordinary. The
    allowlist is the merged route's own (D-008): a file the route would refuse
    to serve is not copied, so the shim's directory contains exactly what a
    panel directory may contain.
    """
    files = 0
    total = 0
    for source in sorted(asset_root.rglob("*")):
        if not source.is_file():
            continue
        if not is_allowed_asset_suffix(source.name):
            continue
        relative = source.relative_to(asset_root)
        if relative.parts[0] in (COMPAT_SHIM_ENTRY, COMPAT_SHIM_DECLARATION) and len(relative.parts) == 1:
            raise CompatShimError(
                f"previewer {panel_id!r} ships a file named {relative.parts[0]!r}, which the shim's own "
                f"generated panel directory needs; migrate the package rather than renaming it"
            )
        size = source.stat().st_size
        files += 1
        total += size
        if files > COMPAT_SHIM_MAX_BUNDLE_FILES or total > COMPAT_SHIM_MAX_BUNDLE_BYTES:
            raise CompatShimError(
                f"previewer {panel_id!r} ships a bundle larger than the shim wraps "
                f"({COMPAT_SHIM_MAX_BUNDLE_FILES} files / {COMPAT_SHIM_MAX_BUNDLE_BYTES} bytes)"
            )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return _CopiedBundle(files=files, bytes_copied=total)


@internal()
def build_compat_panel(spec: PanelSpec, *, root: Path | None = None) -> DiscoveredPanel:
    """Wrap one ADR-048-form previewer as a panel directory and return it.

    The generated directory holds the declaration, the adapter document, and a
    copy of the previewer's bundle. From here on it is a panel like any other:
    :func:`scistudio.panels.descriptor.panel_descriptor` builds its descriptor,
    the merged asset route serves its files, and the frame host mounts it
    without knowing it was ever anything else.

    Args:
        spec: A registered spec carrying an ADR-048 ``frontend_manifest``.
        root: Where to write. Defaults to :func:`compat_shim_root`.

    Returns:
        The :class:`~scistudio.panels.discovery.DiscoveredPanel` to install.

    Raises:
        CompatShimError: When the manifest is unusable, the bundle is out of
            bounds, or the directory cannot be written. Every one of them is a
            diagnostic the caller records, never an exception that costs the
            rest of the registry.
    """
    manifest = spec.frontend_manifest
    if manifest is None:
        raise CompatShimError(f"previewer {spec.previewer_id!r} declares no ADR-048 module to wrap")
    if not is_safe_panel_id(spec.previewer_id):
        raise CompatShimError(f"previewer id {spec.previewer_id!r} is not a usable panel id")

    validation = validate_manifest(manifest)
    if not validation.valid:
        raise CompatShimError(f"previewer {spec.previewer_id!r} cannot be wrapped: {'; '.join(validation.diagnostics)}")
    if not manifest.asset_root:
        raise CompatShimError(f"previewer {spec.previewer_id!r} declares a module but no asset_root")
    asset_root = Path(manifest.asset_root)
    if not asset_root.is_dir():
        raise CompatShimError(
            f"previewer {spec.previewer_id!r} declares an asset_root that is not a directory: {asset_root}"
        )

    entry = module_entry_path(manifest)
    if not (asset_root / entry).is_file():
        raise CompatShimError(f"previewer {spec.previewer_id!r} names a module the bundle does not contain: {entry!r}")

    shim_root = root if root is not None else compat_shim_root()
    directory = shim_root / spec.previewer_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _copy_bundle(asset_root, directory, panel_id=spec.previewer_id)
        # `./` because the document is served from this panel's own directory on
        # the merged asset route; the import therefore crosses the frame's opaque
        # origin onto the one route that answers a cross-origin read (FR-021).
        (directory / COMPAT_SHIM_ENTRY).write_text(
            compat_shim_document(
                entry_url=f"./{entry}",
                export_name=manifest.export_name or "default",
                api_version=manifest.api_version,
                features=spec.features,
            ),
            encoding="utf-8",
        )
    except CompatShimError:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise CompatShimError(f"previewer {spec.previewer_id!r} could not be wrapped: {exc}") from exc

    panel_manifest = PanelManifest(
        panel_id=spec.previewer_id,
        display_name=spec.previewer_id,
        target_types=spec.target_type_names,
        # FR-043, stated once and enforced twice: the declaration says
        # displaying, so the host's capability gate drops `emit` structurally,
        # and the generated document has no emission path to drop.
        capability=PanelCapability.DISPLAYING,
        entry=COMPAT_SHIM_ENTRY,
        # The previewer's own declared version, not the host's: a module built
        # against a major the host no longer accepts must be refused by the
        # version gate (FR-004) rather than laundered into acceptance by the
        # wrapper around it.
        api_version=manifest.api_version,
        features=(*spec.features, COMPAT_SHIM_FEATURE),
        priority=spec.priority,
        supports_collection=spec.supports_collection,
    )
    (directory / COMPAT_SHIM_DECLARATION).write_text(
        json.dumps(panel_manifest.to_declaration_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tier = spec.owner_kind if isinstance(spec.owner_kind, PanelTier) else PanelTier.PACKAGE
    return DiscoveredPanel(
        manifest=panel_manifest,
        tier=tier,
        directory=directory,
        root=shim_root,
        owner_name=spec.owner_name,
        # The spec's own provider still answers this panel's reads: FR-042 keeps
        # an unmigrated previewer *rendering*, and what it renders is what its
        # Python side already produced.
        provider=spec.backend_provider,
    )


@internal()
def install_compat_panels(
    registry: PanelRegistry,
    discovery: PanelDiscovery,
    *,
    root: Path | None = None,
) -> list[str]:
    """Wrap every unmigrated ADR-048 previewer and add it to *discovery*.

    Called once per registry build, after the on-disk scan has registered what
    it found, so that a directory always wins over a shim for the same id.

    Args:
        registry: The :class:`~scistudio.panels.registry.PanelRegistry` holding
            the specs, including those the retired ``get_previewers()`` factory
            supplied (FR-020, FR-045).
        discovery: The :class:`~scistudio.panels.discovery.PanelDiscovery` the
            four-tier scan produced. Wrapped previewers are added to its
            ``panels`` map, which is what the asset route and the descriptor
            read.
        root: Where to write. Defaults to :func:`compat_shim_root`.

    Returns:
        The ids that were wrapped, in registration order. Every refusal is
        recorded as a discovery diagnostic instead, so one unwrappable package
        does not cost the others and the panel it names still falls to the
        FR-014 failure path with the data visible.
    """
    wrapped: list[str] = []
    for spec in shimmable_specs(registry.all_specs(), set(discovery.panels)):
        try:
            panel = build_compat_panel(spec, root=root)
        except CompatShimError as exc:
            logger.warning("ADR-048 compatibility shim refused %s: %s", spec.previewer_id, exc.message)
            discovery.diagnostics.append(exc.message)
            continue
        discovery.panels[panel.panel_id] = panel
        wrapped.append(panel.panel_id)
    return wrapped
