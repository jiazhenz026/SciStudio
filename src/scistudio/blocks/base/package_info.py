"""PackageInfo — metadata for external block packages.

Kept in a separate file to avoid circular imports when external packages
import it for registration.  See ADR-025.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageInfo:
    """Metadata about a block package.

    External block packages return a ``PackageInfo`` instance alongside
    their block list in the ``scistudio.blocks`` entry-point callable.
    The registry uses this to populate the two-level palette hierarchy
    (package -> category -> block).
    """

    name: str
    description: str = ""
    author: str = ""
    version: str = "0.1.0"
