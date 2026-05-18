"""SARIF 2.1.0 converters for the ADR-042/043/044 QA cascade (TC-1G.2 + 1G.3).

Each submodule converts one tool's native output format to a SARIF log
that GitHub Code Scanning can ingest via
``github/codeql-action/upload-sarif@v3``.

Per ADR-042 §4.3 line 504-507, ``partialFingerprints`` give us free
per-finding stable IDs and PR-diff-based auto-close.  The fingerprint
algorithm is documented in :mod:`._common`.

The package is intentionally light on third-party dependencies — only the
Python stdlib is required.  SARIF 2.1.0 is JSON, the schema is stable,
and we emit a deterministic subset.
"""

from __future__ import annotations
