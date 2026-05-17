"""extract_docs — grep ARCHITECTURE.md + ADR/*.md + CLAUDE.md for symbols
mentioned in code.json.

Output: for each unique symbol referenced in code.json, list every doc file
that mentions it, with the surrounding fenced-code block or ±10 lines of
context.

Conservative match: only emits hits where the symbol appears either inside a
markdown fence (``` block) or in a `backticked` span. Plain-prose mentions
without backticks are too noisy and create false-positive doc-orphans.

Usage:
    python -m scripts.spec_audit.extract_docs [--repo-root PATH] [--code PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Doc files in scope per the cascade plan (ARCHITECTURE primary, ADRs supplementary).
DOC_PATHS: list[str] = [
    "docs/architecture/ARCHITECTURE.md",
    "CLAUDE.md",
]
DOC_GLOBS: list[str] = [
    "docs/adr/ADR-*.md",
]


def _gather_doc_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in DOC_PATHS:
        p = repo_root / rel
        if p.exists():
            files.append(p)
    for glob in DOC_GLOBS:
        files.extend(sorted((repo_root).glob(glob)))
    return files


# Extract the symbol "tail" — the bit users actually grep for.
# For "block-abc.Block.run" → ["Block.run", "Block", "run"]
# For "rest-api.GET_/api/blocks/" → ["GET_/api/blocks/", "/api/blocks/"]
def _symbol_aliases(interface_id: str) -> list[str]:
    aliases: list[str] = [interface_id]
    if "." in interface_id:
        parts = interface_id.split(".")
        # tail: last 1-3 dotted parts
        for n in (3, 2, 1):
            if n <= len(parts):
                aliases.append(".".join(parts[-n:]))
    # REST routes: pull out the path itself
    if interface_id.startswith("rest-api."):
        rest = interface_id[len("rest-api.") :]
        if "_/" in rest:
            method, path = rest.split("_", 1)
            aliases.append(path)
            aliases.append(f"{method} {path}")
    # dedupe but preserve order
    seen: set[str] = set()
    out: list[str] = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _find_mentions_in_file(file_path: Path, alias: str) -> list[dict[str, Any]]:
    """Return [{anchor: 'Lnn', snippet: '...'}] for each backtick / fence hit."""
    hits: list[dict[str, Any]] = []
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # Tracking fence-block state
    in_fence = False
    fence_start_line = 0
    fence_buf: list[str] = []
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                # Close fence — check if alias appears in fence body
                body = "\n".join(fence_buf)
                if alias in body:
                    hits.append(
                        {
                            "anchor": f"L{fence_start_line}-L{idx}",
                            "snippet": body[:500] + ("..." if len(body) > 500 else ""),
                        }
                    )
                in_fence = False
                fence_buf = []
            else:
                in_fence = True
                fence_start_line = idx
            continue
        if in_fence:
            fence_buf.append(line)
            continue
        # Out of fence: check for backtick-wrapped mention
        pattern = rf"`[^`]*{re.escape(alias)}[^`]*`"
        if re.search(pattern, line):
            ctx_start = max(0, idx - 3)
            ctx_end = min(len(lines), idx + 3)
            snippet = "\n".join(lines[ctx_start:ctx_end])
            hits.append(
                {
                    "anchor": f"L{idx}",
                    "snippet": snippet[:500] + ("..." if len(snippet) > 500 else ""),
                }
            )
    return hits


def gather_doc_mentions(
    repo_root: Path,
    interface_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Return {interface_id: [{file, anchor, snippet}, ...]}."""
    doc_files = _gather_doc_files(repo_root)
    result: dict[str, list[dict[str, Any]]] = {}
    for iid in interface_ids:
        aliases = _symbol_aliases(iid)
        all_hits: list[dict[str, Any]] = []
        for doc in doc_files:
            for alias in aliases:
                hits = _find_mentions_in_file(doc, alias)
                for h in hits:
                    h["file"] = doc.relative_to(repo_root).as_posix()
                    h["alias"] = alias
                    all_hits.append(h)
        if all_hits:
            result[iid] = all_hits
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Find doc mentions of code interfaces")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--code", type=Path, default=Path("build/spec-audit/code.json"))
    ap.add_argument("--out", type=Path, default=Path("build/spec-audit/docs.json"))
    args = ap.parse_args()

    if not args.code.exists():
        print(f"[extract_docs] ERROR: code.json not found at {args.code} — run extract_code first", file=sys.stderr)
        return 2

    code_records = json.loads(args.code.read_text(encoding="utf-8"))
    interface_ids = [r["interface_id"] for r in code_records]
    mentions = gather_doc_mentions(args.repo_root, interface_ids)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(mentions, indent=2, default=str),
        encoding="utf-8",
    )
    print(
        f"[extract_docs] {sum(len(v) for v in mentions.values())} mentions across {len(mentions)} interfaces → {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
