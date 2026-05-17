"""spec_audit — orchestrator. Chains the 3 extractors + 1 diff.

Usage:
    python scripts/spec_audit.py              # full drift check (CI mode)
    python scripts/spec_audit.py --baseline   # baseline mode (no spec yet)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"[spec_audit] $ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=cwd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full spec_audit pipeline")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--baseline", action="store_true", help="Skip spec parse + diff; only emit code inventory")
    args = ap.parse_args()

    repo_root = args.repo_root
    build_dir = repo_root / "build" / "spec-audit"
    build_dir.mkdir(parents=True, exist_ok=True)

    rc = run_step(
        [
            sys.executable,
            "-m",
            "scripts.spec_audit.extract_code",
            "--repo-root",
            str(repo_root),
            "--out",
            str(build_dir / "code.json"),
        ],
        cwd=repo_root,
    )
    if rc != 0:
        print(f"[spec_audit] extract_code failed (rc={rc})", file=sys.stderr)
        return rc

    if args.baseline:
        print("[spec_audit] baseline mode — skipping spec parse + diff")
        return 0

    rc = run_step(
        [
            sys.executable,
            "-m",
            "scripts.spec_audit.extract_spec",
            "--spec",
            str(repo_root / "docs" / "specs" / "INTERFACE_SPEC.md"),
            "--out",
            str(build_dir / "spec.json"),
        ],
        cwd=repo_root,
    )
    if rc != 0:
        print(f"[spec_audit] extract_spec failed (rc={rc})", file=sys.stderr)
        return rc

    rc = run_step(
        [
            sys.executable,
            "-m",
            "scripts.spec_audit.extract_docs",
            "--repo-root",
            str(repo_root),
            "--code",
            str(build_dir / "code.json"),
            "--out",
            str(build_dir / "docs.json"),
        ],
        cwd=repo_root,
    )
    if rc != 0:
        print(f"[spec_audit] extract_docs failed (rc={rc})", file=sys.stderr)
        return rc

    rc = run_step(
        [
            sys.executable,
            "-m",
            "scripts.spec_audit.diff",
            "--code",
            str(build_dir / "code.json"),
            "--spec",
            str(build_dir / "spec.json"),
            "--docs",
            str(build_dir / "docs.json"),
            "--out",
            str(build_dir / "diff-report.md"),
            "--mode",
            "drift",
        ],
        cwd=repo_root,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
