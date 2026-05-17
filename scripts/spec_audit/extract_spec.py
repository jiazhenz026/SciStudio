"""extract_spec — parse `docs/specs/INTERFACE_SPEC.md` per the locked grammar.

The grammar (locked Phase 0.3 — alongside this parser):

    ## <N>. <module-name>
    ### `interface_id` — <short description>
    Status: a | b | c | d
    Source: `path/to/file.py:Lnn-Lmm`
    Primary-doc-source: `docs/architecture/ARCHITECTURE.md §X.Y` | `[ARCHITECTURE: not documented]`
    Supplementary-doc-source: ADR-NNN §X, ADR-MMM §Y    (optional, comma-separated)
    Issue: #NNN | #TBD-<short>                          (required if Status in {b,c,d})

    ```<lang>
    <signature block>
    ```

Grammar invariants:
  - Each `### ` heading starts a new InterfaceRecord
  - The `Status:` field is REQUIRED and must be exactly one of a/b/c/d
  - The `Source:` field MUST be present and parseable (path + L-line range)
  - `Primary-doc-source:` is REQUIRED — either ARCHITECTURE.md§X.Y or the
    literal placeholder `[ARCHITECTURE: not documented]` (forces a docs
    fix follow-up issue)
  - `Issue:` is REQUIRED iff Status ∈ {b,c,d}
  - The fenced code block under the entry is the signature; its language tag
    indicates the surface kind hint (python / json / http / etc.)

This parser is strict: deviations are errors, not warnings. The point is to
make the SSOT machine-checkable.

Usage:
    python -m scripts.spec_audit.extract_spec [--spec PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .models import InterfaceRecord

STATUS_RE = re.compile(r"^\s*Status:\s*([abcd])\s*$", re.IGNORECASE)
SOURCE_RE = re.compile(r"^\s*Source:\s*`([^`]+)`\s*$")
PDS_RE = re.compile(r"^\s*Primary-doc-source:\s*(.+?)\s*$")
SDS_RE = re.compile(r"^\s*Supplementary-doc-source:\s*(.+?)\s*$")
ISSUE_RE = re.compile(r"^\s*Issue:\s*(#\S+)\s*$")
INTERFACE_HEADING_RE = re.compile(r"^###\s+`([^`]+)`\s+—\s+(.+?)\s*$")
MODULE_HEADING_RE = re.compile(r"^##\s+\d+\.\s+(\S+?)\s*$")
FENCE_OPEN_RE = re.compile(r"^```(\S+)?\s*$")
FENCE_CLOSE_RE = re.compile(r"^```\s*$")
SOURCE_PATH_LINES_RE = re.compile(r"^(.+?):L(\d+)-L(\d+)$")


class SpecParseError(Exception):
    """Raised when the spec doc violates the grammar."""


def parse_spec(spec_path: Path) -> list[InterfaceRecord]:
    if not spec_path.exists():
        # An empty / missing SSOT is valid during Phase 6 draft; emit zero records.
        return []

    lines = spec_path.read_text(encoding="utf-8").splitlines()
    records: list[InterfaceRecord] = []
    current_module: str | None = None
    errors: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if mo := MODULE_HEADING_RE.match(line):
            current_module = mo.group(1)
            i += 1
            continue

        ih = INTERFACE_HEADING_RE.match(line)
        if not ih:
            i += 1
            continue

        # Start of new entry
        interface_id = ih.group(1)
        short_desc = ih.group(2)
        heading_line_no = i + 1
        i += 1

        status: str | None = None
        source: str | None = None
        primary_doc: str | None = None
        supplementary_doc: list[str] | None = None
        issue: str | None = None
        signature_lang: str | None = None
        signature_body: list[str] = []

        # Read field lines + the fenced code block until the next ### / ## / EOF
        while i < len(lines):
            row = lines[i]
            if MODULE_HEADING_RE.match(row) or INTERFACE_HEADING_RE.match(row):
                break
            if mo := STATUS_RE.match(row):
                status = mo.group(1).lower()
            elif mo := SOURCE_RE.match(row):
                source = mo.group(1)
            elif mo := PDS_RE.match(row):
                primary_doc = mo.group(1).strip("`")
            elif mo := SDS_RE.match(row):
                supplementary_doc = [s.strip() for s in mo.group(1).split(",") if s.strip()]
            elif mo := ISSUE_RE.match(row):
                issue = mo.group(1)
            elif FENCE_OPEN_RE.match(row):
                fmo = FENCE_OPEN_RE.match(row)
                signature_lang = fmo.group(1) if fmo else None
                i += 1
                while i < len(lines) and not FENCE_CLOSE_RE.match(lines[i]):
                    signature_body.append(lines[i])
                    i += 1
            i += 1

        # Grammar validation
        if status is None:
            errors.append(f"{spec_path}:L{heading_line_no} — `{interface_id}` missing Status:")
            i += 1
            continue
        if source is None:
            errors.append(f"{spec_path}:L{heading_line_no} — `{interface_id}` missing Source:")
            i += 1
            continue
        if primary_doc is None:
            errors.append(f"{spec_path}:L{heading_line_no} — `{interface_id}` missing Primary-doc-source:")
            i += 1
            continue
        if status in {"b", "c", "d"} and issue is None:
            errors.append(f"{spec_path}:L{heading_line_no} — `{interface_id}` status={status} requires Issue: line")
            i += 1
            continue

        # Parse source path + lines
        source_file: str | None = source
        source_lines: str | None = None
        spm = SOURCE_PATH_LINES_RE.match(source)
        if spm:
            source_file = spm.group(1)
            source_lines = f"L{spm.group(2)}-L{spm.group(3)}"

        # Infer kind hint from fence language (rough; manual override later)
        kind_hint_map = {
            "python": "abc",  # default; could be pydantic / protocol; spec author chooses
            "json": "pydantic",
            "http": "fastapi_route",
            "yaml": "pydantic",
            "toml": "entry_point",
        }
        kind_hint = kind_hint_map.get(signature_lang or "python", "abc")

        records.append(
            InterfaceRecord(
                interface_id=interface_id,
                kind=kind_hint,  # type: ignore[arg-type]
                module=current_module or "unknown",
                source_file=source_file,
                source_lines=source_lines,
                signature={
                    "short": short_desc,
                    "lang": signature_lang,
                    "body": "\n".join(signature_body),
                },
                status=status,  # type: ignore[arg-type]
                primary_doc_source=primary_doc,
                supplementary_doc_source=supplementary_doc,
                issue=issue,
            )
        )

        # Don't double-increment if we broke out of the loop on next ### or ##
        if i < len(lines) and (MODULE_HEADING_RE.match(lines[i]) or INTERFACE_HEADING_RE.match(lines[i])):
            continue
        i += 1

    if errors:
        raise SpecParseError(f"INTERFACE_SPEC.md grammar errors ({len(errors)}):\n" + "\n".join(errors))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse INTERFACE_SPEC.md → JSON records")
    ap.add_argument("--spec", type=Path, default=Path("docs/specs/INTERFACE_SPEC.md"))
    ap.add_argument("--out", type=Path, default=Path("build/spec-audit/spec.json"))
    args = ap.parse_args()

    try:
        records = parse_spec(args.spec)
    except SpecParseError as exc:
        print(f"[extract_spec] ERROR:\n{exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([r.to_dict() for r in records], indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[extract_spec] wrote {len(records)} records → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
