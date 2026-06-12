"""Detect untracked deferral / "lazy" language in source comments and strings.

AGENTS.md §3.6 requires every deferral to cite a tracking reference
(``TODO(#NNN)`` / issue / ADR / follow-up). Bare ``TODO``s and weasel
phrases like ``for now`` / ``placeholder`` / ``v1`` / ``temporary`` that
defer work *without* a reference are not trackable and must be caught.

This mirrors ``scripts/semantic_dup_scan.py``: a baseline-ratchet whole-repo
gate plus a diff-scoped gate, both wired into CI and the gate-record check.

A hit is **tracked** (allowed) only when its line carries a tracking
reference (``#1602``, ``ADR-042``, ``Follow-up``, ``T-006`` ...). There is
deliberately **no per-line escape marker**: an opt-out comment would become a
universal bypass that every deferral routes through, defeating the gate. The
only ways past it are a real tracking reference or removing the deferral.

Known *legitimate* technical collocations (``tempfile``, ``placeholder=``,
``/api/v1``) are suppressed centrally via :data:`EXCLUSIONS` — a reviewed,
repo-wide list, not an author-controlled bypass.

Modes
-----
- Default: scan and emit a markdown report of untracked hits.
- ``--write-baseline PATH``: record current whole-repo untracked counts as
  the ratchet ceiling.
- ``--check PATH``: whole-repo scan; exit 1 if untracked counts exceed the
  baseline ratchet (debt may shrink, never grow).
- ``--diff BASE_REF``: scan only lines added in ``git diff BASE_REF...HEAD``;
  exit 1 on any new untracked deferral; report new tracked ``TODO(#NNN)``
  count (the "how many new TODOs does this PR add" signal).

Usage examples
--------------
Local report:
    python scripts/deferral_scan.py
Initial baseline:
    python scripts/deferral_scan.py \\
        --write-baseline docs/audit/baselines/deferral-baseline.json
CI whole-repo ratchet:
    python scripts/deferral_scan.py \\
        --check docs/audit/baselines/deferral-baseline.json
CI diff gate (PR):
    python scripts/deferral_scan.py --diff origin/main
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_ROOT = "src/scistudio"

# Deferral / laziness markers. ``\b`` word boundaries mean identifiers with
# underscores (``placeholder_text``, ``later_runs``) do NOT match — only the
# bare word in prose/comments does.
DEFERRAL_PATTERNS: list[tuple[str, str]] = [
    ("todo", r"\bTODO\b"),
    ("fixme", r"\bFIXME\b"),
    ("xxx", r"\bXXX\b"),
    ("hack", r"\bhack(?:s|y|ed)?\b"),
    ("kludge", r"\bkludg\w*"),
    ("for_now", r"\bfor now\b"),
    ("for_the_moment", r"\bfor the moment\b"),
    ("for_simplicity", r"\bfor simplicity\b"),
    ("later", r"\blater\b"),
    ("eventually", r"\beventually\b"),
    ("in_the_future", r"\bin the future\b|\bfuture work\b|\bdown the line\b"),
    ("mvp", r"\bMVP\b"),
    ("v1", r"\bv1\b"),
    ("placeholder", r"\bplaceholder\b"),
    ("stopgap", r"\bstop-?gap\b"),
    ("temporary", r"\btemporar(?:y|ily)\b"),
    ("not_implemented", r"\b(?:not implemented|unimplemented)\b"),
    ("tentative", r"\bshould probably\b|\bmight want to\b|\bwe (?:could|might)\b"),
    ("revisit", r"\b(?:revisit|come back to)\b"),
    ("handoff", r"\bhandled elsewhere\b|\b's job\b|\bbelongs elsewhere\b"),
    ("low_quality", r"\b(?:naive|crude|simplistic|quick and dirty)\b"),
]
_COMPILED = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in DEFERRAL_PATTERNS]

# A line is "tracked" (allowed) only if it cites a real reference. No
# per-line escape marker exists by design (see module docstring).
TRACKING_RE = re.compile(
    r"#\d+|ADR[-\s]?\d+|\bFollow[-\s]?up\b|\bT-\d+\b|\bD\d+\b|issues?/\d+",
    re.IGNORECASE,
)

# Per-phrase exclusions for high-frequency *legitimate* technical collocations,
# so the gate does not flag honest code. This is a central, reviewed list — the
# only sanctioned suppression. New genuine collocations are added here (via PR),
# never via a per-line opt-out.
EXCLUSIONS: dict[str, re.Pattern[str]] = {
    "temporary": re.compile(
        r"tempfile|TemporaryDirectory|NamedTemporary|mkdtemp|tmp_?dir|temp_?dir|tmp_?path",
        re.IGNORECASE,
    ),
    "placeholder": re.compile(r"""placeholder\s*=|["']placeholder["']""", re.IGNORECASE),
    "v1": re.compile(r"/v1\b|\bv1\.\d|schema[_\s-]?version|api[_/]v1", re.IGNORECASE),
    "xxx": re.compile(r"xx+x", re.IGNORECASE),  # XXXX... censor/format runs, not the marker
}


@dataclass
class Hit:
    path: str
    lineno: int
    phrase: str
    tracked: bool
    text: str


def _excluded(phrase: str, line: str) -> bool:
    pat = EXCLUSIONS.get(phrase)
    return bool(pat and pat.search(line))


def _hits_in_line(rel: str, lineno: int, line: str) -> list[Hit]:
    tracked = bool(TRACKING_RE.search(line))
    out: list[Hit] = []
    for name, rx in _COMPILED:
        if rx.search(line) and not _excluded(name, line):
            out.append(Hit(path=rel, lineno=lineno, phrase=name, tracked=tracked, text=line.strip()[:160]))
    return out


def scan_tree(root: Path, repo_root: Path) -> list[Hit]:
    out: list[Hit] = []
    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            rel = py.relative_to(repo_root).as_posix()
        except ValueError:
            rel = py.as_posix()
        for i, line in enumerate(text.splitlines(), start=1):
            out.extend(_hits_in_line(rel, i, line))
    return out


def _metrics(hits: list[Hit]) -> dict:
    untracked = [h for h in hits if not h.tracked]
    tracked = [h for h in hits if h.tracked]
    by_phrase = Counter(h.phrase for h in untracked)
    return {
        "untracked_total": len(untracked),
        "tracked_total": len(tracked),
        "by_phrase": dict(sorted(by_phrase.items())),
    }


def _build_baseline(root: Path, metrics: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {"root": root.as_posix()},
        "current": metrics,
        "ratchet": {
            # No headroom: the untracked total may never grow. Per-phrase caps
            # lock each category so one cannot balloon while another shrinks.
            "max_untracked_total": metrics["untracked_total"],
            "max_by_phrase": metrics["by_phrase"],
        },
        "ratchet_policy": (
            "Whole-repo untracked deferral counts may shrink but never grow. "
            "After tracking or removing deferrals, re-run --write-baseline to "
            "ratchet down. New untracked deferrals in a PR diff are blocked by "
            "the --diff gate."
        ),
    }


def _check_against_baseline(baseline: dict, metrics: dict) -> list[str]:
    violations: list[str] = []
    ratchet = baseline.get("ratchet", {})
    cap_total = ratchet.get("max_untracked_total")
    if cap_total is not None and metrics["untracked_total"] > cap_total:
        violations.append(
            f"untracked deferrals: {metrics['untracked_total']} > ratchet {cap_total} "
            f"(baseline {baseline['current']['untracked_total']})"
        )
    caps = ratchet.get("max_by_phrase", {})
    for phrase, count in metrics["by_phrase"].items():
        limit = caps.get(phrase, 0)
        if count > limit:
            violations.append(f"  phrase '{phrase}': {count} > ratchet {limit}")
    return violations


def _report_md(root: Path, hits: list[Hit], metrics: dict) -> str:
    untracked = [h for h in hits if not h.tracked]
    lines = [
        f"# Deferral discipline scan (`{root}`)",
        "",
        f"- Untracked deferrals: **{metrics['untracked_total']}**",
        f"- Tracked deferrals (with #NNN / ADR / Follow-up ref): {metrics['tracked_total']}",
        "",
        "## Untracked by phrase",
        "",
    ]
    for phrase, count in sorted(metrics["by_phrase"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{phrase}`: {count}")
    lines.append("")
    lines.append("## Untracked hits")
    lines.append("")
    for h in untracked:
        lines.append(f"- `{h.path}:{h.lineno}` [{h.phrase}] {h.text}")
    return "\n".join(lines)


def _diff_added_lines(base_ref: str, repo_root: Path) -> list[tuple[str, int, str]]:
    """Return (path, new_lineno, text) for lines added vs ``base_ref``."""
    out = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", "*.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    added: list[tuple[str, int, str]] = []
    path = ""
    new_ln = 0
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for raw in out.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
        elif raw.startswith("@@"):
            m = hunk_re.match(raw)
            new_ln = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            added.append((path, new_ln, raw[1:]))
            new_ln += 1
    return added


def _run_diff_gate(base_ref: str, repo_root: Path, root_prefix: str) -> int:
    added = _diff_added_lines(base_ref, repo_root)
    new_untracked: list[Hit] = []
    new_tracked = 0
    for path, lineno, text in added:
        # Only the product-code surface (same as the whole-repo baseline root).
        # This also excludes the scanner itself and its tests, whose pattern
        # fixtures legitimately contain the vocabulary.
        if not path.startswith(root_prefix):
            continue
        for h in _hits_in_line(path, lineno, text):
            if h.tracked:
                if h.phrase == "todo":
                    new_tracked += 1
            else:
                new_untracked.append(h)
    print(f"PR diff vs {base_ref}: +{new_tracked} tracked TODO(#NNN), +{len(new_untracked)} untracked deferral(s)")
    if new_untracked:
        for h in new_untracked:
            print(f"  - {h.path}:{h.lineno} [{h.phrase}] {h.text}", file=sys.stderr)
        print(
            "\nFAIL: this PR adds untracked deferral language. For each line above, pick one:\n"
            "  [1] Real deferral  -> implement the full functionality now instead of deferring;\n"
            "                        or, if it genuinely must wait, file an issue and cite it as\n"
            "                        `# TODO(#NNN): <what is deferred and why>`.\n"
            "  [2] False positive -> it is not really a deferral; add `# TODO(#NNN): <why this\n"
            "                        phrasing is fine>` citing an issue so it is tracked and the\n"
            "                        central EXCLUSIONS list can be refined to stop flagging it.\n"
            "  There is no silent bypass: every path leaves a tracked, reviewable trail.",
            file=sys.stderr,
        )
        return 1
    print("OK: no new untracked deferrals.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=DEFAULT_ROOT, type=Path)
    parser.add_argument("--out", default=None, type=Path, help="Write markdown report here")
    parser.add_argument("--write-baseline", default=None, type=Path, help="Write ratchet baseline JSON here and exit 0.")
    parser.add_argument("--check", default=None, type=Path, help="Compare whole repo against baseline; exit 1 on growth.")
    parser.add_argument("--diff", default=None, help="Base ref; scan only added lines, exit 1 on new untracked deferral.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    if args.diff:
        return _run_diff_gate(args.diff, repo_root, args.root.as_posix() + "/")

    hits = scan_tree(args.root.resolve(), repo_root)
    metrics = _metrics(hits)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_report_md(args.root, hits, metrics), encoding="utf-8")
        print(f"Wrote report to {args.out}")

    if args.write_baseline:
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline = _build_baseline(args.root, metrics)
        args.write_baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline to {args.write_baseline}")
        print(f"  Current: {json.dumps(metrics)}")
        return 0

    if args.check:
        if not args.check.exists():
            print(f"ERROR: baseline file not found: {args.check}", file=sys.stderr)
            return 2
        baseline = json.loads(args.check.read_text(encoding="utf-8"))
        violations = _check_against_baseline(baseline, metrics)
        print(f"Current: {json.dumps(metrics)}")
        if violations:
            print("\nFAIL: deferral ratchet violated (untracked count grew):", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print("OK: untracked deferrals within baseline ratchet.")
        return 0

    print(_report_md(args.root, hits, metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
