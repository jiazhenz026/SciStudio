"""The panel message contract, as the scaffold's generated documents read it.

ADR-054 spec 5 FR-014/FR-015. The scaffold writes two documents that both speak
the D-011 envelope: the panel's own ``index.html`` and the ``harness.html`` that
stands in for the host. Neither restates the contract in its own words —
:func:`contract_javascript` renders the constant block both embed, and it is
rendered from the names in this module.

**Why the names live here rather than being copied into a template.** A harness
that hand-copies the message names is drift waiting to happen: the host learns a
new request type, the harness keeps answering the old set, and the agent's
"I checked it in the harness" stops meaning anything. Because the documents are
generated from these tuples and the harness's router is *driven* by them —
it validates an inbound type against :data:`PANEL_TO_HOST_TYPES` and answers a
request by looking the reply up in :data:`PANEL_REQUEST_RESULT_TYPES` — adding a
name here changes what the harness does, and removing one takes the behaviour
with it.

**The host's copy is the frontend's, and the two are held together by a test.**
The host half of this contract is TypeScript
(``frontend/src/panels/panelMessages.ts``, named by
:data:`HOST_CONTRACT_RELATIVE_PATH`); a Python scaffold cannot import it, and the
frontend source is not shipped inside the installed package, so this module
cannot be generated from it at runtime. What holds them together instead is
``tests/ai/test_mcp_tools_panels.py``, which reads that file and fails when its
``HOST_TO_PANEL_TYPES`` / ``PANEL_TO_HOST_TYPES`` / ``PANEL_HOST_ACTIONS`` lists
stop matching the tuples here. That test is the reason this module is a mirror
rather than a fork.

:data:`PANEL_MESSAGE_MARKER` and the API version are not restated either: the
version is :data:`scistudio.core.panels.PANEL_API_VERSION`, the one constant
ADR-054 spec 1 SC-001 allows.
"""

from __future__ import annotations

import json
from typing import Any, Final

from scistudio.core.panels import PANEL_API_VERSION

__all__ = [
    "HOST_CONTRACT_RELATIVE_PATH",
    "HOST_TO_PANEL_TYPES",
    "PANEL_API_VERSION",
    "PANEL_HOST_ACTIONS",
    "PANEL_MESSAGE_MARKER",
    "PANEL_REQUEST_RESULT_TYPES",
    "PANEL_REQUEST_TYPES",
    "PANEL_TO_HOST_TYPES",
    "contract_constants",
    "contract_javascript",
]


#: The D-011 envelope marker. A message without it is not part of the contract.
PANEL_MESSAGE_MARKER: Final[int] = 1

#: Every message type the host sends a mounted panel (spec 1 D-017).
HOST_TO_PANEL_TYPES: Final[tuple[str, ...]] = (
    "init",
    "update",
    "read_result",
    "resource_result",
    "host_action_result",
    "error",
    "state_request",
    "teardown",
)

#: Every message type a panel may send the host. A *displaying* panel is granted
#: none of the outbound path beyond ``ready``, ``read``, ``resource``,
#: ``host_action``, ``error`` and ``state``; ``emit`` belongs to a producing
#: panel alone (spec 1 FR-011, FR-012).
PANEL_TO_HOST_TYPES: Final[tuple[str, ...]] = (
    "ready",
    "read",
    "resource",
    "host_action",
    "emit",
    "error",
    "state",
)

#: The closed set of actions ``host_action`` names (spec 1 D-017). Each is chrome
#: the frame cannot perform for itself.
PANEL_HOST_ACTIONS: Final[tuple[str, ...]] = ("export", "download", "editor_handoff")

#: The three request types, each answered by exactly one result type (D-017).
#: Written as a mapping rather than by string concatenation so a fourth request
#: type cannot be added without deciding what answers it — and so the harness's
#: router can be driven by it instead of by a switch statement.
PANEL_REQUEST_RESULT_TYPES: Final[dict[str, str]] = {
    "read": "read_result",
    "resource": "resource_result",
    "host_action": "host_action_result",
}

#: The request types in the order the harness reports them.
PANEL_REQUEST_TYPES: Final[tuple[str, ...]] = tuple(PANEL_REQUEST_RESULT_TYPES)

#: Where the host's half of this contract lives, relative to the repository
#: root. Named here so the parity test and the reference document cite one path.
HOST_CONTRACT_RELATIVE_PATH: Final[str] = "frontend/src/panels/panelMessages.ts"


def contract_constants() -> dict[str, Any]:
    """Return the contract as the JSON-safe mapping the documents embed.

    Returns:
        A dict whose keys are the JavaScript constant names the generated
        documents declare, and whose values are their values.

    Example:
        >>> contract_constants()["PANEL_MESSAGE_MARKER"]
        1
        >>> contract_constants()["PANEL_REQUEST_RESULT_TYPES"]["read"]
        'read_result'
    """
    return {
        "PANEL_MESSAGE_MARKER": PANEL_MESSAGE_MARKER,
        "PANEL_API_VERSION": PANEL_API_VERSION,
        "HOST_TO_PANEL_TYPES": list(HOST_TO_PANEL_TYPES),
        "PANEL_TO_HOST_TYPES": list(PANEL_TO_HOST_TYPES),
        "PANEL_HOST_ACTIONS": list(PANEL_HOST_ACTIONS),
        "PANEL_REQUEST_RESULT_TYPES": dict(PANEL_REQUEST_RESULT_TYPES),
    }


def contract_javascript(*, indent: str = "  ") -> str:
    """Render the ``var`` block the panel document and the harness both embed.

    The block is plain ES5 ``var`` declarations because a panel document is
    strictly self-contained and loads with no build step (spec 1 FR-034, A-004),
    and because the harness has to run from a ``file://`` URL with nothing
    installed.

    Args:
        indent: Leading whitespace for each declaration, so the block drops into
            an already-indented ``<script>`` body without reflowing it.

    Returns:
        One newline-separated block of ``var NAME = <json>;`` lines, generated
        from :func:`contract_constants` and therefore from this module's tuples.

    Example:
        >>> "var PANEL_MESSAGE_MARKER = 1;" in contract_javascript(indent="")
        True
    """
    lines = [f"{indent}var {name} = {json.dumps(value)};" for name, value in contract_constants().items()]
    return "\n".join(lines)
