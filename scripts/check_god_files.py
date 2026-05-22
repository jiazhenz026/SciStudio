"""Advisory check: flag Python source files exceeding the god-file threshold.

Mirror of the frontend `max-lines` ESLint rule (#1422) for the Python side.
Per umbrella issue #1427:

- Threshold: 750 LOC. Frontend `#1422` uses 500; the Python side starts at 750
  to avoid flagging basic type-definition files whose size is inherent to
  their role (per owner directive 2026-05-22). The threshold may be lowered
  in a later phase once the largest files are decomposed.
- Scope: `src/scistudio/**/*.py`, excluding `tests/**` and `__pycache__/**`.
- Mode: advisory (exit 0 even on violations). Use `--enforce` to exit non-zero
  on *new* violations (files not in `GOD_FILE_SIZE_WAIVERS`).
- Waivers shrink as Phase 1 sub-PRs land. Promote to hard-fail (`--enforce`
  in CI required job) after Phase 1 completes per checklist task in
  `docs/planning/backend-god-file-refactor-checklist.md`.

Usage:

    python scripts/check_god_files.py            # advisory, exit 0
    python scripts/check_god_files.py --enforce  # exit 1 on new violations
    python scripts/check_god_files.py --json     # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_LINES = 750

SCAN_ROOT = Path("src/scistudio")

EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({"__pycache__", "tests"})

GOD_FILE_SIZE_WAIVERS: frozenset[str] = frozenset(
    {
        # ``src/scistudio/api/runtime.py`` removed 2026-05-22 (#1430) — the
        # 1839-LOC god-file was split into the ``runtime/`` sub-package.
        "src/scistudio/engine/scheduler.py",
        "src/scistudio/blocks/registry.py",
        # ``src/scistudio/qa/governance/gate_record.py`` was decomposed into
        # the ``gate_record/`` sub-package in PR for #1433 (umbrella #1427);
        # waiver removed because every new sub-module is below the 750 LOC
        # threshold.
        "src/scistudio/blocks/io/savers/save_data.py",
        "src/scistudio/blocks/io/loaders/load_data.py",
        # tools_workflow.py and tools_inspection.py removed from waivers in #1431 —
        # decomposed into src/scistudio/ai/agent/mcp/{tools_workflow,tools_inspection}/
        # sub-packages whose largest sub-module is < 750 LOC.
        "src/scistudio/core/versioning/git_engine.py",
        "src/scistudio/api/routes/ai_pty.py",
    }
)


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIR_NAMES for part in path.parts)


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def _scan(root: Path) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for candidate in root.rglob("*.py"):
        if _is_excluded(candidate):
            continue
        rel = candidate.relative_to(Path.cwd()).as_posix() if candidate.is_absolute() else candidate.as_posix()
        loc = _count_lines(candidate)
        if loc >= MAX_LINES:
            results.append((rel, loc))
    results.sort(key=lambda row: row[1], reverse=True)
    return results


def _format_text(rows: list[tuple[str, int]]) -> tuple[str, int]:
    new_violations: list[tuple[str, int]] = []
    waived: list[tuple[str, int]] = []
    for path, loc in rows:
        if path in GOD_FILE_SIZE_WAIVERS:
            waived.append((path, loc))
        else:
            new_violations.append((path, loc))

    lines: list[str] = []
    lines.append(f"God-file scan: threshold = {MAX_LINES} LOC, scope = {SCAN_ROOT}")
    lines.append("")
    if new_violations:
        lines.append(f"NEW violations (not in GOD_FILE_SIZE_WAIVERS): {len(new_violations)}")
        for path, loc in new_violations:
            lines.append(f"  [NEW] {path} ({loc} LOC)")
        lines.append("")
    if waived:
        lines.append(f"Tracked waivers (umbrella #1427): {len(waived)}")
        for path, loc in waived:
            lines.append(f"  [waived] {path} ({loc} LOC)")
        lines.append("")
    if not rows:
        lines.append("OK: no files at or above threshold.")
    elif not new_violations:
        lines.append("OK: all files at or above threshold are tracked waivers.")
    return "\n".join(lines), len(new_violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flag Python files exceeding the god-file LOC threshold.")
    parser.add_argument("--enforce", action="store_true", help="Exit non-zero on NEW (non-waived) violations.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    if not SCAN_ROOT.exists():
        sys.stderr.write(f"scan root not found: {SCAN_ROOT}\n")
        return 2

    rows = _scan(SCAN_ROOT)
    new_count = sum(1 for path, _ in rows if path not in GOD_FILE_SIZE_WAIVERS)

    if args.json:
        payload = {
            "threshold": MAX_LINES,
            "scan_root": str(SCAN_ROOT),
            "violations": [{"path": path, "loc": loc, "waived": path in GOD_FILE_SIZE_WAIVERS} for path, loc in rows],
            "new_violation_count": new_count,
        }
        print(json.dumps(payload, indent=2))
    else:
        text, _ = _format_text(rows)
        print(text)

    if args.enforce and new_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
