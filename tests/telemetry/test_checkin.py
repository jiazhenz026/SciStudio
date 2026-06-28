"""Tests for the alpha-only launch check-in (#1855).

ALPHA-ONLY; deleted in beta with the rest of the #1848 gate.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading
import time

import pytest

from scistudio.telemetry import checkin


def test_no_url_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in: with no endpoint configured the check-in does nothing."""
    monkeypatch.delenv("SCISTUDIO_ALPHA_CHECKIN_URL", raising=False)
    assert checkin.fire_and_forget() is False


def test_fingerprint_matches_gate_formula() -> None:
    """The fingerprint must equal desktop/activation.js machineFingerprint().

    Same construction: sha256("scistudio-alpha-v1:" + raw machine id). We can't
    know the raw id here, but we can prove the digest is the prefixed-raw-id
    hash and is a stable 64-char hex string.
    """
    fp = checkin.machine_fingerprint()
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
    expected = hashlib.sha256(
        (checkin._FP_PREFIX + checkin._raw_machine_id()).encode("utf-8")
    ).hexdigest()
    assert fp == expected


def test_slack_text_is_single_line_with_fields() -> None:
    line = checkin._slack_text(fp="abc123", build="7", plat="Darwin/arm64", name="Tester")
    assert "\n" not in line
    assert "fp=abc123" in line
    assert "build=7" in line
    assert "Darwin/arm64" in line
    assert "name=Tester" in line


def test_slack_text_omits_name_when_absent() -> None:
    line = checkin._slack_text(fp="abc", build="1", plat="Linux/x86_64", name=None)
    assert "name=" not in line


def test_dispatch_posts_slack_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: a configured URL receives a Slack {"text": ...} body."""
    received: list[dict] = []

    class Collector(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            n = int(self.headers.get("Content-Length", 0))
            received.append(json.loads(self.rfile.read(n) or b"{}"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_: object) -> None:  # silence
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Collector) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        monkeypatch.setenv("SCISTUDIO_ALPHA_CHECKIN_URL", f"http://127.0.0.1:{port}/")
        monkeypatch.setenv("SCISTUDIO_ALPHA_FP", "deadbeef")
        monkeypatch.setenv("SCISTUDIO_BUILD_NUMBER", "42")
        monkeypatch.setenv("SCISTUDIO_ALPHA_NAME", "unit-test")

        assert checkin.fire_and_forget() is True
        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.02)
        httpd.shutdown()

    assert received, "collector never received the check-in"
    payload = received[0]
    assert set(payload.keys()) == {"text"}  # Slack incoming-webhook shape
    assert "fp=deadbeef" in payload["text"]
    assert "build=42" in payload["text"]
    assert "name=unit-test" in payload["text"]


def test_uses_forwarded_fingerprint_without_recompute(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Electron forwards SCISTUDIO_ALPHA_FP, the check-in uses it verbatim."""
    sent: list[str] = []
    monkeypatch.setattr(checkin, "_post", lambda url, text: sent.append(text))
    monkeypatch.setattr(
        checkin, "machine_fingerprint", lambda: pytest.fail("should not recompute")
    )
    monkeypatch.setenv("SCISTUDIO_ALPHA_CHECKIN_URL", "http://example.invalid/")
    monkeypatch.setenv("SCISTUDIO_ALPHA_FP", "forwarded-fp")
    # Give the daemon thread a moment; _post is monkeypatched so it's instant.
    assert checkin.fire_and_forget() is True
    deadline = time.time() + 2
    while not sent and time.time() < deadline:
        time.sleep(0.01)
    assert sent and "fp=forwarded-fp" in sent[0]


def test_bad_url_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead endpoint must not raise or block beyond the short timeout."""
    monkeypatch.setenv("SCISTUDIO_ALPHA_CHECKIN_URL", "http://127.0.0.1:1/")
    monkeypatch.setenv("SCISTUDIO_ALPHA_FP", "x")
    start = time.perf_counter()
    assert checkin.fire_and_forget() is True  # returns immediately (background thread)
    assert (time.perf_counter() - start) < 0.5
