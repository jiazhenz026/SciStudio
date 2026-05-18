"""Consolidate the ADR-042 cascade into a single view per ADR-042 §27.5.

ADR-042 §27.5 mandates that ``docs/adr/_consolidated/cascade-current.md``
be auto-generated from the union of the base ADR (currently ADR-042) and
every addendum that carries ``amends:`` records in its frontmatter
(currently ADR-043 and ADR-044). The "addendum wins" prose has been
replaced with explicit, machine-readable amendment declarations whose
``kind`` (extend / replace / constrain / clarify) determines precedence.

This is the v1 implementation, shipped under #1169 (Phase 1D sub-PR 2):

* Walks ``docs/adr/`` for ADR markdown files.
* For each file, parses the YAML frontmatter and extracts ``amends``.
* Emits a deterministic concatenation:

  1. ADR-042 body (verbatim).
  2. One section per amending addendum (ADR-043, ADR-044, …) listing
     ``target`` / ``kind`` / ``summary`` for every amendment plus the
     full body of that addendum.
* ``--verify`` mode hashes the would-be output and compares against the
  on-disk artifact; non-zero exit if they diverge.

Out of scope for v1
-------------------
The full text-substitution apply-pass (rewriting ADR-042 §X.Y prose in
place per each ``replace`` amendment) is deferred — that requires a
markdown-section-aware editor whose contract is itself worth a separate
review. v1 emits a structured concatenation that makes every amendment
visible without rewriting parent prose.

TODO(#1169-followup): implement the apply-pass once the markdown
section editor lands. Out of scope per ADR-042 §27.5 v1 plan + change
plan #1169.
  Followup: open after 1D sub-PR 2 merges.

CLI
---
``python -m scripts.audit.consolidate_cascade [--verify] [--output PATH]``

* No flags → emits ``docs/adr/_consolidated/cascade-current.md``.
* ``--verify`` → re-generates in memory, compares hash with on-disk file,
  exits 0 on match else 1 (used by CI guard).
* ``--output PATH`` → writes to PATH instead of the canonical location
  (useful for diff-only workflows).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ------------------------------------------------------------------ paths

# Canonical layout: repo_root/docs/adr/*.md.
# This script lives at repo_root/scripts/audit/consolidate_cascade.py.
_THIS_FILE = Path(__file__).resolve()
REPO_ROOT_DEFAULT = _THIS_FILE.parent.parent.parent
ADR_DIR_REL = Path("docs/adr")
OUTPUT_REL = Path("docs/adr/_consolidated/cascade-current.md")

# The base ADR of the QA cascade. Hardcoded because ADR-042 is the named
# anchor of §27.5; if a future ADR establishes a different cascade base,
# the value moves into the fact registry.
BASE_ADR_NUM = 42


# ----------------------------------------------------------------- types


@dataclass(frozen=True)
class AmendmentRecord:
    """In-memory mirror of ``scieasy.qa.schemas.frontmatter.Amendment``.

    We deliberately do not import the pydantic model here — this script
    runs in environments (CI early stages, ADR docs-only PRs) where
    ``scieasy`` may not be installed. The frontmatter shape is simple
    and stable enough to parse with the stdlib.
    """

    target: str
    kind: str
    summary: str


@dataclass(frozen=True)
class ParsedADR:
    """One ADR's frontmatter (parsed) + raw body."""

    adr_num: int
    path: Path
    title: str
    status: str
    amends: tuple[AmendmentRecord, ...]
    body: str  # everything after the closing `---` of frontmatter


# ----------------------------------------------------- frontmatter parser
#
# We use a minimal stdlib YAML reader — the ADR frontmatter format is
# constrained by ADRFrontmatter so we only need a handful of constructs:
# scalars, lists, nested mapping (for `amends`). We could call pyyaml
# but importing it here couples this script to a dep that may not be
# present in every CI lane. The custom reader is small and tested.


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<fm>.*?\n)---\s*\n(?P<body>.*)",
    re.DOTALL,
)
_ADR_FILENAME_RE = re.compile(r"ADR-(\d+)\.md$")


def _strip_inline_comment(line: str) -> str:
    """Strip ``# comment`` tail from a YAML line, respecting strings."""
    # Simple heuristic: a `#` preceded by whitespace and not inside
    # double quotes starts a comment. Single-quoted strings in our
    # frontmatter never contain `#`, so we can skip that case.
    in_dq = False
    out = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            in_dq = not in_dq
            out.append(ch)
        elif ch == "#" and not in_dq and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _unquote(value: str) -> str:
    """Strip surrounding quotes from a YAML scalar value."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _parse_frontmatter_for_amends(fm_text: str) -> dict[str, object]:
    """Extract the subset of frontmatter fields we care about.

    Returns a dict with keys: ``title`` (str), ``status`` (str),
    ``amends`` (list[AmendmentRecord]). Unknown keys are ignored.

    The parser handles only what real ADR frontmatter contains:
    top-level ``key: value`` lines, the multi-line ``amends:`` list of
    mappings, and YAML comments. It is intentionally NOT a general-purpose
    YAML parser — generality would require pyyaml and would invite the
    very drift this script exists to detect.
    """
    out: dict[str, object] = {"title": "", "status": "", "amends": []}
    amends: list[AmendmentRecord] = []

    lines = fm_text.splitlines()
    i = 0
    in_amends = False
    cur_amend: dict[str, str] = {}

    while i < len(lines):
        raw = lines[i]
        line = _strip_inline_comment(raw)

        if not line.strip():
            i += 1
            continue

        # Top-level key
        if not line.startswith(" ") and ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()

            # Close any open amendment record before processing a new top-level key
            if in_amends and key != "amends":
                if cur_amend:
                    amends.append(
                        AmendmentRecord(
                            target=cur_amend.get("target", ""),
                            kind=cur_amend.get("kind", ""),
                            summary=cur_amend.get("summary", ""),
                        )
                    )
                    cur_amend = {}
                in_amends = False

            if key == "title":
                out["title"] = _unquote(rest)
            elif key == "status":
                out["status"] = _unquote(rest)
            elif key == "amends":
                in_amends = True
                cur_amend = {}
                # Inline form `amends: []` — nothing to consume.
                if rest in ("", "[]"):
                    pass
            i += 1
            continue

        # Indented line — only meaningful inside `amends:`
        if in_amends:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if stripped.startswith("- "):
                # New amendment record
                if cur_amend:
                    amends.append(
                        AmendmentRecord(
                            target=cur_amend.get("target", ""),
                            kind=cur_amend.get("kind", ""),
                            summary=cur_amend.get("summary", ""),
                        )
                    )
                    cur_amend = {}
                # `- key: value` on the same line
                after = stripped[2:]
                if ":" in after:
                    k, _, v = after.partition(":")
                    cur_amend[k.strip()] = _unquote(v.strip())
            elif ":" in stripped and indent >= 2:
                k, _, v = stripped.partition(":")
                cur_amend[k.strip()] = _unquote(v.strip())
            # else: ignore
        i += 1

    # Flush trailing amendment
    if cur_amend:
        amends.append(
            AmendmentRecord(
                target=cur_amend.get("target", ""),
                kind=cur_amend.get("kind", ""),
                summary=cur_amend.get("summary", ""),
            )
        )

    out["amends"] = amends
    return out


def parse_adr(path: Path) -> ParsedADR | None:
    """Parse a single ADR markdown file.

    Returns ``None`` if the file has no frontmatter or no parseable ADR
    number in its filename (e.g. ``ADR.md`` is the legacy monolith).
    """
    m = _ADR_FILENAME_RE.search(path.name)
    if not m:
        return None
    adr_num = int(m.group(1))

    text = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    fm_text = fm_match.group("fm")
    body = fm_match.group("body")

    fields = _parse_frontmatter_for_amends(fm_text)
    return ParsedADR(
        adr_num=adr_num,
        path=path,
        title=str(fields.get("title", "")),
        status=str(fields.get("status", "")),
        amends=tuple(fields.get("amends", [])),  # type: ignore[arg-type]
        body=body,
    )


# ----------------------------------------------------- consolidator


def discover_adrs(repo_root: Path) -> list[ParsedADR]:
    """Return all ADR-NNN.md files under ``docs/adr/`` parsed, sorted by num."""
    adr_dir = repo_root / ADR_DIR_REL
    if not adr_dir.is_dir():
        return []
    parsed: list[ParsedADR] = []
    for p in sorted(adr_dir.glob("ADR-*.md")):
        result = parse_adr(p)
        if result is not None:
            parsed.append(result)
    return sorted(parsed, key=lambda a: a.adr_num)


def render_cascade(adrs: list[ParsedADR]) -> str:
    """Render the consolidated cascade view.

    Layout:
        # ADR-042 Cascade — Consolidated View
        (header note)

        ## Base ADR-042
        <ADR-042 body>

        ## Amending Addenda

        ### ADR-043 — <title>
        Status: <status>

        Amendments:
          - target / kind / summary
          - ...

        <ADR-043 body>

        ### ADR-044 — <title>
        ...
    """
    base = next((a for a in adrs if a.adr_num == BASE_ADR_NUM), None)
    if base is None:
        raise RuntimeError(f"Base ADR-{BASE_ADR_NUM} not found under docs/adr/ — cannot render cascade.")

    amenders = [a for a in adrs if a.amends and a.adr_num != BASE_ADR_NUM]

    parts: list[str] = []
    parts.append("# ADR-042 Cascade — Consolidated View")
    parts.append("")
    parts.append(
        "> **Auto-generated** by `scripts/audit/consolidate_cascade.py` per "
        "ADR-042 §27.5. Do NOT hand-edit — `consolidate_cascade.py --verify` "
        "rejects drift. Regenerate via `python -m scripts.audit.consolidate_cascade`."
    )
    parts.append("")
    parts.append(f"## Base ADR-{base.adr_num:03d} — {base.title}")
    parts.append("")
    parts.append(f"_Status: {base.status}_")
    parts.append("")
    parts.append(base.body.rstrip())
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Amending Addenda")
    parts.append("")
    if not amenders:
        parts.append("_(no amending addenda)_")
    else:
        for addendum in amenders:
            parts.append(f"### ADR-{addendum.adr_num:03d} — {addendum.title}")
            parts.append("")
            parts.append(f"_Status: {addendum.status}_")
            parts.append("")
            parts.append("**Amendments declared in frontmatter (§27.5):**")
            parts.append("")
            for amend in addendum.amends:
                parts.append(f"- **target**: `{amend.target}`")
                parts.append(f"  - **kind**: `{amend.kind}`")
                parts.append(f"  - **summary**: {amend.summary}")
            parts.append("")
            parts.append(f"**Body of ADR-{addendum.adr_num:03d}:**")
            parts.append("")
            parts.append(addendum.body.rstrip())
            parts.append("")
            parts.append("---")
            parts.append("")

    return "\n".join(parts) + "\n"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- CLI


def _resolve_output(repo_root: Path, output: Path | None) -> Path:
    if output is not None:
        return output
    return repo_root / OUTPUT_REL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="consolidate_cascade",
        description=("Consolidate ADR-042 + addenda into a single view per ADR-042 §27.5."),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Path to write the consolidated view. "
            "Default: docs/adr/_consolidated/cascade-current.md relative to "
            "--repo-root."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=("Verify-only mode: compare in-memory render against on-disk file; exit 1 on mismatch. Used by CI guard."),
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    output_path = _resolve_output(repo_root, args.output)

    adrs = discover_adrs(repo_root)
    if not adrs:
        print(
            f"ERROR: no ADRs discovered under {repo_root / ADR_DIR_REL}",
            file=sys.stderr,
        )
        return 2

    try:
        rendered = render_cascade(adrs)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.verify:
        if not output_path.is_file():
            print(
                f"ERROR (verify): {output_path} does not exist. Run "
                f"`python -m scripts.audit.consolidate_cascade` to create it.",
                file=sys.stderr,
            )
            return 1
        on_disk = output_path.read_text(encoding="utf-8")
        if _hash(on_disk) != _hash(rendered):
            print(
                f"ERROR (verify): {output_path} differs from re-rendered "
                f"cascade. Regenerate with `python -m scripts.audit."
                f"consolidate_cascade`.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {output_path} matches in-memory render.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path} ({len(rendered):,} bytes).")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    sys.exit(main())
