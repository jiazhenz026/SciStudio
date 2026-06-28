"""Griffe extension: render Sphinx cross-reference roles as clean inline code.

The SciStudio public-surface docstrings use Sphinx/reStructuredText cross-
reference roles (``:class:`X```, ``:meth:`X```, ``:mod:`X```, ``:data:`X```,
``:func:`X```, ``:attr:`X```, ...). Those roles are the conventional in-source
form a Python developer reads in an editor, but the generated API reference is
rendered by ``mkdocstrings`` with the **Google** docstring parser, which does
not understand RST roles — so they leak verbatim onto the page (e.g. the text
``:meth:`to_memory``` instead of ``to_memory``), which reads as noise.

This extension rewrites those roles to plain Markdown inline code at griffe
**load time**, so:

* the on-disk source keeps its conventional RST roles (unchanged), and
* the published reference renders ``to_memory`` cleanly.

We deliberately render as inline code rather than ``mkdocstrings`` cross-
reference autorefs (``[X][]``): a short-name role like ``:class:`PreviewTarget```
has no fully-qualified target, so an autoref would not resolve to a page anchor
and would fail the ``mkdocs build --strict`` gate (ADR-052 §7 requires the
reference to build green). Inline code is unambiguous, link-free, and safe.

Wiring (``mkdocs.yml``)::

    plugins:
      - mkdocstrings:
          handlers:
            python:
              options:
                extensions:
                  - scripts/docs/griffe_sphinx_roles.py:SphinxRolesToInlineCode

ADR-052 §7 (generated reference). This is doc-build tooling, not core runtime.
"""

from __future__ import annotations

import re

from griffe import Extension, Object

# A Sphinx cross-reference role: ``:role:`target``` or ``:role:`Title <target>```.
# ``role`` may carry a domain prefix (``:py:class:``) and the role name itself
# may contain ``+``/``-``. ``target`` may be prefixed with ``~`` (show only the
# last dotted component) and may use the ``Title <target>`` explicit-title form.
_ROLE = re.compile(r":(?:py:)?(?:[a-zA-Z][a-zA-Z+-]*):`([^`]+)`")


def _render_target(raw: str) -> str:
    """Turn a role target into the display text, honoring RST conventions.

    * ``Title <target>`` explicit-title form → ``Title``.
    * ``~pkg.mod.Name`` (leading tilde) → ``Name`` (last component only).
    * otherwise the target verbatim (``pkg.mod`` stays fully qualified).
    """
    target = raw.strip()
    # Explicit-title form: "Display Text <actual.target>".
    explicit = re.match(r"^(.*?)\s*<([^>]+)>$", target)
    if explicit:
        title = explicit.group(1).strip()
        if title:
            return title
        target = explicit.group(2).strip()
    if target.startswith("~"):
        return target[1:].rsplit(".", 1)[-1]
    return target


def _convert(text: str) -> str:
    return _ROLE.sub(lambda m: f"`{_render_target(m.group(1))}`", text)


class SphinxRolesToInlineCode(Extension):
    """Rewrite Sphinx cross-reference roles in docstrings to inline code."""

    def on_object(self, *, obj: Object, **kwargs: object) -> None:
        """Rewrite Sphinx roles in this object's docstring to inline code."""
        doc = obj.docstring
        if doc is None or not doc.value or ":" not in doc.value:
            return
        doc.value = _convert(doc.value)
