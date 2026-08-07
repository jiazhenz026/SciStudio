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
delivery that behaves identically on all five, and a provider added
later needs nothing of this module beyond reading a file it is told to
read (FR-029).

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
from pydantic import BaseModel, Field, field_validator

from scistudio.ai.agent.providers_registry import agent_keys
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

#: The optional questions a user may explicitly skip (contract C2). A
#: skipped question reaches the brief marked as skipped rather than
#: omitted, so the agent can tell "the user did not say" from "the user
#: said nothing applies" (FR-021).
SKIPPABLE_QUESTIONS = frozenset({"workflow_description", "interaction_wishes", "other_software"})


def _new_brief_filename() -> str:
    """Return a fresh, collision-proof brief filename (FR-030).

    Timestamp first so a directory listing reads chronologically — the
    brief outlives its session precisely so it can be found later — and a
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

    @field_validator("skipped")
    @classmethod
    def _skipped_names_are_known(cls, value: list[str]) -> list[str]:
        """Reject a skip marker for a question that cannot be skipped.

        An unrecognised name would otherwise be dropped silently and the
        brief would render an explicitly-skipped question as unanswered —
        exactly the distinction FR-021 exists to preserve.
        """
        unknown = sorted(set(value) - SKIPPABLE_QUESTIONS)
        if unknown:
            raise ValueError(
                f"unknown skippable question(s) {unknown}; expected a subset of {sorted(SKIPPABLE_QUESTIONS)}"
            )
        return value


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

    context = ImportSessionContext(
        source_location=request.source_location,
        has_no_codebase=request.has_no_codebase,
        destination_tier=request.destination_tier,
        data_kinds=tuple(request.data_kinds),
        data_kinds_other=request.data_kinds_other,
        workflow_description=request.workflow_description,
        interaction_wishes=request.interaction_wishes,
        other_software=request.other_software,
        skipped=frozenset(request.skipped),
        provider=request.provider,
        permission_mode=request.permission_mode,
    )
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
