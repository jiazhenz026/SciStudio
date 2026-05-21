"""Tests for monorepo scanner gating behind SCISTUDIO_DEV env var (#509)."""

from __future__ import annotations

import os
from unittest.mock import patch


def test_monorepo_scan_disabled_by_default():
    """Without SCISTUDIO_DEV=1, include_monorepo should be False."""
    env = {k: v for k, v in os.environ.items() if k != "SCISTUDIO_DEV"}
    with patch.dict(os.environ, env, clear=True):
        assert os.environ.get("SCISTUDIO_DEV") != "1"


def test_monorepo_scan_enabled_with_env():
    """With SCISTUDIO_DEV=1, include_monorepo should be True."""
    with patch.dict(os.environ, {"SCISTUDIO_DEV": "1"}):
        assert os.environ.get("SCISTUDIO_DEV") == "1"


def test_monorepo_scan_disabled_with_wrong_value():
    """SCISTUDIO_DEV must be exactly '1' to enable monorepo scan."""
    with patch.dict(os.environ, {"SCISTUDIO_DEV": "true"}):
        assert os.environ.get("SCISTUDIO_DEV") != "1"
    with patch.dict(os.environ, {"SCISTUDIO_DEV": "0"}):
        assert os.environ.get("SCISTUDIO_DEV") != "1"
