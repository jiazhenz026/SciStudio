"""Public author-facing previewer helpers (ADR-052 §8).

This is the canonical home for the small, reusable helpers a package-owned
previewer may import, alongside the two canonical author roots
``scistudio.previewers.models`` and ``scistudio.previewers.data_access``.

Today it exposes a single helper:

* :func:`sanitize_svg` — defense-in-depth SVG sanitization (FR-019) that a
  package SVG/plot previewer reuses before returning SVG text. Previously this
  lived in the core-internal ``scistudio.previewers.fallbacks`` module; it was
  relocated here in #1823 so authors never import from ``fallbacks``.

NOTE: the authoritative security boundary for rendered SVG is the frontend's
``<iframe sandbox="" srcDoc=...>`` (no ``allow-scripts`` / ``allow-same-origin``).
This best-effort regex pass is a second layer, not the sole guarantee, since
regex-based HTML filtering cannot be made fully robust.
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
    """Strip <script>, on* handlers, and remote href/xlink:href from SVG (FR-019).

    Public author helper (ADR-052 §8.3 — provisional). A package SVG/plot
    previewer calls this before returning SVG text. Returns
    ``(sanitized_text, removed_anything)``. The authoritative security boundary
    is the frontend sandboxed iframe; this is a best-effort second layer.
    """
    sanitized = _SVG_SCRIPT_RE.sub("", svg_text)
    sanitized, n_events = _SVG_EVENT_ATTR_RE.subn("", sanitized)
    sanitized, n_hrefs = _SVG_EXTERNAL_HREF_RE.subn("", sanitized)
    removed = sanitized != svg_text or n_events > 0 or n_hrefs > 0
    return sanitized, removed
