"""Creating link fixtures on Windows without a symlink privilege (#2075).

Several security tests need a link that points outside a base directory, so
they can assert the product refuses to follow it. Creating a *symlink* on
Windows needs a privilege developer machines and CI agents usually lack, which
would leave those tests skipped on the platform this repository is developed
on — exactly where the escape is most likely to be introduced.

A **directory junction** needs no privilege, and `os.path.realpath` follows it
identically. Since the product's escape check compares real paths
(`scistudio.tutorials.actions` resolves both sides with `os.path.realpath`),
a junction is a faithful stand-in: the assertion under test is unchanged.

Skipping remains the last resort, for the case where neither a symlink nor a
junction can be created.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

__all__ = ["link_to_directory"]


def link_to_directory(link: Path, target: Path) -> None:
    """Point *link* at directory *target*, or skip if the OS refuses both forms.

    Tries a real symlink first, then a Windows directory junction, then skips.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("symlink creation is not permitted in this environment")

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip("neither a symlink nor a directory junction can be created here")
