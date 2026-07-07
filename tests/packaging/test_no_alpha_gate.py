"""Regression checks for retiring the temporary alpha access gate."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_bundle_excludes_alpha_activation_gate() -> None:
    package_json = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
    bundled_files = set(package_json["build"]["files"])

    assert "activation.js" not in bundled_files
    assert "preload-gate.js" not in bundled_files

    removed_paths = [
        "desktop/activation.js",
        "desktop/preload-gate.js",
        "desktop/resources/alpha-gate.html",
        "desktop/resources/alpha-public-key.pem",
        "scripts/alpha-token.js",
        "scripts/alpha-token-gui.js",
        "scripts/alpha-token-issuer.command",
        "scripts/build-issuer-app.sh",
    ]
    assert [path for path in removed_paths if (ROOT / path).exists()] == []


def test_startup_paths_do_not_wire_alpha_checkin_or_slack_webhooks() -> None:
    startup_sources = [
        ROOT / "desktop/main.js",
        ROOT / "src/scistudio/api/app.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in startup_sources)

    forbidden = [
        "SCISTUDIO_ALPHA_CHECKIN_URL",
        "SCISTUDIO_ALPHA_FP",
        "SCISTUDIO_ALPHA_NAME",
        "alpha-checkin.json",
        "hooks.slack.com",
        "slack incoming webhook",
        "scistudio:alpha-activate",
        "alpha-gate.html",
    ]
    assert [token for token in forbidden if token in text] == []
