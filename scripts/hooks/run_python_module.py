#!/usr/bin/env python3
"""Run a repository src-layout Python module from local hooks."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: run_python_module.py <module> [args...]", file=sys.stderr)
        return 2

    module = args[0]
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "src"))
    sys.argv = [module, *args[1:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
