"""Cross-platform discovery of the agent provider's CLI binary.

The discovery routine implemented here (in T-ECA-102) searches the
eight fallback paths from ADR-033 §3 D1.2, in order:

1. ``$HOME/.local/bin/<name>`` (Anthropic installer default).
2. ``$NVM_BIN/<name>``.
3. ``$PNPM_HOME/<name>``.
4. ``shutil.which("<name>")``.
5. Login-shell resolution: ``bash -lc "command -v <name>"`` (Unix).
6. Windows: ``HKCU\\Environment\\Path`` +
   ``HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\Environment\\Path``.
7. NVM directories: ``$HOME/.nvm/versions/node/*/bin/<name>``.
8. npm global: ``$(npm root -g)/../bin/<name>`` (only if ``npm`` is on
   PATH).
9. Standard fallbacks: ``/usr/local/bin``, ``/usr/bin``.

First hit wins. ``None`` if no fallback resolves.

Phase 1 ships only the stub; the implementation lands in T-ECA-102.
"""

from __future__ import annotations

from pathlib import Path


def find_binary(name: str) -> Path | None:
    """Locate the named binary using the ADR-033 §3 D1.2 fallback order.

    Parameters
    ----------
    name
        Bare binary name (e.g. ``"claude"``, ``"codex"``).

    Returns
    -------
    pathlib.Path or None
        Absolute path to the first matching binary, or ``None`` if no
        fallback resolves to an executable.

    Raises
    ------
    NotImplementedError
        Always, in Phase 1. Implementation lands in T-ECA-102.
    """
    raise NotImplementedError("find_binary is implemented in T-ECA-102")
