"""Execute a fixture notebook, or one slice of it, in a fresh process.

This is the executing half of the T-010 differential harness that spec §4.4
describes. ``tests/explore/test_analysis_differential.py`` never runs notebook
code itself: it spawns this script twice per fixture, once for the whole
notebook and once for the backward slice, and compares the declared outputs.

The two modes:

``--mode full``
    Run every enabled cell in written order. Before and after each cell the
    whole module namespace is fingerprinted and
    :func:`~scistudio.explore.fingerprint.compare_namespaces` turns the two
    snapshots into the cell's observed changed set. Those observations are what
    the test feeds back into ``build_graph`` so the slice is chosen from what
    the cells were *seen* to do rather than from what their source shows.

``--mode slice --cells c1,c2,...``
    Run only the named cells, in written order, on a namespace that has never
    seen the others. No fingerprinting: the point of this run is the outputs.

Why a subprocess at all: a notebook's cells bind module-scope names, import
whatever they like, and mutate global state. Running them inside the pytest
process would let one fixture's ``import numpy`` decide whether another
fixture's fingerprint takes the numpy path, and would let a leaked name from
the full run stand in for one the slice omitted — which is precisely the
failure the differential test exists to detect. A fresh interpreter per run is
the only namespace that is honestly cold.

**Magic lines are stripped only when the cell does not compile without them.**
A real kernel tokenises before it decides what a magic is, so an operator that
a formatter wrapped onto its own line -- ``value = (\\n    total\\n    % count\\n)``
is what ``black`` and ``ruff format`` produce -- is ordinary Python to the
kernel and is executed as written. Stripping it unconditionally here would hide
from the differential test exactly the reads the analysis loses by stripping it,
so this runner compiles first and strips only on failure.

Output is one JSON object on stdout, fenced by :data:`RESULT_BEGIN` and
:data:`RESULT_END` so that anything a cell prints cannot be mistaken for it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

RESULT_BEGIN = "<<<SCISTUDIO-DIFFERENTIAL-RESULT"
RESULT_END = "SCISTUDIO-DIFFERENTIAL-RESULT>>>"

_MAGIC_LINE = re.compile(r"^[ \t]*[%!]")


class _OutputRecorder:
    """Stands in for ``scistudio.output`` while a fixture notebook runs.

    ``scistudio.output`` is the block runtime's declaration call. The runtime
    that provides it belongs to the explore-session and interactive-block specs,
    and does not exist yet; the fixtures import ``scistudio`` and call it exactly
    as a person's notebook would, and this recorder is bound onto the module for
    the life of the subprocess. What the differential test needs from an output
    call is only *what value was declared under what name*, so each argument is
    described at the moment of the call.

    Binding it onto the real module rather than injecting a fake name into the
    namespace matters twice over: the fixture notebooks stay ordinary Python that
    a linter can read, and ``scistudio`` becomes a name the notebook itself binds,
    so the graph resolves the output cell's read of it like any other.
    """

    def __init__(self) -> None:
        self.declared: dict[str, Any] = {}

    def install(self) -> None:
        import scistudio

        scistudio.output = self.output  # type: ignore[attr-defined]

    def output(self, **values: object) -> None:
        for name, value in values.items():
            self.declared[name] = describe(value)


def describe(value: object) -> Any:
    """Render *value* as something two processes can compare exactly.

    Frames and series go through CSV, arrays through ``tolist`` beside their
    dtype and shape, and everything else through ``repr``. All three are
    deterministic for a given value and carry enough of it that a slice which
    skipped a mutating cell cannot come out looking the same.
    """
    pandas = sys.modules.get("pandas")
    numpy = sys.modules.get("numpy")
    if pandas is not None and isinstance(value, pandas.DataFrame):
        return {"kind": "frame", "csv": value.to_csv(), "dtypes": [str(d) for d in value.dtypes]}
    if pandas is not None and isinstance(value, pandas.Series):
        return {"kind": "series", "csv": value.to_csv(), "dtype": str(value.dtype)}
    if numpy is not None and isinstance(value, numpy.ndarray):
        return {"kind": "array", "dtype": str(value.dtype), "shape": list(value.shape), "values": value.tolist()}
    return {"kind": "value", "repr": repr(value)}


def load_cells(path: pathlib.Path) -> list[dict[str, Any]]:
    """Return the code cells of *path* as ``{id, source, enabled}`` in written order."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cells: list[dict[str, Any]] = []
    for index, cell in enumerate(payload["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = cell["source"]
        cells.append(
            {
                "id": cell.get("id") or f"cell-{index}",
                "source": "".join(source) if isinstance(source, list) else source,
                "enabled": bool(cell.get("metadata", {}).get("scistudio", {}).get("enabled", True)),
            }
        )
    return cells


def compile_cell(source: str, cell_id: str) -> Any:
    """Compile *source*, stripping magic and shell lines only if it will not compile.

    See the module docstring: a kernel tokenises before it decides, so a line
    that merely *looks* like a magic inside otherwise valid Python is run as
    written.
    """
    filename = f"<cell {cell_id}>"
    try:
        return compile(source, filename, "exec")
    except SyntaxError:
        stripped = "\n".join("" if _MAGIC_LINE.match(line) else line for line in source.splitlines())
        return compile(stripped, filename, "exec")


def snapshot(namespace: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint every top-level name the cells own (A-007's kernel half).

    Dunder names are the interpreter's, not the notebook's, and
    :func:`compare_namespaces` reports on exactly what it is given, so the filter
    belongs here — as its docstring says the caller's does.
    """
    from scistudio.explore.fingerprint import fingerprint

    return {name: fingerprint(value) for name, value in namespace.items() if not name.startswith("__")}


def run(path: pathlib.Path, *, observe: bool, only: list[str] | None) -> dict[str, Any]:
    from scistudio.explore.dependency_analysis import source_hash
    from scistudio.explore.fingerprint import compare_namespaces

    recorder = _OutputRecorder()
    recorder.install()
    namespace: dict[str, Any] = {"__name__": "__main__"}
    observations: dict[str, dict[str, Any]] = {}
    executed: list[str] = []

    cells = [cell for cell in load_cells(path) if cell["enabled"]]
    if only is not None:
        wanted = set(only)
        cells = [cell for cell in cells if cell["id"] in wanted]

    for cell in cells:
        code = compile_cell(cell["source"], cell["id"])
        before = snapshot(namespace) if observe else {}
        exec(code, namespace)
        executed.append(cell["id"])
        if not observe:
            continue
        after = snapshot(namespace)
        change = compare_namespaces(
            before,
            after,
            cell_id=cell["id"],
            source_hash=source_hash(cell["source"]),
        )
        observations[cell["id"]] = {
            "changed_names": sorted(change.changed_names),
            "unobservable_names": sorted(change.unobservable_names),
            "source_hash": change.source_hash,
        }

    return {"executed": executed, "observations": observations, "outputs": recorder.declared}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook")
    parser.add_argument("--mode", choices=("full", "slice"), required=True)
    parser.add_argument("--cells", default="")
    args = parser.parse_args(argv)

    only = [item for item in args.cells.split(",") if item] if args.mode == "slice" else None
    result: dict[str, Any]
    try:
        result = run(pathlib.Path(args.notebook), observe=args.mode == "full", only=only)
        result["error"] = None
    except BaseException as error:
        result = {
            "executed": [],
            "observations": {},
            "outputs": {},
            "error": f"{type(error).__name__}: {error}",
        }
    print(RESULT_BEGIN)
    print(json.dumps(result, sort_keys=True))
    print(RESULT_END)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
