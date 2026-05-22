"""Detect semantic duplication via embedding clustering.

Walks a source root, extracts every function / method, embeds each one
with a code-tuned sentence-transformer, then reports clusters of
behaviourally similar functions (candidate semantic duplicates that
lexical tools like sentrux / jscpd cannot see).

Modes
-----
- Default (no --check / no --write-baseline): scan and emit a markdown
  report; optionally a JSON payload via --json-out.
- ``--write-baseline PATH``: scan, write a JSON baseline at PATH that
  captures current aggregate metrics + a ratchet config that future
  --check runs will enforce.
- ``--check PATH``: scan, compare aggregate metrics against the
  baseline at PATH; exit 1 if any ratchet is violated. Used in CI.

Usage examples
--------------
Local one-off:
    python scripts/semantic_dup_scan.py --out docs/audit/2026-05-21-semantic-dup-scan.md

Initial baseline:
    python scripts/semantic_dup_scan.py \\
        --write-baseline docs/audit/baselines/semantic-dup-baseline.json

CI gate:
    python scripts/semantic_dup_scan.py \\
        --check docs/audit/baselines/semantic-dup-baseline.json \\
        --json-out docs/audit/_latest/semantic-dup-current.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"
DEFAULT_THRESHOLD = 0.92
DEFAULT_MIN_LOC = 5
DEFAULT_RATCHET_SLACK = 0.05  # 5% headroom so initial baseline is not razor-tight


@dataclass
class Func:
    path: Path
    qualname: str
    lineno: int
    end_lineno: int
    source: str

    @property
    def loc(self) -> int:
        return self.end_lineno - self.lineno + 1


def _walk(node: ast.AST, qual: str) -> Iterator[tuple[ast.AST, str]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child, qual
        elif isinstance(child, ast.ClassDef):
            sub_qual = f"{qual}.{child.name}" if qual else child.name
            yield from _walk(child, sub_qual)
        else:
            yield from _walk(child, qual)


def _strip_docstring(node: ast.AST, lines: list[str]) -> str:
    body = node.body  # type: ignore[attr-defined]
    skip = set()
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        for ln in range(body[0].lineno, body[0].end_lineno + 1):
            skip.add(ln)
    return "\n".join(
        line
        for i, line in enumerate(lines, start=node.lineno)
        if i not in skip  # type: ignore[attr-defined]
    )


def extract_functions(root: Path, min_loc: int, repo_root: Path) -> list[Func]:
    out: list[Func] = []
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        all_lines = text.splitlines()
        for node, qual in _walk(tree, ""):
            if not hasattr(node, "end_lineno") or node.end_lineno is None:
                continue
            loc = node.end_lineno - node.lineno + 1
            if loc < min_loc:
                continue
            func_lines = all_lines[node.lineno - 1 : node.end_lineno]
            src = _strip_docstring(node, func_lines)
            qualname = f"{qual}.{node.name}" if qual else node.name
            try:
                rel = py.relative_to(repo_root)
            except ValueError:
                rel = py
            out.append(
                Func(
                    path=rel,
                    qualname=qualname,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno,
                    source=src,
                )
            )
    return out


def _cluster(sim_matrix, threshold: float) -> list[list[int]]:
    n = sim_matrix.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return [g for g in groups.values() if len(g) > 1]


def _avg_pairwise_sim(sim_matrix, idxs: list[int]) -> float:
    if len(idxs) < 2:
        return 1.0
    total = 0.0
    count = 0
    for i in range(len(idxs)):
        for j in range(i + 1, len(idxs)):
            total += float(sim_matrix[idxs[i], idxs[j]])
            count += 1
    return total / count if count else 1.0


def _scan(args, repo_root: Path):
    import numpy as np
    from fastembed import TextEmbedding

    funcs = extract_functions(args.root.resolve(), args.min_loc, repo_root)
    print(f"[1/4] Extracted {len(funcs)} functions (>= {args.min_loc} LOC) from {args.root}")
    if not funcs:
        return funcs, [], None

    # fastembed (ONNX runtime + int8-quantized BGE) replaces
    # sentence-transformers + PyTorch here. Install footprint drops from
    # ~2GB to ~100MB and cold inference is ~3x faster on CPU.
    print(f"[2/4] Loading model: {args.model}")
    model = TextEmbedding(model_name=args.model)

    print(f"[3/4] Embedding {len(funcs)} functions (this is the slow part)...")
    # fastembed.embed returns an iterator; stack into an (N, D) matrix.
    raw = np.array(list(model.embed([f.source for f in funcs], batch_size=16)))
    # L2-normalise so the dot product equals cosine similarity downstream.
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = raw / norms

    print(f"[4/4] Clustering at cosine threshold >= {args.threshold}")
    sim = embeddings @ embeddings.T
    np.fill_diagonal(sim, 0.0)
    clusters = _cluster(sim, args.threshold)
    enriched = []
    for c in clusters:
        total_loc = sum(funcs[i].loc for i in c)
        avg_sim = _avg_pairwise_sim(sim, c)
        enriched.append((c, total_loc, avg_sim))
    enriched.sort(key=lambda t: (-t[1], -len(t[0])))
    return funcs, enriched, sim


def _build_metrics(funcs: list[Func], enriched: list[tuple]) -> dict:
    total_loc = sum(f.loc for f in funcs)
    duplicate_loc = sum(loc for _, loc, _ in enriched)
    pct = (duplicate_loc / total_loc * 100) if total_loc else 0.0
    max_cluster_size = max((len(c) for c, _, _ in enriched), default=0)
    return {
        "functions_scanned": len(funcs),
        "clusters": len(enriched),
        "duplicate_loc": duplicate_loc,
        "total_loc": total_loc,
        "duplicate_pct": round(pct, 2),
        "max_cluster_size": max_cluster_size,
    }


def _build_report_md(args, funcs: list[Func], enriched: list[tuple], metrics: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Semantic duplication scan (`{args.root}`)")
    lines.append("")
    lines.append(f"- Functions scanned: {metrics['functions_scanned']}")
    lines.append(f"- Model: `{args.model}`")
    lines.append(f"- Cosine threshold: `{args.threshold}`")
    lines.append(f"- Min LOC: `{args.min_loc}`")
    lines.append(f"- Candidate duplicate clusters: **{metrics['clusters']}**")
    lines.append(
        f"- LOC inside duplicate clusters: **{metrics['duplicate_loc']}** / "
        f"{metrics['total_loc']} ({metrics['duplicate_pct']:.1f}%)"
    )
    lines.append(f"- Largest cluster: **{metrics['max_cluster_size']}** functions")
    lines.append("")
    for rank, (c, total_loc_c, avg_sim) in enumerate(enriched, 1):
        lines.append(f"## Cluster {rank} - {len(c)} funcs, {total_loc_c} LOC, avg sim={avg_sim:.3f}")
        lines.append("")
        for i in c:
            f = funcs[i]
            rel = f.path.as_posix()
            lines.append(f"- `{rel}:{f.lineno}`  `{f.qualname}`  ({f.loc} LOC)")
        lines.append("")
    return "\n".join(lines)


def _build_json_payload(args, funcs: list[Func], enriched: list[tuple], metrics: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "root": args.root.as_posix(),
            "model": args.model,
            "threshold": args.threshold,
            "min_loc": args.min_loc,
        },
        "metrics": metrics,
        "clusters": [
            {
                "size": len(c),
                "loc": total_loc_c,
                "avg_sim": round(avg_sim, 4),
                "members": [
                    {
                        "path": funcs[i].path.as_posix(),
                        "lineno": funcs[i].lineno,
                        "qualname": funcs[i].qualname,
                        "loc": funcs[i].loc,
                    }
                    for i in c
                ],
            }
            for c, total_loc_c, avg_sim in enriched
        ],
    }


def _build_baseline(args, metrics: dict) -> dict:
    def _ratchet(value, slack):
        return int(value * (1.0 + slack)) if isinstance(value, int) else round(value * (1.0 + slack), 2)

    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "root": args.root.as_posix(),
            "model": args.model,
            "threshold": args.threshold,
            "min_loc": args.min_loc,
        },
        "current": metrics,
        "ratchet": {
            "max_clusters": _ratchet(metrics["clusters"], DEFAULT_RATCHET_SLACK),
            "max_duplicate_pct": _ratchet(metrics["duplicate_pct"], DEFAULT_RATCHET_SLACK),
            "max_cluster_size": metrics["max_cluster_size"],
            "max_duplicate_loc": _ratchet(metrics["duplicate_loc"], DEFAULT_RATCHET_SLACK),
        },
        "ratchet_policy": (
            "Initial baseline allows ~5% headroom on count + LOC; max_cluster_size "
            "is set tight (no headroom) to prevent any cluster from growing. "
            "After fixing duplicates, re-run with --write-baseline to ratchet down."
        ),
    }


def _check_against_baseline(baseline: dict, metrics: dict) -> list[str]:
    violations: list[str] = []
    ratchet = baseline.get("ratchet", {})
    for key, observed_key, label in (
        ("max_clusters", "clusters", "cluster count"),
        ("max_duplicate_pct", "duplicate_pct", "duplicate LOC %"),
        ("max_cluster_size", "max_cluster_size", "largest cluster size"),
        ("max_duplicate_loc", "duplicate_loc", "duplicate LOC absolute"),
    ):
        limit = ratchet.get(key)
        observed = metrics.get(observed_key)
        if limit is None or observed is None:
            continue
        if observed > limit:
            violations.append(
                f"{label}: {observed} > ratchet {limit} (baseline {baseline['current'].get(observed_key)})"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="src/scistudio", type=Path)
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
    parser.add_argument("--min-loc", default=DEFAULT_MIN_LOC, type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", default=None, type=Path, help="Write human markdown report here")
    parser.add_argument("--json-out", default=None, type=Path, help="Write full JSON payload here")
    parser.add_argument(
        "--write-baseline",
        default=None,
        type=Path,
        help="Write baseline JSON (current metrics + auto-derived ratchet) to this path and exit 0.",
    )
    parser.add_argument(
        "--check",
        default=None,
        type=Path,
        help="Compare against baseline at this path; exit 1 on ratchet violation.",
    )
    parser.add_argument("--device", default=None, help="cpu / cuda (auto-detect if omitted)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    funcs, enriched, _sim = _scan(args, repo_root)
    if not funcs:
        print("Nothing to embed. Exiting.")
        return 0

    metrics = _build_metrics(funcs, enriched)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_build_report_md(args, funcs, enriched, metrics), encoding="utf-8")
        print(f"Wrote markdown report to {args.out}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(_build_json_payload(args, funcs, enriched, metrics), indent=2),
            encoding="utf-8",
        )
        print(f"Wrote JSON payload to {args.json_out}")

    if args.write_baseline:
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline = _build_baseline(args, metrics)
        args.write_baseline.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        print(f"\nWrote baseline to {args.write_baseline}")
        print(f"  Current: {json.dumps(metrics)}")
        print(f"  Ratchet: {json.dumps(baseline['ratchet'])}")
        return 0

    if args.check:
        if not args.check.exists():
            print(f"ERROR: baseline file not found: {args.check}", file=sys.stderr)
            return 2
        baseline = json.loads(args.check.read_text(encoding="utf-8"))
        violations = _check_against_baseline(baseline, metrics)
        print(f"\nCurrent: {json.dumps(metrics)}")
        print(f"Ratchet: {json.dumps(baseline.get('ratchet', {}))}")
        if violations:
            print("\nFAIL: semantic duplication ratchet violated:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print("\nOK: all ratchets within limits.")
        return 0

    if not args.out and not args.json_out:
        print()
        print(_build_report_md(args, funcs, enriched, metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
