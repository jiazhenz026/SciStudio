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

  **That confinement is checked, not assumed** (#2229). The reference arrives
  in a ``panel.json`` a project may have brought with it from anywhere, and it
  ends in ``exec_module``, so it is the same class of surface
  :mod:`scistudio.panels.editing` describes — the one this repository has been
  bitten on three times (#2038, #2037, #2039). Two checks, in this order:

  1. **The shape.** A provider names a dotted Python module path, so every
     component must be a Python identifier. A component that is empty, ``..``,
     absolute, a drive letter, or carrying a path separator is not a module
     name and is refused before any path is built. This is the check that
     matters, because ``Path.joinpath`` *resets on an absolute segment*: split
     on ``.``, ``"../escape"`` becomes ``["", "", "/escape"]`` and the join
     lands at the filesystem anchor rather than under the root.
  2. **The result.** The file the name resolves to must still be inside the
     resolved root, by the same ``relative_to`` comparison
     :func:`scistudio.panels.editing.confined_panel_directory` uses. Resolving
     first means a symlink pointing out of the tier is refused by the same
     comparison that refuses a traversal. A path that escapes is refused, not
     clamped, and the refusal names the panel.

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
    "is_importable_module_name",
    "resolve_declared_provider",
    "split_provider_reference",
]

#: The sentence every shape refusal carries, so the two call sites and the
#: tests defending them agree on one wording rather than three.
UNUSABLE_MODULE_NAME_REASON = (
    "is not a dotted Python module name; a component that is empty, '..', "
    "absolute, a drive letter, or carrying a path separator is refused before "
    "any path is built"
)


@internal()
def is_importable_module_name(module_name: str) -> bool:
    """Return whether *module_name* is a dotted sequence of Python identifiers.

    The one shape check, and the reason it is a *shape* check rather than a
    path check: ``Path.joinpath`` discards everything left of an absolute
    segment, so ``root.joinpath(*"../escape".split("."))`` is not
    ``root/../escape`` but the filesystem anchor. Asking whether each component
    is an identifier refuses every spelling of that — ``..`` (empty
    components), ``/escape`` and ``escape\\sub`` (separators), ``C:`` (a drive
    letter, which is also how the colon would be read) — without having to
    enumerate them.
    """
    if not isinstance(module_name, str) or not module_name:
        return False
    return all(part.isidentifier() for part in module_name.split("."))


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
    """Return the file *module_name* resolves to **under** *root*, else ``None``.

    Both importable shapes are covered: ``<name>.py`` and a
    ``<name>/__init__.py`` package (mirroring
    :func:`scistudio.core.dropins._importable_entries`).

    "Under" is enforced rather than assumed (#2229): a name that is not a
    dotted sequence of identifiers never reaches the join, and a file that
    resolves outside the resolved root is not returned. ``None`` therefore
    means "this tier holds no such module" for a well-shaped name, and "no"
    for everything else — :func:`resolve_declared_provider` refuses the
    ill-shaped name itself, before calling this, so a refusal is never mistaken
    for an ordinary miss.
    """
    if not is_importable_module_name(module_name):
        return None
    resolved_root = Path(root).resolve()
    candidate = resolved_root.joinpath(*module_name.split("."))
    init_file = candidate / "__init__.py"
    if candidate.is_dir() and init_file.is_file():
        return _confined(resolved_root, init_file)
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return _confined(resolved_root, py_file)
    return None


def _confined(resolved_root: Path, path: Path) -> Path | None:
    """Return *path* if it resolves inside *resolved_root*, else ``None``.

    The same comparison :func:`scistudio.panels.editing.confined_panel_directory`
    makes, for the same reason: resolving before comparing is what makes a
    symlink out of the tier refused by the check that refuses a traversal.
    """
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError:
        logger.warning("panel provider module %s resolves outside its tier root %s", path, resolved_root)
        return None
    return path


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

    # FR-047, #2229: the shape first, before a path is built or an import is
    # attempted. An ill-shaped module part is refused for being ill-shaped —
    # never allowed to fall through to `importlib.import_module`, whose
    # "No module named" would read as a typo rather than as a refusal.
    if not is_importable_module_name(module_name):
        return ProviderResolution(
            None,
            f"panel {panel_id!r} declares provider {dotted!r}, whose module part "
            f"{module_name!r} {UNUSABLE_MODULE_NAME_REASON}",
        )

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
