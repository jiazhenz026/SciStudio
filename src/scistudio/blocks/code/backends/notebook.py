"""Backend that runs Jupyter notebook Code Block scripts.

A Code Block whose script is a ``.ipynb`` runs the whole notebook through
``nbconvert``. ADR-054 FR-040 adds one thing to that and changes nothing else:
a **cell selection**. A block packaged from an exploration notebook must run the
backward slice of the notebook's declared outputs and nothing else, so this
backend materialises the selected cells — in the notebook's written order — as
the run-scoped notebook ``nbconvert`` executes, and leaves the packaged copy on
disk untouched.

The selection is optional and arrives as a hint on the Code Block's
``environment`` mapping under :data:`NOTEBOOK_CELL_SELECTION_KEY`. A Code Block
that carries none behaves exactly as it did before: the whole notebook is
copied and executed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    codeblock_exchange_env,
    register_codeblock_backend,
    run_codeblock_process,
)
from scistudio.blocks.code.config import CodeBlockConfig, CodeBlockConfigError
from scistudio.blocks.code.exchange import safe_exchange_name
from scistudio.blocks.code.interpreters import InterpreterResolutionError, ResolvedInterpreter
from scistudio.stability import provisional

_EXECUTED_NOTEBOOK_PORT = "_executed_notebook"
_NOTEBOOK_MIME_TYPE = "application/x-ipynb+json"

#: Key under the Code Block's ``environment`` mapping that carries the ordered
#: cell ids this run must execute (ADR-054 FR-040).
#:
#: A packaged notebook block writes it; every other Code Block leaves it out and
#: is unaffected. The value is a sequence of nbformat 4.5 cell ids; the order
#: written here is not the execution order — the notebook's own written order
#: is (FR-040), so a caller cannot reorder a notebook by permuting this list.
NOTEBOOK_CELL_SELECTION_KEY = "notebook_cell_selection"

#: Environment variable set for a run that carries a cell selection.
#:
#: The notebook helpers read it to choose their packaged-mode backend — reading
#: and writing the exchange folders — over the session-mode one that talks to a
#: live kernel. A notebook run with no selection never sees it.
NOTEBOOK_MODE_ENV_VAR = "SCISTUDIO_NOTEBOOK_MODE"

#: Value of :data:`NOTEBOOK_MODE_ENV_VAR` for a packaged run.
PACKAGED_NOTEBOOK_MODE = "packaged"


@provisional(since="0.3.1")
class NotebookCodeBlockBackend:
    """Run a Code Block script that is a Jupyter notebook (``.ipynb``).

    This backend executes a notebook end to end with Jupyter ``nbconvert`` and
    saves the run notebook as an output artifact, so you can use a notebook as a
    workflow step. It needs Jupyter ``nbconvert`` available, either auto-detected
    on the system path or pinned through the Code Block's ``interpreter_mode`` /
    ``interpreter_path`` settings. The notebook's kernel launches from the
    project root and reads and writes the declared input and output folders.

    Args:
        executable_locator: Optional function that finds an executable by name
            (defaults to :func:`shutil.which`). Mainly useful for testing.

    Example:
        >>> backend = NotebookCodeBlockBackend()
        >>> backend.supports(Path("report.ipynb"), config)
        True
    """

    name = "notebook"
    """Backend identifier used in the registry and provenance records."""
    extensions = frozenset({".ipynb"})
    """File extensions this backend handles (Jupyter notebooks)."""

    def __init__(self, executable_locator: Callable[[str], str | None] | None = None) -> None:
        self._executable_locator = executable_locator or shutil.which

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        """Return whether *script_path* is a notebook this backend runs."""
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        """Resolve ``nbconvert`` and build the command that executes the notebook."""
        executable = self._resolve_executable(context.config)
        target = executed_notebook_path(context)
        # ADR-041 §4: nbconvert launches the kernel from the configured
        # working directory (default ``"."`` = project root). Previously
        # ``--ExecutePreprocessor.cwd`` and the interpreter ``working_directory``
        # were set to ``context.exchange_dir``, which broke notebooks that
        # read project-relative paths like ``Path("data/raw")``. The
        # exchange dir remains the materialisation target for declared
        # ports.
        script_cwd = _resolve_existing_working_directory(context)
        argv = _nbconvert_argv(
            executable,
            source_notebook=target,
            execution_cwd=script_cwd,
            timeout_seconds=context.config.timeout_seconds,
        )
        version, warnings = _probe_nbconvert_version(executable)
        return ResolvedInterpreter(
            family="notebook",
            executable=executable,
            argv=argv,
            working_directory=script_cwd.as_posix(),
            environment=notebook_run_environment(context),
            version=version,
            warnings=warnings,
        )

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        """Execute the notebook in place and return the finished process.

        The notebook is copied to the framework-managed executed-notebook path
        and run there, so the script on disk is never modified. When the run
        carries a cell selection (ADR-054 FR-040) the copy is the slice rather
        than the whole notebook, which is what makes a packaged block run the
        cells the dependency graph selected and nothing else.
        """
        target = executed_notebook_path(context)
        target.parent.mkdir(parents=True, exist_ok=True)
        selection = notebook_cell_selection(context.environment_config)
        if selection is None:
            shutil.copy2(context.script_path, target)
        else:
            document = _read_notebook_document(context.script_path)
            target.write_text(
                json.dumps(select_notebook_cells(document, selection), indent=1) + "\n",
                encoding="utf-8",
            )
        # ADR-041 §4: keep the subprocess cwd aligned with the resolved
        # working directory used by ``resolve()`` so nbconvert and its
        # spawned kernel share the same launch directory.
        script_cwd = _resolve_existing_working_directory(context)
        return run_codeblock_process(
            argv=interpreter.argv,
            cwd=script_cwd,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )

    def _resolve_executable(self, config: CodeBlockConfig) -> str:
        if config.interpreter_mode == "existing":
            if not config.interpreter_path:
                raise InterpreterResolutionError(
                    "Notebook CodeBlock interpreter_mode='existing' requires interpreter_path."
                )
            return _resolve_configured_executable(config.interpreter_path)

        if config.interpreter_mode != "auto":
            raise InterpreterResolutionError(f"Unsupported notebook interpreter mode: {config.interpreter_mode}")

        discovered_nbconvert = self._executable_locator("jupyter-nbconvert")
        if discovered_nbconvert:
            return str(Path(discovered_nbconvert).resolve())

        discovered_jupyter = self._executable_locator("jupyter")
        if discovered_jupyter and _jupyter_has_nbconvert(discovered_jupyter):
            return str(Path(discovered_jupyter).resolve())
        raise InterpreterResolutionError(
            "Notebook CodeBlock backend requires Jupyter nbconvert. Install the optional Jupyter tooling "
            "or set interpreter_mode='existing' with an executable path."
        )


@provisional(since="0.3.4")
def notebook_run_environment(context: CodeBlockRuntimeContext) -> dict[str, str]:
    """Return the environment variables one notebook run is launched with.

    A notebook exchanges data through the same folders every other Code Block
    script does, so it gets the same ``SCISTUDIO_*`` variables the Python and R
    backends inject. ADR-054 FR-040's packaged mode is what made the omission
    visible: a packaged notebook reads its declared input ports and writes its
    declared output ports, and it locates both through these variables. Adding
    them is additive — an existing notebook that ignores them runs as before.

    A run that carries a cell selection is additionally marked packaged, which
    is how the notebook helpers choose their file-exchange backend over the
    session-mode one that talks to a live kernel.

    Args:
        context: The run's context.

    Returns:
        The environment delta layered over the current process environment.
    """
    environment = {
        **_environment_delta(context.environment_config),
        **codeblock_exchange_env(context),
    }
    if notebook_cell_selection(context.environment_config) is not None:
        environment[NOTEBOOK_MODE_ENV_VAR] = PACKAGED_NOTEBOOK_MODE
    return environment


@provisional(since="0.3.4")
def notebook_cell_selection(environment_config: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Return the ordered cell ids this run must execute, or ``None`` for all of them.

    ADR-054 FR-040. The selection is read from the Code Block's ``environment``
    hints under :data:`NOTEBOOK_CELL_SELECTION_KEY`. ``None`` means the config
    carries no selection at all and the whole notebook runs — the behaviour of
    every Code Block written before packaging existed.

    An **empty** selection is not the same thing as an absent one: it says "run
    no cells", which is never what a packaged block wants, so it is rejected
    rather than silently widened to the whole notebook.

    Args:
        environment_config: The run's interpreter and environment hints.

    Returns:
        The selected cell ids as written in the config, or ``None``.

    Raises:
        CodeBlockConfigError: If the value is present but is not a list of
            non-empty strings, or is an empty list.
    """
    raw = environment_config.get(NOTEBOOK_CELL_SELECTION_KEY)
    if raw is None:
        return None
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise CodeBlockConfigError(
            f"{NOTEBOOK_CELL_SELECTION_KEY} must be a list of notebook cell ids, got {type(raw).__name__}."
        )
    selection: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise CodeBlockConfigError(
                f"{NOTEBOOK_CELL_SELECTION_KEY} must contain non-empty cell id strings, got {entry!r}."
            )
        selection.append(entry)
    if not selection:
        raise CodeBlockConfigError(
            f"{NOTEBOOK_CELL_SELECTION_KEY} is empty, which would run no cells at all. "
            f"Omit the key to run the whole notebook."
        )
    return tuple(selection)


@provisional(since="0.3.4")
def select_notebook_cells(document: Mapping[str, Any], selection: Sequence[str]) -> dict[str, Any]:
    """Return *document* reduced to *selection*, in the notebook's written order.

    ADR-054 FR-040. Everything outside the cell list — the notebook metadata,
    the kernelspec, the nbformat version — is carried through unchanged, because
    the slice has to launch the same kernel the whole notebook would.

    Written order is the notebook's, not the caller's: the returned cells appear
    in the order the file has them regardless of the order *selection* lists
    them, so a selection can never reorder a notebook. That matters because the
    dependency graph's slice is only correct under written order.

    Args:
        document: A parsed ``.ipynb`` mapping.
        selection: The cell ids to keep. Duplicates are ignored.

    Returns:
        A new notebook mapping holding only the selected cells.

    Raises:
        CodeBlockConfigError: If the document has no cell list, or a selected
            cell id is not in it — naming the ids that are missing, because a
            selection that silently loses a cell would run a different program
            than the one that was packaged.
    """
    cells = document.get("cells")
    if not isinstance(cells, list):
        raise CodeBlockConfigError("Notebook has no 'cells' list; it cannot be sliced for a packaged run.")

    wanted = set(selection)
    kept = [cell for cell in cells if isinstance(cell, dict) and cell.get("id") in wanted]
    found = {cell.get("id") for cell in kept}
    missing = [cell_id for cell_id in dict.fromkeys(selection) if cell_id not in found]
    if missing:
        raise CodeBlockConfigError(
            f"Notebook cell selection names {len(missing)} cell(s) the notebook does not contain: {', '.join(missing)}."
        )

    sliced = dict(document)
    sliced["cells"] = kept
    return sliced


def _read_notebook_document(path: Path) -> dict[str, Any]:
    """Parse a ``.ipynb`` into its JSON mapping, or raise a configuration error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CodeBlockConfigError(f"Could not read the notebook at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CodeBlockConfigError(f"Notebook at {path} is not a JSON object.")
    return payload


def executed_notebook_path(context: CodeBlockRuntimeContext) -> Path:
    """Return the framework-managed executed notebook artifact path."""

    folder = _executed_notebook_output_dir(context)
    return folder / f"{context.script_path.stem}.executed.ipynb"


def _executed_notebook_output_dir(context: CodeBlockRuntimeContext) -> Path:
    # TODO(#1245): Let backends inject framework-managed CodeBlock outputs before
    #   port planning so `_executed_notebook` does not need a declared port to be
    #   returned from CodeBlock.run().
    #   Out of scope per ADR-041 section 7 and docs/specs/adr-041-codeblock-v2.md AC-011.
    #   Followup: https://github.com/zjzcpj/SciStudio/issues/1245.
    for output in context.config.outputs:
        if output.name == _EXECUTED_NOTEBOOK_PORT and output.exchange_folder:
            folder = output.exchange_folder.replace("\\", "/").strip("/")
            if folder.startswith("outputs/"):
                folder = folder[len("outputs/") :]
            if folder:
                return context.exchange_dir / "outputs" / safe_exchange_name(folder)
    return context.exchange_dir / "outputs" / safe_exchange_name(_EXECUTED_NOTEBOOK_PORT)


def _resolve_configured_executable(raw_executable: str) -> str:
    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise InterpreterResolutionError("Notebook interpreter executable must not be empty.")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise InterpreterResolutionError(f"Notebook interpreter executable not found: {raw_executable}")
        return str(resolved)

    discovered = shutil.which(raw_executable)
    if discovered is None:
        raise InterpreterResolutionError(f"Notebook interpreter executable not found on PATH: {raw_executable}")
    return str(Path(discovered).resolve())


def _nbconvert_argv(
    executable: str,
    *,
    source_notebook: Path,
    execution_cwd: Path,
    timeout_seconds: float | None,
) -> list[str]:
    executable_name = Path(executable).name.lower()
    argv = [executable]
    if "nbconvert" not in executable_name:
        argv.append("nbconvert")
    argv.extend(
        [
            "--to",
            "notebook",
            "--execute",
            "--inplace",
            str(source_notebook),
            f"--ExecutePreprocessor.cwd={execution_cwd}",
        ]
    )
    if timeout_seconds is not None:
        argv.append(f"--ExecutePreprocessor.timeout={max(1, int(timeout_seconds))}")
    return argv


def _probe_nbconvert_version(executable: str) -> tuple[str | None, list[str]]:
    argv = (
        [executable, "--version"]
        if "nbconvert" in Path(executable).name.lower()
        else [executable, "nbconvert", "--version"]
    )
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture notebook interpreter version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"Notebook interpreter version command exited with {completed.returncode}"]
    return output or None, []


def _jupyter_has_nbconvert(executable: str) -> bool:
    version, _warnings = _probe_nbconvert_version(executable)
    return version is not None


def _environment_delta(environment_config: Mapping[str, object]) -> dict[str, str]:
    raw_delta = (
        environment_config.get("environment_variables")
        or environment_config.get("env")
        or environment_config.get("environment")
        or {}
    )
    if not isinstance(raw_delta, Mapping):
        raise InterpreterResolutionError("Notebook environment variables must be a mapping.")
    return {str(key): str(value) for key, value in raw_delta.items() if os.environ.get(str(key)) != str(value)}


def _resolve_existing_working_directory(context: CodeBlockRuntimeContext) -> Path:
    """Resolve ``working_directory`` and require it to exist as a directory.

    :meth:`CodeBlockConfig.resolve_working_directory` intentionally allows
    paths that don't yet exist, but :func:`subprocess.run` / nbconvert
    raise low-level ``FileNotFoundError`` when ``cwd`` doesn't exist.
    Surface a clear :class:`CodeBlockConfigError` instead so the failure
    points at the misconfigured field, not at a Python subprocess
    internal. Codex P2 review of PR #1392.
    """
    script_cwd = context.config.resolve_working_directory(context.project_dir)
    if not script_cwd.exists():
        raise CodeBlockConfigError(
            f"working_directory does not exist: {script_cwd} "
            f"(resolved from {context.config.working_directory!r} under project root "
            f"{context.project_dir!r})"
        )
    if not script_cwd.is_dir():
        raise CodeBlockConfigError(f"working_directory must be a directory, not a file: {script_cwd}")
    return script_cwd


def register() -> None:
    """Register the notebook backend with the shared CodeBlock runtime."""

    register_codeblock_backend(NotebookCodeBlockBackend(), replace=True)
