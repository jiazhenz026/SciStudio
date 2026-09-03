"""Resolving a panel's optional Python provider (FR-047).

A panel needs no Python by default: the shared bounded data-access layer windows
every core type, so a declaration that names no provider has its windowed reads
served from there (A-010). A package type that layer cannot window ships a
provider, named in the declaration as a ``module:attribute`` reference.

Two things follow from FR-047 and both live here rather than at the two call
sites that used to hold a copy each:

* **The reference is resolved from the tier the panel was discovered in.** A
  user-library panel never resolves its provider out of the open project's
  directory, and vice versa. A module that lives under the owning tier root is
  imported *by file path* under an mtime-stamped synthetic name — the same
  hygiene :meth:`scistudio.blocks.registry.BlockRegistry.instantiate` uses for
  drop-in blocks — so nothing is cached under a bare stem where another tier's
  same-named module could win the import or be poisoned by it, and an edit is
  picked up on the next load.

* **A provider that fails to import is a discovery diagnostic naming the
  panel**, not a load failure at mount. That is why
  :func:`resolve_declared_provider` returns the failure rather than logging it
  and answering ``None``: discovery needs the sentence to put on the panel's
  diagnostic, and a person whose provider has a typo has to be told which panel
  is broken while they are looking at the list of panels, not when they next
  open a file.

:mod:`scistudio.panels.session` resolves the same references at render time for
the ADR-048 spec form and delegates to the same two functions, so the drop-in
import hygiene has one definition rather than one per caller.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scistudio.stability import internal

logger = logging.getLogger(__name__)

__all__ = [
    "ProviderResolution",
    "dropin_module_path",
    "import_callable",
    "resolve_declared_provider",
    "split_provider_reference",
]


@internal()
class ProviderResolution:
    """The outcome of resolving one provider reference.

    Either ``provider`` is a callable and ``error`` is ``None``, or ``provider``
    is ``None`` and ``error`` is the sentence discovery records as a diagnostic.
    """

    __slots__ = ("error", "provider")

    def __init__(self, provider: Callable[..., Any] | None, error: str | None) -> None:
        self.provider = provider
        self.error = error

    def __bool__(self) -> bool:
        return self.provider is not None


@internal()
def split_provider_reference(dotted: str) -> tuple[str, str]:
    """Split a ``module:attribute`` (or ``module.attribute``) reference.

    Raises:
        ValueError: When the reference names no attribute at all.
    """
    if ":" in dotted:
        module_name, attribute = dotted.split(":", 1)
    else:
        module_name, attribute = dotted.rsplit(".", 1)
    module_name = module_name.strip()
    attribute = attribute.strip()
    if not module_name or not attribute:
        raise ValueError(f"{dotted!r} is not a 'module:attribute' reference")
    return module_name, attribute


@internal()
def import_callable(dotted: str) -> Callable[..., Any] | None:
    """Resolve a ``module:callable`` provider by ordinary import, or ``None``."""
    try:
        module_name, attribute = split_provider_reference(dotted)
        module = importlib.import_module(module_name)
        provider = getattr(module, attribute)
    except Exception:
        logger.warning("Failed to import panel provider %r", dotted, exc_info=True)
        return None
    return provider if callable(provider) else None


@internal()
def dropin_module_path(root: Path, module_name: str) -> Path | None:
    """Return the file *module_name* resolves to under *root*, else ``None``.

    Both importable shapes are covered: ``<name>.py`` and a
    ``<name>/__init__.py`` package (mirroring
    :func:`scistudio.core.dropins._importable_entries`).
    """
    candidate = root.joinpath(*module_name.split("."))
    init_file = candidate / "__init__.py"
    if candidate.is_dir() and init_file.is_file():
        return init_file
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return py_file
    return None


@internal()
def resolve_declared_provider(
    dotted: str,
    *,
    panel_id: str,
    owning_root: Path | None = None,
) -> ProviderResolution:
    """Resolve a declaration's provider reference, reporting why it failed.

    Args:
        dotted: The ``module:attribute`` reference the declaration names.
        panel_id: The panel the reference belongs to; every failure names it.
        owning_root: The tier root the panel was discovered under, for the
            user and project tiers. ``None`` for the core and package tiers,
            whose providers are ordinary installed imports.

    Returns:
        A :class:`ProviderResolution` carrying either the callable or the
        diagnostic sentence (FR-047).
    """
    from scistudio.core.dropins import evict_cached_bytecode

    try:
        module_name, attribute = split_provider_reference(dotted)
    except ValueError as exc:
        return ProviderResolution(None, f"panel {panel_id!r} declares provider {dotted!r}, which {exc}")

    path = dropin_module_path(owning_root, module_name) if owning_root is not None else None

    if path is None:
        try:
            module: Any = importlib.import_module(module_name)
        except Exception as exc:
            logger.debug("panel %s provider import failed", panel_id, exc_info=True)
            return ProviderResolution(
                None,
                f"panel {panel_id!r} declares provider {dotted!r}, whose module "
                f"could not be imported ({type(exc).__name__}: {exc})",
            )
    else:
        try:
            # A drop-in edited within one second of its last load, to the same
            # length, would otherwise re-execute the previous bytecode.
            evict_cached_bytecode(path)
            synthetic = f"_scistudio_panel_provider_{path.stem}_{path.stat().st_mtime_ns}"
            file_spec = importlib.util.spec_from_file_location(synthetic, path)
            if file_spec is None or file_spec.loader is None:
                return ProviderResolution(
                    None,
                    f"panel {panel_id!r} declares provider {dotted!r}, whose module at {path} is not loadable",
                )
            module = importlib.util.module_from_spec(file_spec)
            file_spec.loader.exec_module(module)
        except Exception as exc:
            logger.debug("panel %s provider exec failed", panel_id, exc_info=True)
            return ProviderResolution(
                None,
                f"panel {panel_id!r} declares provider {dotted!r}, whose module at {path} "
                f"raised on import ({type(exc).__name__}: {exc})",
            )

    provider = getattr(module, attribute, None)
    if provider is None:
        return ProviderResolution(
            None,
            f"panel {panel_id!r} declares provider {dotted!r}, but {module_name!r} has no {attribute!r}",
        )
    if not callable(provider):
        return ProviderResolution(
            None,
            f"panel {panel_id!r} declares provider {dotted!r}, which is a "
            f"{type(provider).__name__} rather than a callable",
        )
    return ProviderResolution(provider, None)
