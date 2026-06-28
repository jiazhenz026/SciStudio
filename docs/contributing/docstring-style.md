---
title: "Docstring Style For Public API Symbols"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 52
related_specs:
  - adr-052-public-api-surface
language_source: en
---

# Docstring Style For Public API Symbols

## 1. Who This Is For

This is the convention every public-surface docstring follows. "Public surface"
means a symbol that is exported in a module's `__all__` or decorated `@stable` /
`@provisional` (the published API reference renders these). The reader we write
for is a **bench scientist who codes but is not a fluent software engineer**, or
an AI assistant generating help text from these docstrings. Both need to learn
*what the thing does and how to call it* without reading the source and without
knowing any of the project's internal records.

The published API reference is generated from these docstrings by
`scripts/docs/build_reference.py` with the **Google** docstring parser. Write
for that parser (see §4).

## 2. The Two Rules

### 2.1 No internal project records in user-facing prose

A docstring (and any prose a user reads) MUST NOT cite an internal project
record. This is a *family* of identifiers, not one prefix:

- decision/spec/requirement records: `ADR-NNN`, `FR-NNN`, `DSN-NNN`, `SC-NNN`,
  `OQ/ECA/OBS/BCP/AC-NNN`,
- record suffixes and addenda: `ADR-027 D7`, `ADR-020-Add5`, `Addendum 6`,
- tracking/bug/issue references: `TRK-NNN`, `BUG-NNN`, bare `#1234`,
- internal taxonomy labels that only make sense via an ADR: e.g. "Tier 1 /
  Tier 2" lifecycle tiers — describe the actual cases instead.

Keep the **behavior** the citation described; drop the **citation**. If a
citation genuinely helps a *maintainer*, move it to an inline implementation
comment (`# ...`), never the docstring.

DO keep legitimate external standards and tooling codes — they are real
technical content: `UTF-8`, `ISO-8601`, `RFC 3339`, `SHA-256`, ruff codes
(`RUF001`, `noqa`), MIME types, etc.

DO keep Sphinx cross-reference roles — `:class:`X``, `:meth:`X``, `:func:`X``,
`:attr:`X``, `:mod:`X``, `:data:`X``. They are the conventional in-editor form
and the reference build renders them as clean inline code. Do not convert or
delete them.

### 2.2 A complete, consistent shape

Every public class / function / block docstring states, in this order:

1. **Summary line** — one line, ends with a period, fits on one line
   (≈ ≤ 88 chars). A noun phrase for a class/type, an imperative phrase for a
   function ("Return ...", "Load ...").
2. **Purpose** — 1–3 sentences in plain language: what it is for and when a
   user reaches for it. No jargon. This is the part a non-fluent coder needs
   most and can least reconstruct from code.
3. **Contract** — the inputs, outputs, and failure modes, using Google
   sections (§4): `Args`, `Returns`/`Yields`, `Raises`. For **blocks**, also
   state the **ports** (named inputs/outputs) and **config** fields the block
   reads, and what the block emits.
4. **Example** — at least one short, runnable usage example where it helps a
   reader (almost always for classes, blocks, and non-trivial functions). Use a
   Google `Example:` section. Trivial one-line helpers may omit it.

Not every symbol needs every sub-part of the contract (a property with no args
has no `Args`), but summary + purpose are mandatory, and the contract must cover
whatever the symbol actually takes, returns, and raises.

### 2.3 Public attributes and properties must be documented (and they must render)

The published reference is generated with `show_if_no_docstring` off, so a public
attribute or property with **no docstring is silently dropped from the docs**.
This is why block UI metadata like `ui_icon` / `ui_color` and config fields
currently do not appear in the reference: they carry a `#` comment, and a `#`
comment is **not** a docstring griffe can render.

Every public attribute and property of a public class MUST carry a docstring so
that it both renders and reads clearly:

- **Class / instance attributes** (including `ClassVar` block metadata and
  config fields): add an *attribute docstring* — a string literal on the line
  immediately after the assignment:

  ```python
  ui_icon: ClassVar[str | None] = None
  """Lucide icon *name* shown on this block's node (e.g. ``"Microscope"``).

  An unknown name falls back to the category icon; ``None`` uses the default.
  """
  ```

  A one-line summary is the minimum; add a short purpose/contract line when the
  attribute's meaning, units, or accepted values are not obvious from the name.
  An existing explanatory `#` comment may stay as a maintainer note, but the
  user-facing description belongs in the attribute docstring.

- **Properties**: document them like any method (the property's own docstring),
  with summary + purpose + `Returns`/`Raises` as applicable.

Scope note: document the public attributes/properties of the public classes in
your module (those exported in `__all__` or `@stable`/`@provisional`). Skip
`_`-prefixed and `internal`-tier members. Adding an attribute docstring is a
docstring-only change — it does not alter runtime behavior.

## 3. Worked Example

Before (cites internal records, leans on ADR-internal "Tier" labels):

```python
class ProcessBlock(Block):
    """Block for deterministic, algorithm-driven data transformations.

    **Lifecycle hooks (ADR-027 D7)**: blocks with expensive one-time setup
    override :meth:`setup` ...

    **Tier 1 (ADR-020-Add5, ADR-027 D7)**: override :meth:`process_item` only
    with the signature ``(self, item, config, state=None)``. ...

    **Tier 2/3**: Override ``run()`` directly ...
    """
```

After (same behavior, reader-facing, example added; the maintainer note moves to
a comment):

```python
# Lifecycle + override contract are specified in ADR-027 D7 / ADR-020-Add5.
class ProcessBlock(Block):
    """Transform every item of a Collection with a deterministic algorithm.

    Subclass this for row-by-row or item-by-item transforms (filtering,
    normalising, feature extraction). The base `run()` streams the primary
    input Collection one item at a time, so peak memory stays at roughly one
    item regardless of dataset size.

    To implement a block, pick one of two levels of control:

    - **Common case** — override :meth:`process_item` with the signature
      ``(self, item, config, state=None)``. The base `run()` does the rest:
      one :meth:`setup` call, one :meth:`process_item` per item with the shared
      ``state``, auto-flush, pack into the output Collection, and :meth:`teardown`
      in a ``finally`` block.
    - **Full control** — override :meth:`run` directly and use ``map_items()``,
      ``parallel_map()``, or ``pack()`` to build the output Collection yourself.

    Set the class attribute ``algorithm`` to a human-readable identifier for the
    transform.

    Example:
        >>> class Doubler(ProcessBlock):
        ...     algorithm = "doubler"
        ...     def process_item(self, item, config, state=None):
        ...         return item * 2
    """
```

## 4. Google Sections Cheat-Sheet

The reference build uses the Google parser. Use these section headers exactly:

```
Args:
    name: Description. Type comes from the annotation; don't repeat it.

Returns:
    Description of the return value.

Yields:
    Description of each yielded value (generators).

Raises:
    ValueError: When and why.

Example:
    >>> result = do_thing(2)
    >>> result
    4
```

For blocks, document ports and config in the purpose/contract prose (there is no
dedicated Google section for ports), e.g. "Reads the primary input Collection;
emits one output Collection of the same length."

## 5. Checklist Before You Commit A Docstring

- [ ] Summary line + purpose present and jargon-free.
- [ ] No internal record citations in the docstring prose.
- [ ] External standards / tooling codes preserved.
- [ ] Sphinx roles (`:meth:` etc.) preserved, not mangled.
- [ ] Contract covers actual args / returns / raises (and ports/config for
      blocks).
- [ ] Every public attribute / property of the class has an attribute docstring
      (so it renders in the reference), not just a `#` comment.
- [ ] At least one runnable example where it helps.
- [ ] Reads cleanly to someone who has never seen the source or any ADR.
