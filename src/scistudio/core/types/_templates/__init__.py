"""Packaged scaffolding templates served via ``GET /api/types/template``.

ADR-053 FR-028. This package ships the data-type scaffolding template
(``type_base_template.py``) that the "New data type" action drops into the
user's ``types/`` folder, in the user library or in the project.

It sits beside :mod:`scistudio.core.types` for the same reason
:mod:`scistudio.blocks._templates` sits beside the block base classes: a
template kept inside the installed package is checked by the same linters and
type checker as the code it scaffolds, so it cannot quietly drift away from
what :mod:`scistudio.core.types` actually exports.

Nothing imports the template. It is read as package data.
"""
