#!/usr/bin/env python3
"""Block AI writes outside the assigned ADR-042 worktree and gate scope."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    try:
        return Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def main() -> int:
    repo_root = _repo_root()
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        sys.path.insert(0, str(src_dir))
    from scistudio.qa.governance.worktree_write_guard import main as guard_main

    return guard_main(["--hook-json"])


if __name__ == "__main__":
    raise SystemExit(main())
