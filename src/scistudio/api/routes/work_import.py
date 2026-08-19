"""ADR-053 §4 — the Bring In My Work session endpoint (FR-022 to FR-030).

One route: ``POST /api/work-import/sessions``. It turns the answers the
framing dialog collected into a running agent session, in a fixed order
that the rest of the feature depends on.

**Why the order is fixed.** The session's opening message is a single
line naming a file (FR-028); the agent has no other source of
instructions. If the spawn raced the write, the agent would open a file
that does not exist yet, or read half a brief, and the session would be
unrecoverable — the user would have to notice, kill the tab, and start
over. So the endpoint validates, composes, writes the brief *and closes
and fsyncs it*, and only then spawns (FR-024).

**Why the brief is a file rather than a system prompt.** Of the five
agent providers in the ADR-034 registry only ``claude-code`` is
``FLAG_FILE`` and can carry a hidden per-session prompt; ``codex``,
``kimi-code`` and both Qoder channels are ``AMBIENT`` and have no
per-session channel at all. A file plus a one-line pointer is the only
delivery that does not vary with that difference, and a sixth provider
needs nothing of this module beyond reading a file it is told to read
(FR-029).

**The one thing delivery still requires of a provider.** The pointer
itself is a positional command-line argument, so a CLI that parses its
first positional as a *subcommand* cannot receive it — Kimi Code is the
observed case and the registry records it as
``prompt_argv_prefix is None``. FR-029 removes the *system-prompt*
difference between providers; it does not remove that one. Such a
provider is refused up front by
:func:`~scistudio.ai.agent.availability.session_unsupported_reason`,
with the registry's own explanation and before anything is written, so a
session that cannot start leaves nothing behind.

**Why one file per session.** Two sessions started in one project must
not overwrite each other's instructions, and a brief that outlives its
session is how a user finds out what their agent was actually told when
a session went wrong (FR-030). The brief lives under the project's
``.scistudio/`` directory, which the default project ``.gitignore``
(:mod:`scistudio.core.versioning.gitignore_template`) already excludes
as per-machine runtime state, so session state never enters the user's
version history (FR-027).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from scistudio.ai.agent.availability import session_unsupported_reason
from scistudio.ai.agent.providers_registry import agent_keys
from scistudio.ai.agent.providers_registry import get as get_descriptor
from scistudio.ai.work_import.brief import compose_brief
from scistudio.ai.work_import.context import ImportSessionContext
from scistudio.api.routes.ai_pty import engine as _engine
from scistudio.api.routes.ai_pty.validation import _validate_project_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/work-import", tags=["work-import"])

#: Terminal-tab title for an import session. Fixed rather than derived
#: from the user's answers: the tab is found by recognising it, and a
#: title that changes with the source folder is not recognisable.
SESSION_TITLE = "Bring in my work"

#: Project-relative directory holding session briefs. Under ``.scistudio/``
#: so the default project ``.gitignore`` excludes it (FR-027).
BRIEF_DIR_PARTS = (".scistudio", "work-import")


def _new_brief_filename() -> str:
    """Return a fresh, collision-proof brief filename (FR-030).

    Timestamp first so a directory listing reads chronologically — the
    brief outlives its session precisely so it stays findable — and a
    random suffix so two sessions started in the same second still get
    distinct files.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}.md"


def _opening_message(brief_relpath: str) -> str:
    """Return the single line the user sees when the session starts (FR-028).

    One sentence, naming the file. The agent reads the brief itself, so a
    user watching the terminal sees a sentence rather than the full
    instruction set scrolling past.
    """
    return f"Read the file {brief_relpath} and follow the instructions in it."


class WorkImportSessionRequest(BaseModel):
    """Request body for ``POST /api/work-import/sessions``.

    Everything the framing dialog collected, plus the absolute project
    directory the session runs in.
    """

    project_dir: str = Field(description="Absolute path of the open project the session runs in.")
    source_location: str | None = Field(
        default=None,
        description="Directory holding the user's existing work, or null when there is no codebase.",
    )
    has_no_codebase: bool = Field(
        default=False,
        description="True when the user has no codebase to import from.",
    )
    destination_tier: Literal["project", "user_library"] = Field(
        description="Where the imported work lands: this project only, or the personal library.",
    )
    data_kinds: list[str] = Field(
        default_factory=list,
        description="Kinds of data the user works with (preset selections).",
    )
    data_kinds_other: str | None = Field(
        default=None,
        description="Free-text data kinds that no preset covered.",
    )
    workflow_description: str | None = Field(
        default=None,
        description="How the user's current process works, in their own words.",
    )
    interaction_wishes: str | None = Field(
        default=None,
        description="What the user wants to be able to change or see while the work runs.",
    )
    other_software: str | None = Field(
        default=None,
        description="Other software the work has to fit alongside.",
    )
    anything_else: str | None = Field(
        default=None,
        description="Anything else the user wanted the agent to know before it starts (FR-019a).",
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="Optional questions the user explicitly skipped.",
    )
    provider: str = Field(description="Agent provider registry key, e.g. 'claude-code'.")
    permission_mode: Literal["safe", "bypass"] = Field(
        description=(
            "Backend permission spelling. The frontend union is 'safe' | 'dangerous' and is mapped "
            "to this one at the request boundary."
        ),
    )


class WorkImportSessionResponse(BaseModel):
    """Response body for ``POST /api/work-import/sessions``.

    The caller adds a terminal tab carrying ``tab_id`` in running state
    and connects ``WS /api/ai/pty/{tab_id}`` with the usual query
    parameters, joining the PTY this endpoint already spawned.
    """

    tab_id: str = Field(description="Tab id of the pre-spawned session PTY.")
    title: str = Field(description="Title for the session's terminal tab.")
    brief_path: str = Field(description="Project-relative path of the brief the agent was pointed at.")
    provider: str = Field(description="Agent provider the session was spawned with.")
    permission_mode: str = Field(description="Permission mode the session was spawned with.")


def _write_brief(project_dir: Path, text: str) -> Path:
    """Write one session brief and return its absolute path.

    Opened with mode ``"x"`` so the filesystem itself enforces one brief
    per session: a name collision fails loudly instead of overwriting a
    concurrent session's instructions (FR-030). Flushed and fsynced
    before the handle closes, so the file the agent is about to be
    pointed at is complete on disk and not merely complete in a buffer
    (FR-024).
    """
    # ``project_dir`` reaches here only through
    # :func:`~scistudio.api.routes.ai_pty.validation._validate_project_dir`,
    # the same validator the PTY route uses: absolute, ``resolve(strict=True)``
    # canonicalised, confirmed to be an existing directory, and — when an MCP
    # context with an active project is installed — refused if it resolves
    # outside that project root. Every path segment appended below is a
    # module constant or a generated filename; none is user-supplied.
    #
    # CodeQL still reports ``py/path-injection`` on the two lines below, for
    # the reason its docstring records at the validator itself: the primitive
    # ``Path`` operations stay user-tainted whatever the allowlist check
    # proves. The alert is accepted here on the same basis, with one
    # difference from the PTY route worth stating plainly — that route only
    # makes this directory a subprocess ``cwd``, whereas this one creates
    # directories and writes a file under it, so the residual exposure when no
    # MCP context is installed is a brief written beneath an existing
    # directory of the caller's choosing rather than merely a working
    # directory set to it.
    brief_dir = project_dir.joinpath(*BRIEF_DIR_PARTS)
    brief_dir.mkdir(parents=True, exist_ok=True)
    brief_path = brief_dir / _new_brief_filename()
    with brief_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return brief_path


@router.post("/sessions", response_model=WorkImportSessionResponse)
def create_work_import_session(request: WorkImportSessionRequest) -> WorkImportSessionResponse:
    """Start a Bring In My Work session and return the tab that runs it.

    Validates the request, composes the brief from the collected answers,
    writes it under the project's ``.scistudio/`` directory, and only
    then spawns the agent — pointed at the brief by a single line. The
    session is an ordinary chat session from that moment on: the user can
    talk to it, redirect it, and end it like any other tab.
    """
    try:
        project_dir = _validate_project_dir(request.project_dir)
    except (RuntimeError, PermissionError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid project_dir: {exc}") from exc

    # The provider is stated, never inferred (ADR-034 FR-010). Checked
    # here as well as in the spawn so a typo is a 400 on the request that
    # made it rather than a 503 that reads like the agent is unavailable.
    accepted = agent_keys()
    if request.provider not in accepted:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider {request.provider!r}; expected one of {sorted(accepted)}.",
        )

    # A registry agent is not automatically a provider that can *run* a session.
    # The opening message is delivered as a positional command-line argument
    # (FR-029), and Kimi Code parses its first positional as a subcommand, so
    # the spawn raises rather than launching an agent with no instructions.
    # Unhandled, that reached the user as a bare 500 with the registry's own
    # explanation lost, plus a brief on disk for a session that never started.
    #
    # Refused here, before the brief is composed or written, for the reason
    # ``AIBlock.validate_config`` refuses the same providers at config time
    # (``scistudio.blocks.ai.ai_block``): a limitation the registry already
    # knows about should surface as the registry's own sentence at the moment
    # the user chose the provider, not as an opaque failure several layers down.
    # The dialog additionally filters these providers out of the picker, so a
    # user should never get here — this is the guard for a caller that is not
    # the dialog, and for a future provider whose limitation nobody carried
    # through to the frontend.
    unsupported = session_unsupported_reason(get_descriptor(request.provider))
    if unsupported is not None:
        raise HTTPException(
            status_code=400,
            detail=(f"Provider {request.provider!r} cannot run a Bring In My Work session. {unsupported}"),
        )

    # ``ImportSessionContext`` owns the answer-shape rules (contract C2): a
    # source location supplied alongside "I don't have a codebase", neither
    # supplied, a skip marker for a question that is not skippable, or a
    # question marked skipped that nevertheless carries an answer. Those are
    # bad requests, not server faults, so each one becomes a 400 carrying the
    # dataclass's own message rather than a 500 with a stack trace. The rules
    # are not restated here: two copies of the same rule drift.
    try:
        context = ImportSessionContext(
            source_location=request.source_location,
            has_no_codebase=request.has_no_codebase,
            destination_tier=request.destination_tier,
            data_kinds=tuple(request.data_kinds),
            data_kinds_other=request.data_kinds_other,
            workflow_description=request.workflow_description,
            interaction_wishes=request.interaction_wishes,
            other_software=request.other_software,
            anything_else=request.anything_else,
            skipped=frozenset(request.skipped),
            provider=request.provider,
            permission_mode=request.permission_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid session context: {exc}") from exc

    brief_text = compose_brief(context)

    try:
        brief_path = _write_brief(project_dir, brief_text)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write the session brief: {exc}") from exc

    brief_relpath = brief_path.relative_to(project_dir).as_posix()

    # Spawn LAST. Everything above is complete and closed on disk before
    # the agent that will read it exists (FR-024).
    try:
        tab_id = _engine.open_work_import_tab(
            provider=request.provider,
            cwd=str(project_dir),
            opening_message=_opening_message(brief_relpath),
            permission_mode=request.permission_mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Provider binary not found: {exc}") from exc
    except RuntimeError as exc:
        message = str(exc)
        status = 503 if "cap" in message.lower() else 500
        raise HTTPException(status_code=status, detail=message) from exc

    logger.info(
        "work-import session started: tab_id=%s provider=%s permission=%s brief=%s",
        tab_id,
        request.provider,
        request.permission_mode,
        brief_relpath,
    )
    return WorkImportSessionResponse(
        tab_id=tab_id,
        title=SESSION_TITLE,
        brief_path=brief_relpath,
        provider=request.provider,
        permission_mode=request.permission_mode,
    )
