"""Block package: {package_name}.

{description}

This module follows the SciEasy block package protocol (ADR-025).
The ``get_blocks()`` callable is the entry-point registered in
``pyproject.toml`` under ``[project.entry-points."scieasy.blocks"]``.
"""

from __future__ import annotations

from scieasy.blocks.base.package_info import PackageInfo

from {module_name}.blocks import ExampleBlock

_PACKAGE_INFO = PackageInfo(
    name="{display_name}",
    description="{description}",
    author="{author}",
    version="0.1.0",
)


def get_blocks() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and the list of block classes.

    The SciEasy block registry calls this function at startup to
    discover blocks provided by this package.
    """
    return (_PACKAGE_INFO, [ExampleBlock])
