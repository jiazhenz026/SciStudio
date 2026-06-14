"""Property-based tests for workflow path (de)serialisation (#1602).

``relativify_paths`` and ``absolutify_paths`` must round-trip: a relative,
forward-slash path under the project dir survives absolutify -> relativify
unchanged, for any OS-portable path. hypothesis generates the paths.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from scistudio.workflow.serializer import absolutify_paths, relativify_paths

_SCHEMA = {"properties": {"infile": {"ui_widget": "file_browser"}}}

# Path segments safe across OSes: alphanumeric, no separators / reserved names.
_segment = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=122),
    min_size=1,
    max_size=8,
).filter(lambda s: s not in (".", ".."))

_rel_path = st.lists(_segment, min_size=1, max_size=4).map("/".join)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(rel=_rel_path)
def test_relativify_inverts_absolutify(rel: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        project = Path(d).resolve()
        cfg = {"infile": rel}
        absolute = absolutify_paths(cfg, project, _SCHEMA)
        # absolutify must have produced an absolute path under the project dir.
        assert Path(absolute["infile"]).is_absolute()
        back = relativify_paths(absolute, project, _SCHEMA)
        assert back["infile"] == rel


def test_absolutify_leaves_absolute_paths_unchanged() -> None:
    with tempfile.TemporaryDirectory() as d:
        project = Path(d).resolve()
        already = str((project / "sub" / "f.csv").resolve())
        cfg = {"infile": already}
        assert absolutify_paths(cfg, project, _SCHEMA)["infile"] == already
