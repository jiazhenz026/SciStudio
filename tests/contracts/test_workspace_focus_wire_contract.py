"""The workspace-focus wire, asserted across the two specs that split it.

ADR-054 spec 5 FR-001 asks the frontend to report where the person is along the
existing active-workflow channel. The manager split that requirement by owner
when the two specs were dispatched in parallel:

* **spec 4** owns the caller — ``frontend/src/lib/api/ai.ts`` declares
  ``WorkspaceFocusPayload`` and ``frontend/src/explore/workspaceFocus.ts``
  builds and posts it;
* **spec 5** owns the channel — ``WorkspaceFocusModel`` in
  ``src/scistudio/api/routes/ai.py`` receives it.

Neither agent could see the other's half while building it. Nothing in either
suite spans the join: the frontend tests assert against a fixture the frontend
authored, and the backend tests assert against a payload the backend authored,
so both can agree with themselves while disagreeing with each other.

That is not a hypothetical. Issue #2237 exists because this repository has
shipped exactly that break three times, and the ADR-054 spec 1 dispatch found a
fourth — three response models renamed ``previewer_id`` to ``panel_id`` with
the frontend never following, caught only when someone built the other half.
The failure is quiet by construction: a hand-written fixture that agrees with
the code beside it looks like coverage.

So this file reads the TypeScript source as text and compares it to the Pydantic
model. That is deliberately crude — no build step, no schema export, no
generator to fall out of date — and crude is what lets it live in the Python
suite and run on every change to either side.

TODO(#2237): a general mechanism for this, covering every model in
``schemas.py`` against ``types/api.ts``. This file covers the one wire ADR-054
splits across two specs; it is not that mechanism and does not pretend to be.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scistudio.api.routes.ai import ActiveContextRequest, WorkspaceFocusModel

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_AI_CLIENT = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "ai.ts"

#: The interface the frontend posts, and the model the backend parses.
_PAYLOAD_INTERFACE = "WorkspaceFocusPayload"


def _typescript_interface_fields(source: str, name: str) -> set[str]:
    """Field names declared on the ``export interface <name>`` block.

    Optional (``foo?:``) and required (``foo:``) alike, since optionality is a
    separate question from whether the two sides agree on the field's existence.
    """
    start = source.index(f"export interface {name}")
    body = source[source.index("{", start) + 1 : source.index("}", start)]
    # Drop line and block comments so a field named inside prose is not counted.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return set(re.findall(r"^\s*(\w+)\??\s*:", body, re.M))


@pytest.fixture(scope="module")
def frontend_source() -> str:
    assert FRONTEND_AI_CLIENT.is_file(), (
        f"{FRONTEND_AI_CLIENT.relative_to(REPO_ROOT)} is gone. If the focus caller moved, "
        "move this test with it rather than deleting it — the wire still has two ends."
    )
    return FRONTEND_AI_CLIENT.read_text(encoding="utf-8")


def test_the_focus_payload_and_model_declare_the_same_fields(frontend_source: str) -> None:
    """FR-001: what spec 4 sends is what spec 5 parses, field for field.

    A field only the frontend declares is silently dropped by the backend; a
    field only the backend declares is never populated. Both directions are
    reported, because they fail differently and a reader needs to know which.
    """
    sent = _typescript_interface_fields(frontend_source, _PAYLOAD_INTERFACE)
    received = set(WorkspaceFocusModel.model_fields)

    assert sent == received, (
        "The workspace-focus wire has drifted between ADR-054 spec 4 and spec 5.\n"
        f"  Frontend-only (the server ignores these): {sorted(sent - received) or 'none'}\n"
        f"  Backend-only (the frontend never sends these): {sorted(received - sent) or 'none'}\n"
        f"  frontend: {FRONTEND_AI_CLIENT.relative_to(REPO_ROOT)}::{_PAYLOAD_INTERFACE}\n"
        "  backend:  src/scistudio/api/routes/ai.py::WorkspaceFocusModel"
    )


def test_mode_is_the_only_required_field() -> None:
    """FR-001 states it, and the frontend's builder relies on it.

    Every identifier is optional so a tab that knows only part of its context
    can still report. If a field became required here, a caller that already
    ships would start getting a 422 rather than a recorded focus.
    """
    required = {name for name, info in WorkspaceFocusModel.model_fields.items() if info.is_required()}
    assert required == {"mode"}, f"expected only 'mode' to be required, got {sorted(required)}"


def test_mode_is_not_a_closed_enum() -> None:
    """A frontend that learns a mode before the backend does must not be refused.

    The backend types ``mode`` as ``str`` deliberately and drops what it cannot
    read, so an older backend answers 200 rather than 422 and the channel keeps
    working. Narrowing this to a ``Literal`` would turn a forward-compatible
    field into a breaking one, which is why it is asserted rather than assumed.
    """
    annotation = WorkspaceFocusModel.model_fields["mode"].annotation
    assert annotation is str, (
        f"'mode' is annotated {annotation!r}; FR-001 requires a plain str so an "
        "unknown mode is dropped rather than answered with a 422."
    )


def test_the_focus_rides_the_existing_active_context_channel() -> None:
    """FR-001: the report travels on the channel that already exists.

    ``focus`` is optional on the existing request, and the three states are
    distinct: absent leaves the stored focus alone, an object replaces it, and
    ``null`` clears it. That is what makes the change additive — every
    pre-ADR-054 caller omits the key and is unaffected.
    """
    assert "focus" in ActiveContextRequest.model_fields, (
        "ActiveContextRequest lost its 'focus' field; FR-001 forbids a second route."
    )
    assert not ActiveContextRequest.model_fields["focus"].is_required(), (
        "'focus' became required, which breaks every caller that predates ADR-054."
    )
    assert "workflow_id" in ActiveContextRequest.model_fields, (
        "the pre-existing active-workflow field is gone; the focus was meant to widen "
        "this channel, not replace it."
    )
