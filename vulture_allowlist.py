"""Vulture allowlist for SciStudio.

Vulture cannot know about framework callbacks, entry-point handlers, Pydantic
field validators, FastAPI route functions, or class attributes consumed only by
introspection. Names referenced here are treated as live by vulture even when
no in-repo call site exists.

Add an entry by writing a fake usage. The shape vulture expects is::

    _.<attribute>           # for class/instance attributes
    <module>.<name>         # for module-level callables

Keep entries minimal and explain why each is allowlisted in a comment. When a
new genuinely dead method is found, the right fix is usually to delete it, not
to allowlist it.
"""

# pydantic model_config / validator hooks ------------------------------------
# Pydantic v2 uses these attribute names from the class body; vulture cannot
# see the consumer (the Pydantic metaclass).
_ = None
_.model_config  # noqa: F821
_.model_validator  # noqa: F821
_.field_validator  # noqa: F821

# FastAPI / route decorators -------------------------------------------------
# Route handlers are reached only through the ASGI app; vulture sees them as
# unused. Allowlist the conventional names so handler bodies stay green.
_.startup  # noqa: F821
_.shutdown  # noqa: F821

# entry-point handlers -------------------------------------------------------
# Block / runner / type classes are loaded through ``importlib.metadata`` entry
# points declared in ``pyproject.toml``. vulture cannot trace those, so the
# class-level discovery names are allowlisted.
_.load_data  # noqa: F821
_.save_data  # noqa: F821

# CLI entry points -----------------------------------------------------------
# Typer commands and ``__main__`` shims wire only through the ``scistudio``
# console script and ``python -m scistudio.*`` invocations.
_.main  # noqa: F821
