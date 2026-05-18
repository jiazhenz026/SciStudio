"""Bootstrap the repo-root ``MAINTAINERS`` file from ADR ``governs`` (ADR-042 §A.3).

This script is the Phase 1C one-shot migration that produces the
initial ``MAINTAINERS`` file. It:

1. Reads YAML frontmatter from every ADR in ``docs/adr/`` and every
   spec in ``docs/specs/`` (Accepted or Proposed; phase != deprecated).
   Note: ADR-043 §3.2 sample uses ``docs/spec/`` (singular) but the
   real on-disk path is ``docs/specs/`` (plural — see ADR-042 §22.4
   etc.). Plural is canonical; singular form recorded as an ADR-043
   §27.4 errata candidate.
2. Extracts ``governs.modules`` and ``governs.files`` from each.
3. Emits one ``MaintainersEntry`` per ADR/spec where:
   - ``path_glob`` = the module path expanded to a glob
     (``scieasy.qa.audit`` → ``src/scieasy/qa/audit/**``), or the
     literal ``governs.files`` entry.
   - ``adrs`` = the source ADR number.
   - ``humans`` = single Tier-2 maintainer (default ``@jiazhenz026``).
   - ``agents_allowed`` = all 5 runtimes (per ADR-042 §A.3 default).
4. Validates the emitted YAML against ``Maintainers`` and writes it.

Re-runs are idempotent on a clean repo (deterministic ordering).

References
----------
ADR-042 §6 — ``MAINTAINERS`` schema and file format.
ADR-042 Appendix A.3 — bootstrap algorithm and defaults.
ADR-042 §27.4 — out-of-scope items live as in-repo TODO markers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

# Module-path → glob mapping rule (ADR-042 §6.4 "globs are repo-relative"):
# ``scieasy.foo.bar`` is the Python dotted path; it lives at
# ``src/scieasy/foo/bar/**``.
_SRC_PREFIX = "src/"


def _module_to_glob(module: str) -> str:
    """Convert a dotted Python module path to a repo-relative glob.

    ``scieasy.qa.audit`` → ``src/scieasy/qa/audit/**``.

    This is the inverse of ``importlib``'s lookup convention and matches
    ADR-042 §6.4 path glob semantics.
    """
    parts = module.split(".")
    return _SRC_PREFIX + "/".join(parts) + "/**"


def _load_frontmatter(adr_path: Path) -> dict[str, Any] | None:
    """Parse the YAML frontmatter block of an ADR/spec file.

    Returns ``None`` if no frontmatter block is present. Raises
    ``yaml.YAMLError`` on malformed YAML — the caller is expected to
    surface that to the user.
    """
    text = adr_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    yaml_block = text[4:end]
    parsed = yaml.safe_load(yaml_block)
    if not isinstance(parsed, dict):
        return None
    return parsed


def _collect_governance(repo_root: Path) -> list[dict[str, Any]]:
    """Walk ``docs/adr/`` and ``docs/specs/`` and collect governs entries.

    Returns a list of ``{adr: int, modules: list[str], files: list[str]}``
    dictionaries, one per ADR/spec with parseable frontmatter and a
    non-empty ``governs`` block. Sort order: ADR number ascending,
    then spec name alphabetical, so the output is deterministic.
    """
    entries: list[tuple[int | None, str, dict[str, Any]]] = []

    adr_dir = repo_root / "docs" / "adr"
    if adr_dir.exists():
        for adr_file in sorted(adr_dir.glob("ADR-*.md")):
            fm = _load_frontmatter(adr_file)
            if fm is None:
                continue
            governs = fm.get("governs") or {}
            if not isinstance(governs, dict):
                continue
            modules = governs.get("modules") or []
            files = governs.get("files") or []
            if not modules and not files:
                continue
            # File name pattern: ``ADR-NNN.md`` → number NNN.
            stem = adr_file.stem
            try:
                adr_number = int(stem.replace("ADR-", ""))
            except ValueError:
                continue
            entries.append(
                (
                    adr_number,
                    adr_file.name,
                    {
                        "adr": adr_number,
                        "modules": list(modules),
                        "files": list(files),
                    },
                )
            )

    # ADR text uses "docs/spec/" (singular) in some places, but the
    # on-disk directory is "docs/specs/" (plural). Plural is canonical
    # — see ADR-042 §22.4, §3.6, §26.3.4, ADR-043 §3.6.4.
    spec_dir = repo_root / "docs" / "specs"
    if spec_dir.exists():
        for spec_file in sorted(spec_dir.glob("*.md")):
            fm = _load_frontmatter(spec_file)
            if fm is None:
                continue
            governs = fm.get("governs") or {}
            if not isinstance(governs, dict):
                continue
            modules = governs.get("modules") or []
            files = governs.get("files") or []
            if not modules and not files:
                continue
            entries.append(
                (
                    None,
                    spec_file.name,
                    {
                        "adr": None,
                        "spec": spec_file.stem,
                        "modules": list(modules),
                        "files": list(files),
                    },
                )
            )

    # Sort: ADRs by number (None last for specs), then by file name.
    entries.sort(key=lambda e: (e[0] is None, e[0] if e[0] is not None else 0, e[1]))
    return [e[2] for e in entries]


def _build_entries(
    governance: list[dict[str, Any]],
    default_human: str,
    default_agents: list[str],
) -> list[dict[str, Any]]:
    """Produce the ``entries`` list for ``MAINTAINERS`` from governance data.

    One entry per ADR's module list (one combined entry, with all the
    modules' globs flattened into the dominant ``path_glob`` per ADR-042
    §6.5 most-specific-wins). Files in ``governs.files`` produce one
    entry per file (since globs are heterogeneous: workflows, templates,
    .md files).

    Per ADR-042 Appendix A.3 the human reviews and refines after this
    bootstrap. We deliberately emit one entry per module rather than
    over-cluster so the human can easily prune later.
    """
    out: list[dict[str, Any]] = []

    for gov in governance:
        adr = gov.get("adr")
        spec = gov.get("spec")
        adrs_field = [adr] if adr is not None else []
        source_note = f"ADR-{adr:03d}" if adr is not None else f"spec {spec}"

        for module in gov["modules"]:
            entry = {
                "path_glob": _module_to_glob(module),
                "adrs": adrs_field,
                "humans": [default_human],
                "agents_allowed": default_agents,
                "notes": f"Module {module}. Bootstrapped from {source_note}.",
            }
            out.append(entry)

        for file_glob in gov["files"]:
            entry = {
                "path_glob": file_glob,
                "adrs": adrs_field,
                "humans": [default_human],
                "agents_allowed": default_agents,
                "notes": f"File {file_glob}. Bootstrapped from {source_note}.",
            }
            out.append(entry)

    return out


def render_maintainers(
    repo_root: Path,
    default_human: str = "@jiazhenz026",
    default_agents: list[str] | None = None,
) -> str:
    """Compose the full ``MAINTAINERS`` YAML text.

    The schema (``scieasy.qa.schemas.maintainers.Maintainers``) requires
    ``entries`` to be non-empty; if no ADR/spec contributes governs data,
    a single fallback entry covering ``**`` is emitted so the file is
    syntactically valid.
    """
    if default_agents is None:
        default_agents = ["Claude", "Codex", "Cursor", "Aider", "Gemini"]

    governance = _collect_governance(repo_root)
    entries = _build_entries(governance, default_human, default_agents)

    if not entries:
        # Schema requires non-empty entries; emit a sentinel that's clearly
        # placeholder.
        entries = [
            {
                "path_glob": "**",
                "adrs": [],
                "humans": [default_human],
                "agents_allowed": default_agents,
                "notes": (
                    "Fallback entry — no ADR/spec frontmatter discovered during bootstrap. Manual refinement required."
                ),
            }
        ]

    header = (
        "# MAINTAINERS — Phase 1C bootstrap (ADR-042 §6 + Appendix A.3)\n"
        "#\n"
        "# Reverse-ownership registry: maps repo paths to the ADRs and humans\n"
        "# that govern them, plus the AI runtimes allowed to edit. Consumed by:\n"
        "#   - scripts/audit/closure.py (bidirectional MAINTAINERS <-> governs)\n"
        "#   - Agent authorization checks across the QA pipeline (Phase 1B+)\n"
        "#\n"
        "# Validated by scieasy.qa.schemas.maintainers.Maintainers\n"
        "# (ADR-042 §6.2 lines 949-982). Glob semantics: ADR-042 §6.4.\n"
        "# Multi-match resolution: ADR-042 §6.5 (most-specific wins; tie-break\n"
        "# by entry order).\n"
        "#\n"
        "# Re-bootstrap: ``python scripts/migrate/bootstrap_maintainers.py``.\n"
        "# Re-runs OVERWRITE this file; human-curated additions should live\n"
        "# in a separate review pass before the Phase 2 ratchet flips.\n"
    )

    # Subclass disables YAML anchors/aliases so each entry stands alone —
    # important because the file is read by humans, diffed during reviews,
    # and consumed by tools that do not need anchor support.
    class _NoAliasDumper(yaml.SafeDumper):
        def ignore_aliases(self, data: Any) -> bool:
            return True

    body = yaml.dump(
        {"version": 1, "entries": entries},
        Dumper=_NoAliasDumper,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    return header + body


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns POSIX exit status."""
    parser = argparse.ArgumentParser(description="Bootstrap the MAINTAINERS file from ADR governs (ADR-042 §A.3).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the SciEasy repo root (default: current working directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path for MAINTAINERS (default: <repo-root>/MAINTAINERS). "
            "Pass ``-`` to print to stdout instead of writing."
        ),
    )
    parser.add_argument(
        "--default-human",
        type=str,
        default="@jiazhenz026",
        help="GitHub handle used as default human owner (with @ prefix).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write; print the rendered text to stdout and exit 0 "
            "(or exit 1 if the rendered text fails schema validation)."
        ),
    )
    args = parser.parse_args(argv)

    rendered = render_maintainers(repo_root=args.repo_root, default_human=args.default_human)

    # Validate before writing — fail loudly if the schema would reject.
    try:
        from scieasy.qa.schemas.maintainers import Maintainers
    except ImportError as exc:  # pragma: no cover — defensive only
        print(f"ERROR: cannot import scieasy.qa.schemas.maintainers: {exc}", file=sys.stderr)
        return 2

    parsed = yaml.safe_load(rendered)
    try:
        Maintainers(**parsed)
    except Exception as exc:
        print(f"ERROR: rendered MAINTAINERS fails schema validation: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print(rendered, end="")
        return 0

    if args.output is None:
        output_path = args.repo_root / "MAINTAINERS"
    elif str(args.output) == "-":
        print(rendered, end="")
        return 0
    else:
        output_path = args.output

    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path} ({len(rendered)} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
