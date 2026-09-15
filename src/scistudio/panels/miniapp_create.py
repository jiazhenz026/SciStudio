"""Creating a MiniApp: the template directory, the agent's brief, and the sources."""
# Creating a MiniApp: the template directory, the agent's brief, and the sources.
#
# ADR-054 MiniApp FR-024/FR-026/FR-027/FR-034/FR-036. Everything here is the
# filesystem and data half of the two create routes in
# :mod:`scistudio.api.routes.panels`; the availability check and the agent
# session stay in the route, so this module imports nothing from
# :mod:`scistudio.api`.
#
# The order the route runs these in is normative and is stated where it is
# enforced (``create_miniapp`` in the route module). This module's own promise is
# narrower: nothing it writes is half-written, and an id it hands back was free
# at the moment it claimed the directory.

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.miniapp import _check_type, _output_ref
from scistudio.panels.targets import FrozenTarget, PanelError, freeze_target

#: The files a new MiniApp is created from (FR-024). Shipped as real files
#: rather than strings in this module so the page the owner reviews is read and
#: edited as a page.
TEMPLATE_DIR = Path(__file__).resolve().parent / "template"

#: Project-relative directory holding MiniApp session briefs (FR-024). Under
#: ``.scistudio/`` so the default project ``.gitignore`` excludes it, as the
#: Bring In My Work briefs are.
BRIEF_DIR_PARTS = (".scistudio", "miniapps")

#: The project tier's panel directory name. The bare literal
#: :func:`scistudio.core.dropins.panel_scan_dirs` uses; there is no shared
#: constant to import yet.
PANELS_DIR_NAME = "panels"

#: Type names a panel descriptor reserves for core panels. A MiniApp claiming
#: one would never load, so the route refuses the source instead of writing a
#: directory that discovery rejects (``panels/descriptor.py``).
CORE_SENTINEL_TYPES = ("DataObject", "Collection", "PlotArtifact")

_ID_SEGMENT = re.compile(r"[a-z][a-z0-9_]*\Z")
_MAX_ID_ATTEMPTS = 1000


@dataclass(frozen=True)
class SourceCandidate:
    """One block output a MiniApp could open on."""

    # One block output a MiniApp could open on (FR-034).

    workflow_id: str
    workflow_name: str
    block_id: str
    block_name: str
    port: str
    type: str
    frozen: FrozenTarget

    def as_dict(self) -> dict[str, str]:
        """The wire shape of ``GET /api/panels/miniapps/{id}/sources``."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "block_id": self.block_id,
            "block_name": self.block_name,
            "port": self.port,
            "type": self.type,
        }


def target_type_name(frozen: FrozenTarget) -> str:
    """Return the declared-type spelling of an output, as ``panel.json`` writes it."""
    if frozen.collection is not None:
        item_type = str(frozen.collection.get("item_type") or "")
        return f"Collection[{item_type}]" if item_type else "Collection"
    return str(frozen.target.recorded_type or "")


def _workflow_name(scheduler: Any, workflow_id: str) -> str:
    definition = getattr(scheduler, "_workflow", None)
    metadata = getattr(definition, "metadata", None)
    if isinstance(metadata, dict):
        name = metadata.get("name")
        if isinstance(name, str) and name:
            return name
    declared = getattr(definition, "id", "")
    return declared if isinstance(declared, str) and declared else workflow_id


def _block_name(scheduler: Any, block_id: str) -> str:
    definition = getattr(scheduler, "_workflow", None)
    for node in getattr(definition, "nodes", []) or []:
        if getattr(node, "id", None) != block_id:
            continue
        config = getattr(node, "config", None)
        if isinstance(config, dict):
            for key in ("name", "label", "title"):
                value = config.get(key)
                if isinstance(value, str) and value:
                    return value
    return block_id


def _is_done(state: Any) -> bool:
    return str(getattr(state, "value", state)).lower() == "done"


def iter_source_candidates(runtime: Any) -> Iterator[SourceCandidate]:
    """Yield every block output of a latest successful run that can be opened.

    The same three dictionaries :func:`scistudio.panels.miniapp.resolve_source`
    reads for one source, walked for all of them. An output that cannot be
    frozen — its run's artifacts were reclaimed, or it never resolved to a data
    reference — is skipped rather than failing the listing. The picker offers
    only outputs that can be opened now.
    """
    from scistudio.panels.miniapp import run_belongs_to_project

    for workflow_id, run in list(getattr(runtime, "workflow_runs", {}).items()):
        if not run_belongs_to_project(runtime, run):
            continue
        scheduler = getattr(run, "scheduler", None)
        if scheduler is None:
            continue
        states = getattr(scheduler, "_block_states", {}) or {}
        outputs = getattr(scheduler, "_block_outputs", {}) or {}
        for block_id, ports in list(outputs.items()):
            if not isinstance(ports, dict):
                continue
            state = states.get(block_id)
            if state is not None and not _is_done(state):
                continue
            for port, value in list(ports.items()):
                frozen = _freeze_output(runtime, value)
                if frozen is None:
                    continue
                yield SourceCandidate(
                    workflow_id=str(workflow_id),
                    workflow_name=_workflow_name(scheduler, str(workflow_id)),
                    block_id=str(block_id),
                    block_name=_block_name(scheduler, str(block_id)),
                    port=str(port),
                    type=target_type_name(frozen),
                    frozen=frozen,
                )


def _freeze_output(runtime: Any, value: Any) -> FrozenTarget | None:
    try:
        frozen = freeze_target(runtime, _output_ref(runtime, value))
        frozen.validate(runtime)
    except (PanelError, ValueError, TypeError, KeyError, OSError):
        return None
    return frozen


def matching_sources(runtime: Any, panel: PanelDescriptor) -> list[dict[str, str]]:
    """Return the sources whose type satisfies *panel*'s declared type."""
    # Return the sources whose type satisfies *panel*'s declared type (FR-034).
    #
    # Type matching is not re-derived here: ``_check_type`` is the rule the
    # context create enforces, so a source this listing offers is one that opens.
    if not panel.types:
        return []
    result: list[dict[str, str]] = []
    for candidate in iter_source_candidates(runtime):
        try:
            _check_type(panel, candidate.frozen)
        except PanelError:
            continue
        result.append(candidate.as_dict())
    return result


def slugify(text: str, *, fallback: str = "miniapp") -> str:
    """Return a panel-id segment derived from *text*, or *fallback*.

    Panel ids are lowercase dotted segments and must equal their directory
    name (``panels/descriptor.py``), so a display name becomes an id by
    lowercasing, replacing everything else with an underscore, and making sure
    the first character is a letter.
    """
    lowered = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    if not lowered:
        return fallback
    if not lowered[0].isalpha():
        lowered = f"m_{lowered}"
    lowered = lowered[:48].rstrip("_")
    return lowered if _ID_SEGMENT.fullmatch(lowered) else fallback


def allocate_panel_id(panels_dir: Path, base: str) -> str:
    """Return *base*, or the next free ``<base>_<n>``."""
    # Return *base*, or the next free ``<base>_<n>`` (FR-024).
    #
    # Only the name is decided here; the directory is claimed by
    # :func:`create_from_template`, which creates it exclusively and asks again
    # if another writer won the race.
    if not (panels_dir / base).exists():
        return base
    for index in range(2, _MAX_ID_ATTEMPTS):
        candidate = f"{base}_{index}"
        if not (panels_dir / candidate).exists():
            return candidate
    raise PanelError(409, "id_exhausted", f"Too many MiniApps named like {base!r} already exist")


def create_from_template(
    project_dir: Path,
    *,
    base_id: str,
    name: str,
    description: str,
    type_name: str,
) -> tuple[str, Path]:
    """Create ``<project>/panels/<id>/`` from the template; return ``(id, dir)``.

    The directory is created with ``mkdir`` (not ``exist_ok``) so the
    filesystem decides the collision: two create requests in the same second
    cannot both believe they own one id. A loser retries with the next free id
    rather than writing into a directory it does not own.
    """
    panels_dir = project_dir / PANELS_DIR_NAME
    panels_dir.mkdir(parents=True, exist_ok=True)
    for _attempt in range(_MAX_ID_ATTEMPTS):
        panel_id = allocate_panel_id(panels_dir, base_id)
        directory = panels_dir / panel_id
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        _write_template(directory, panel_id=panel_id, name=name, description=description, type_name=type_name)
        return panel_id, directory
    raise PanelError(409, "id_exhausted", f"Too many MiniApps named like {base_id!r} already exist")


def _write_template(directory: Path, *, panel_id: str, name: str, description: str, type_name: str) -> None:
    """Write the three template files into an already-claimed directory."""
    manifest = json.loads((TEMPLATE_DIR / "panel.json").read_text(encoding="utf-8"))
    manifest["id"] = panel_id
    manifest["name"] = name
    manifest["description"] = description
    manifest["types"] = [type_name]
    page = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{scistudio:name}}", _html_text(name))
    page = page.replace("{{scistudio:request}}", _html_text(description))
    _write_text(directory / "panel.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    _write_text(directory / "index.html", page)
    shutil.copyfile(TEMPLATE_DIR / "panel.py", directory / "panel.py")


def _html_text(value: str) -> str:
    """Escape *value* for a text position in the template page.

    The user's own words go into the page, so they are escaped rather than
    trusted — a request mentioning a tag is text about a tag, not markup.
    """
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_brief(project_dir: Path, text: str) -> Path:
    """Write one MiniApp brief under ``.scistudio/miniapps/`` and return its path.

    Mode ``"x"``, then flush and fsync before the handle closes, for the reason
    the Bring In My Work brief does the same: the agent is about to be pointed
    at this file by name, and a half-written brief is an unrecoverable session.
    """
    brief_dir = project_dir.joinpath(*BRIEF_DIR_PARTS)
    brief_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    brief_path = brief_dir / f"{stamp}-{uuid.uuid4().hex[:8]}.md"
    with brief_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return brief_path


def opening_message(brief_relpath: str) -> str:
    """The single line the user sees when the session starts."""
    return f"Read the file {brief_relpath} and follow the instructions in it."


def compose_create_brief(
    *,
    panel_id: str,
    directory_relpath: str,
    request: str,
    type_name: str,
    source: dict[str, str],
) -> str:
    """The instructions the MiniApp-writing session is pointed at."""
    # The instructions the MiniApp-writing session is pointed at (FR-027).
    return f"""# Write the MiniApp `{panel_id}`

A user asked SciStudio for a small app to look at one piece of their data.
SciStudio has already created the directory and opened it in a tab, so the
user is watching a template page while you work. Replace it.

## What the user asked for

{request.strip()}

## What you are working on

- MiniApp directory: `{directory_relpath}`
- MiniApp id: `{panel_id}`
- Declared type: `{type_name}`
- Opened on: workflow `{source.get("workflow_id", "")}`, block
  `{source.get("block_id", "")}`, port `{source.get("port", "")}`

## How to do it

1. Follow the `scistudio-write-miniapp` skill. It is the MiniApp form: what
   `panel.json` declares, how the page talks to the SDK (`read`, `call`,
   `save`), what `panel.py` may do, and what the frame does and does not allow.
2. Write only inside `{directory_relpath}`, unless the user asks you for
   something else. This is their project; a MiniApp leaves only itself behind.
3. Keep the `id`, `contexts`, and `types` that are already in `panel.json`.
   The tab is open on that id and that type right now, and changing either
   closes the user's tab underneath them. If the type is wrong for what they
   asked for, say so instead of editing it.
4. Put the work that is slow in `setup(data)` in `panel.py`, once, and answer
   the page from what it loaded. `data` is the output above, already
   reconstructed as a SciStudio data object.
5. Run `validate_panel` on the directory before you finish, and fix what it
   reports. The tab reloads every time you save, so the user sees each step.

When it works, tell the user in one or two sentences what they can now do with
it — not how you built it.
"""


def compose_convert_brief(
    *,
    panel_id: str,
    directory_relpath: str,
    outputs: list[dict[str, str]],
    note: str | None,
) -> str:
    """The instructions the Convert-to-block session is pointed at."""
    # The instructions the Convert-to-block session is pointed at (FR-036).
    listed = "\n".join(
        f"- `{o.get('name', '')}` on port `{o.get('port', '')}`, type `{o.get('type', '')}`" for o in outputs
    )
    extra = f"\n## What the user added\n\n{note.strip()}\n" if note and note.strip() else ""
    return f"""# Turn the MiniApp `{panel_id}` into an interactive block

A user explored their data in a MiniApp and settled on what they want. They now
want the workflow to ask them for it on every run, as an interactive block.

## The MiniApp

`{directory_relpath}`. Read it — its `panel.json`, its page, and its
`panel.py` — to learn what the user was actually deciding. Leave it exactly as
it is: it is still theirs to open, and this conversion does not replace it.

## The outputs the block must produce

{listed or "- (the user named none; ask them)"}
{extra}
## How to do it

1. Follow the `scistudio-write-block` skill and write the block into this
   project's `blocks/` directory.
2. The block is an ADR-051 interactive block, so it has three obligations:
   - `prepare_prompt` builds a self-contained view of what the user has to
     decide, from the block's inputs. It does the reading; the interaction
     never reaches back into the run.
   - exactly one decision is written back from that interaction.
   - `run` computes the outputs above from the inputs and that decision, and
     is what the workflow re-runs.
3. A MiniApp is exploratory and a block is reproducible. Anything the MiniApp
   chose interactively that is not the one decision has to become block
   configuration with a stated default, not a hidden constant.
4. Validate the block and tell the user how to add it to a workflow.
"""


__all__ = [
    "BRIEF_DIR_PARTS",
    "CORE_SENTINEL_TYPES",
    "PANELS_DIR_NAME",
    "TEMPLATE_DIR",
    "SourceCandidate",
    "allocate_panel_id",
    "compose_convert_brief",
    "compose_create_brief",
    "create_from_template",
    "iter_source_candidates",
    "matching_sources",
    "opening_message",
    "slugify",
    "target_type_name",
    "write_brief",
]
