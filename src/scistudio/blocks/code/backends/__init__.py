"""Discovery of the built-in Code Block interpreter backend modules.

Each backend lives in its own module in this package and exposes a
``register()`` function. The runtime imports these modules and calls that hook,
so a new language backend can be added by dropping in a module without changing
the Code Block itself.
"""

from __future__ import annotations

import importlib
import pkgutil

_LOADED_MODULES: set[str] = set()


def load_codeblock_backend_modules() -> tuple[str, ...]:
    """Import backend modules and invoke their registration hooks."""

    loaded: list[str] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda info: info.name):  # type: ignore[name-defined]
        if module_info.name.startswith("_"):
            continue
        module_name = f"{__name__}.{module_info.name}"
        if module_name in _LOADED_MODULES:
            continue
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if register is not None:
            if not callable(register):
                raise TypeError(f"{module_name}.register must be callable")
            register()
        _LOADED_MODULES.add(module_name)
        loaded.append(module_name)
    return tuple(loaded)
