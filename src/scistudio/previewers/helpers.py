"""Public author-facing previewer helpers.

This is the canonical home for the small, reusable helpers a package-owned
previewer may import, alongside the two main author roots
:mod:`scistudio.previewers.models` and :mod:`scistudio.previewers.data_access`.

Today it exposes a single helper, :func:`sanitize_svg`, which a package SVG/plot
previewer uses to scrub SVG text before returning it.

Note: the authoritative security boundary for rendered SVG is the frontend's
sandboxed ``<iframe>`` (no scripts, no same-origin access). This regex pass is a
best-effort second layer, not the sole guarantee, because regex-based HTML
filtering can never be made fully robust.
"""

from __future__ import annotations

import re

from scistudio.stability import provisional

__all__ = ["sanitize_svg"]

# SVG sanitization: strip <script> blocks and event handler / external-resource
# attributes (FR-019, defense-in-depth). The closing tag is matched as
# ``</script[^>]*>`` (handles malformed closers like ``</script\t\nbar>``) and an
# unterminated ``<script>`` is stripped to end-of-text.
_SVG_SCRIPT_RE = re.compile(r"<script\b[^>]*>[\s\S]*?(?:</script[^>]*>|\Z)", re.IGNORECASE)
_SVG_EVENT_ATTR_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
# Strip remote (http/https/protocol-relative) and active-scheme
# (javascript:/vbscript:) href / xlink:href values; data: URIs (embedded
# images) are left intact and are inert under the iframe sandbox.
_SVG_EXTERNAL_HREF_RE = re.compile(
    r"\s(?:xlink:href|href)\s*=\s*"
    r"(\"\s*(?:https?:|//|javascript:|vbscript:)[^\"]*\"|'\s*(?:https?:|//|javascript:|vbscript:)[^']*')",
    re.IGNORECASE,
)


@provisional(since="0.3.1")
def sanitize_svg(svg_text: str) -> tuple[str, bool]:
    """Strip scripts, event handlers, and remote links from SVG text.

    Call this before returning SVG from a previewer to remove ``<script>``
    blocks, ``on*`` event-handler attributes, and remote or active-scheme
    ``href`` / ``xlink:href`` values (http/https, protocol-relative,
    ``javascript:``, ``vbscript:``). Embedded ``data:`` image URIs are left
    intact. This is a best-effort second layer; the sandboxed iframe in the
    frontend is the authoritative boundary.

    Args:
        svg_text: The raw SVG markup to sanitize.

    Returns:
        A ``(sanitized_text, removed_anything)`` tuple, where the boolean is
        ``True`` if anything was stripped.

    Example:
        >>> clean, removed = sanitize_svg('<svg onload="x()"><rect/></svg>')
        >>> removed
        True
    """
    sanitized = _SVG_SCRIPT_RE.sub("", svg_text)
    sanitized, n_events = _SVG_EVENT_ATTR_RE.subn("", sanitized)
    sanitized, n_hrefs = _SVG_EXTERNAL_HREF_RE.subn("", sanitized)
    removed = sanitized != svg_text or n_events > 0 or n_hrefs > 0
    return sanitized, removed
