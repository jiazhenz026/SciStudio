"""CI-side helpers for the ADR-042/043/044 QA cascade.

This package hosts the *ratchet wrapper* (`ratchet.py`), the per-tool SARIF
adapters (`sarif/`), and the baselines I/O helpers (`baselines.py`) that
together implement the zero-tolerance enforcement model described in
ADR-042 §4.3.

Per ADR-042 §4.3, GitHub branch protection accepts a required check whose
``conclusion`` is one of ``success``, ``skipped``, or ``neutral``.  The
ratchet wrapper exploits that semantic to allow cleanup PRs to merge while
CI still reports a non-zero finding count, *provided* the count is
monotonically non-increasing and no previously-clean file regressed.

This package intentionally lives **outside** ``src/scieasy/`` because it is
infrastructure (CI), not runtime code.  Phase 1 lands the infrastructure;
Phase 2 wires the upload-sarif step.
"""

from __future__ import annotations
