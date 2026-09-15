"""PreviewSessionManager — the deprecated Python previewer renderer."""
# Maintainer context (kept outside generated API documentation):
# The legacy (deprecated, removed in 0.3.6) renderer for
# :class:`PreviewerSpec` providers. Routing is not decided here: the panel
# service routes every preview through ``scistudio.panels.router`` over panels
# and legacy previewers together, and hands this manager the legacy spec that
# won. A manager built without a resolver (a standalone registry in a test or
# the process-global default service) routes over its own registry with the
# same ladder. Session storage, guards, tiles, plot export and child routing
# come from :class:`scistudio.panels.sessions.SessionStore`.
#
# Provider calls are wrapped defensively: a typed error becomes an error
# envelope; an unexpected provider exception becomes a
# :class:`PreviewErrorCode.PROVIDER_EXCEPTION` envelope (FR-028/FR-029).
# Development references: #2465, ADR-048, ADR-054, FR-007, FR-028, FR-029.

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar, cast

from scistudio.panels.sessions import (
    ChildContextResolver,
    SessionStore,
    error_envelope,
    record_metadata_from_query,
    routing_error_envelope,
    storage_ref_from_query,
)
from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    OwnerKind,
    PreviewEnvelope,
    PreviewError,
    PreviewErrorCode,
    PreviewerSpec,
    PreviewLimits,
    PreviewProvider,
    PreviewRequest,
    PreviewResourceProvider,
    PreviewSession,
    PreviewTarget,
    ProviderError,
    UnknownPreviewerError,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.stability import internal

logger = logging.getLogger(__name__)

_DEFAULT_MAX_SESSIONS = 512

ProviderT = TypeVar("ProviderT", bound=Callable[..., Any])
#: ``(target, query) -> spec``: the router the owning service routes with.
SpecResolver = Callable[[PreviewTarget, dict[str, Any]], PreviewerSpec]


@contextmanager
def _activated_package_import_roots(owner_kind: OwnerKind) -> Iterator[None]:
    """Activate installed package import roots around a package previewer call.

    A package previewer module is importable at render time only because
    discovery cached it under a scoped ``prepended_sys_paths``; a lazy
    third-party import inside the provider needs the plugin ``src`` and
    ``site-packages`` again. Package tier only, best effort.
    """
    # Development references: #2112.
    if owner_kind is not OwnerKind.PACKAGE:
        yield
        return
    try:
        from scistudio.desktop.paths import installed_package_import_roots, prepended_sys_paths

        roots = list(installed_package_import_roots())
    except Exception:  # pragma: no cover - defensive; never fail a render
        yield
        return
    if not roots:
        yield
        return
    with prepended_sys_paths(roots):
        yield


@internal()
class PreviewSessionManager(SessionStore):
    """Legacy previewer sessions: provider invocation over a :class:`PreviewerRegistry`."""

    def __init__(
        self,
        registry: PreviewerRegistry,
        *,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        data_access_factory: Callable[[PreviewLimits], PreviewDataAccess] | None = None,
        child_context_resolver: ChildContextResolver | None = None,
        project_dir: Path | None = None,
        resolver: SpecResolver | None = None,
    ) -> None:
        super().__init__(
            max_sessions=max_sessions,
            data_access_factory=data_access_factory,
            child_context_resolver=child_context_resolver,
            child_session=self.create_session,
        )
        self._registry = registry
        self._resolver = resolver
        from scistudio.core.dropins import previewer_import_roots, previewer_scan_dirs

        self._dropin_import_roots = previewer_import_roots(project_dir)
        scan_dirs = previewer_scan_dirs(project_dir)
        # Project-first, user last (FR-058/FR-060); a tutorial project swaps the
        # user tier for its scoped library, so the owning root of a drop-in spec
        # is read off this tuple, never recomputed.
        self._project_previewers_root = scan_dirs[0] if project_dir is not None else None
        self._user_previewers_root = scan_dirs[-1]

    @property
    def registry(self) -> PreviewerRegistry:
        return self._registry

    def set_resolver(self, resolver: SpecResolver | None) -> None:
        """Route through *resolver* (the owning service's ladder) instead of this registry."""
        self._resolver = resolver

    def _select_spec(self, target: PreviewTarget, query: dict[str, Any]) -> PreviewerSpec:
        if self._resolver is not None:
            return self._resolver(target, query)
        from scistudio.panels.router import PanelRouter

        return PanelRouter.over_registry(self._registry).select(target, query)

    # -- session lifecycle --------------------------------------------------

    def create_session(
        self,
        target: PreviewTarget,
        query: dict[str, Any] | None = None,
        *,
        spec: PreviewerSpec | None = None,
        guard: Callable[[], None] | None = None,
        authority: Any = None,
    ) -> PreviewEnvelope:
        """Create a session for *spec* (routed first when omitted) and render it.

        A routing failure returns an error envelope and creates no session.
        """
        query = dict(query or {})
        if guard is not None:
            guard()
        if spec is None:
            try:
                spec = self._select_spec(target, query)
            except PreviewError as exc:
                return routing_error_envelope(target, exc)
        session = self._store(spec, target, query, guard=guard, authority=authority)
        return self._render(spec, session.target, session.query, session.limits, session.session_id)

    def read_session(self, session_id: str) -> PreviewEnvelope:
        """Re-render the current envelope for *session_id* (404 code when unknown)."""
        session = self._get_session(session_id)
        spec = self._require_spec(session.previewer_id)
        return self._render(spec, session.target, session.query, session.limits, session.session_id)

    def patch_session(self, session_id: str, query_patch: dict[str, Any]) -> PreviewEnvelope:
        """Merge *query_patch* into the session query state and re-render."""
        session = self._merge_query(session_id, query_patch)
        spec = self._require_spec(session.previewer_id)
        return self._render(spec, session.target, dict(session.query), session.limits, session_id)

    def render_target(self, target: PreviewTarget, query: dict[str, Any] | None = None) -> PreviewEnvelope:
        """Render a one-shot envelope without creating a session."""
        query = dict(query or {})
        try:
            spec = self._select_spec(target, query)
        except PreviewError as exc:
            return routing_error_envelope(target, exc)
        return self._render(spec, target, query, PreviewLimits(), session_id=None)

    # -- internals ----------------------------------------------------------

    def _renderer_resource(
        self,
        session: PreviewSession,
        resource_id: str,
        merged: dict[str, Any],
        access: PreviewDataAccess,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        spec = self._require_spec(session.previewer_id)
        resource_provider = self._resolve_resource_provider(spec)
        if resource_provider is None:
            return super()._renderer_resource(session, resource_id, merged, access, params)
        from scistudio.panels.sessions import public_resource_params

        request = PreviewRequest(
            target=session.target,
            spec=spec,
            query=merged,
            data_access=access,
            limits=session.limits,
            session_id=session.session_id,
            storage=storage_ref_from_query(merged, session.target.ref),
            record_metadata=record_metadata_from_query(merged),
        )
        try:
            with _activated_package_import_roots(spec.owner_kind):
                return resource_provider(request, resource_id, public_resource_params(params))
        except ProviderError:
            raise
        except Exception as exc:
            logger.debug("preview resource provider failed for %s", resource_id, exc_info=True)
            raise ProviderError(
                f"resource provider for {session.previewer_id!r} failed: {exc}",
                detail={"resource_id": resource_id, "previewer_id": session.previewer_id},
            ) from exc

    def _render(
        self,
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any],
        limits: PreviewLimits,
        session_id: str | None,
    ) -> PreviewEnvelope:
        provider = self._resolve_provider(spec)
        if provider is None:
            return error_envelope(
                target,
                PreviewErrorCode.MISSING_BUNDLE,
                f"previewer {spec.previewer_id!r} has no backend provider",
                previewer_id=spec.previewer_id,
            ).with_session(session_id)
        request = PreviewRequest(
            target=target,
            spec=spec,
            query=query,
            data_access=self._data_access_factory(limits),
            limits=limits,
            session_id=session_id,
            storage=storage_ref_from_query(query, target.ref),
            record_metadata=record_metadata_from_query(query),
        )
        try:
            with _activated_package_import_roots(spec.owner_kind):
                envelope = provider(request)
        except PreviewError as exc:
            envelope = error_envelope(target, exc.code, exc.message, previewer_id=spec.previewer_id, detail=exc.detail)
        except Exception as exc:
            logger.warning("preview provider %s raised", spec.previewer_id, exc_info=True)
            envelope = error_envelope(
                target,
                PreviewErrorCode.PROVIDER_EXCEPTION,
                f"provider {spec.previewer_id!r} raised: {exc}",
                previewer_id=spec.previewer_id,
            )
        # A provider-set frontend manifest wins; otherwise the spec's (#1579).
        if envelope.frontend_manifest is None and spec.frontend_manifest is not None:
            envelope = replace(envelope, frontend_manifest=spec.frontend_manifest)
        return envelope.with_session(session_id)

    def _resolve_provider(self, spec: PreviewerSpec) -> PreviewProvider | None:
        return self._provider_from_decl_scoped(spec, spec.backend_provider)

    def _resolve_resource_provider(self, spec: PreviewerSpec) -> PreviewResourceProvider | None:
        return self._provider_from_decl_scoped(spec, spec.resource_provider)

    def _owning_previewer_root(self, owner_kind: OwnerKind) -> Path | None:
        """Return the drop-in directory *owner_kind* specs are scanned from."""
        if owner_kind is OwnerKind.PROJECT:
            return self._project_previewers_root
        if owner_kind is OwnerKind.USER:
            return self._user_previewers_root
        return None

    def _provider_from_decl_scoped(self, spec: PreviewerSpec, provider: ProviderT | str | None) -> ProviderT | None:
        """Resolve a provider declaration, scoped to the tier that owns *spec*.

        A drop-in previewer's ``module:callable`` provider is imported by file
        path from its owning tier root under a synthetic name, so a same-named
        module in another tier can neither win the import nor be poisoned by it.
        Package and core string providers are ordinary installed imports.
        """
        # Development references: #2017, #2072, FR-016.
        if not isinstance(provider, str):
            return _provider_from_decl(provider)
        owning_root = self._owning_previewer_root(spec.owner_kind)
        if owning_root is None:
            return _provider_from_decl(provider)
        from scistudio.core.dropins import (
            PREVIEWERS_DIR_NAME,
            guard_dropin_roots,
            transient_dropin_modules,
        )
        from scistudio.desktop.paths import prepended_sys_paths, user_python_import_roots

        guard_dropin_roots(self._dropin_import_roots, dir_name=PREVIEWERS_DIR_NAME)
        roots = (owning_root, *user_python_import_roots())
        with prepended_sys_paths(roots), transient_dropin_modules(roots):
            return cast(ProviderT | None, _dropin_provider_from_decl(provider, owning_root))

    def _require_spec(self, previewer_id: str) -> PreviewerSpec:
        spec = self._registry.get(previewer_id)
        if spec is None:
            raise UnknownPreviewerError(
                f"Unknown previewer: {previewer_id}",
                detail={"previewer_id": previewer_id},
            )
        return spec


def _provider_from_decl(provider: ProviderT | str | None) -> ProviderT | None:
    if provider is None:
        return None
    if callable(provider):
        return provider
    if isinstance(provider, str):
        return cast(ProviderT | None, _import_callable(provider))
    return None


def _import_callable(dotted: str) -> Callable[..., Any] | None:
    """Resolve a ``module:callable`` (or ``module.callable``) provider import path."""
    import importlib

    try:
        if ":" in dotted:
            mod_name, attr = dotted.split(":", 1)
        else:
            mod_name, attr = dotted.rsplit(".", 1)
        module = importlib.import_module(mod_name)
        provider = getattr(module, attr)
    except Exception:
        logger.warning("Failed to import previewer provider %r", dotted, exc_info=True)
        return None
    return provider if callable(provider) else None


def _dropin_module_path(root: Path, mod_name: str) -> Path | None:
    """Return the file *mod_name* resolves to under *root*, else ``None``.

    Both importable shapes are covered: ``<name>.py`` and a
    ``<name>/__init__.py`` package (mirroring
    :func:`scistudio.core.dropins._importable_entries`).
    """
    candidate = root.joinpath(*mod_name.split("."))
    init_file = candidate / "__init__.py"
    if candidate.is_dir() and init_file.is_file():
        return init_file
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return py_file
    return None


def _dropin_provider_from_decl(dotted: str, owning_root: Path) -> Callable[..., Any] | None:
    """Resolve a drop-in spec's ``module:callable`` provider against its own tier.

    A provider module that lives under *owning_root* is imported **by file
    path** under an mtime-stamped synthetic name — the same hygiene
    :meth:`scistudio.blocks.registry.BlockRegistry.instantiate` uses for
    drop-in blocks — so it never claims a bare-stem ``sys.modules`` entry that
    another tier's same-named module could collide with or be poisoned by, and
    edits are picked up on the next render. A provider that does not live
    under the tier root (e.g. one in the shared user dependency site) falls
    back to a plain import, which the caller runs inside the scoped roots.
    """
    import importlib.util

    from scistudio.core.dropins import evict_cached_bytecode

    try:
        if ":" in dotted:
            mod_name, attr = dotted.split(":", 1)
        else:
            mod_name, attr = dotted.rsplit(".", 1)
    except ValueError:
        logger.warning("Failed to import previewer provider %r", dotted, exc_info=True)
        return None
    path = _dropin_module_path(owning_root, mod_name)
    if path is None:
        return _import_callable(dotted)
    try:
        # FR-062: the by-path load must not re-execute stale bytecode for a
        # provider edited within one second of its last load.
        evict_cached_bytecode(path)
        synth_name = f"_scistudio_previewer_provider_{path.stem}_{path.stat().st_mtime_ns}"
        file_spec = importlib.util.spec_from_file_location(synth_name, path)
        if file_spec is None or file_spec.loader is None:
            return None
        module = importlib.util.module_from_spec(file_spec)
        file_spec.loader.exec_module(module)
        provider = getattr(module, attr)
    except Exception:
        logger.warning("Failed to import previewer provider %r", dotted, exc_info=True)
        return None
    return provider if callable(provider) else None


__all__ = ["PreviewSessionManager"]
