"""Alpha launch check-in: best-effort, fire-and-forget tester counting (#1855).

ALPHA-ONLY; removed in beta with the #1848 activation gate (see the beta-removal
checklist in docs/alpha-activation-gate.md).

Why this exists
---------------
The #1848 activation gate binds a per-machine token but is offline/zero-server,
so it yields no count of how many machines actually run the build, and a
security review confirmed it is bypassable (run the bundled backend directly,
patch the unsigned asar, spoof the fingerprint). Because SciStudio is fully
open source that is accepted; the real goal is a count of internal testers, not
unbreakable DRM. This check-in lives in the Python backend on purpose: every way
of starting the product -- Electron, a source checkout, or a direct
``python -m scistudio.cli.main`` (the most common gate bypass) -- flows through
``create_app``'s lifespan, so all of them report.

Design constraints (match the codebase's "never crash startup" posture)
-----------------------------------------------------------------------
- Never blocks the event loop: the POST runs on a daemon thread we never join.
- Never raises: every error is swallowed.
- No new dependency: stdlib ``urllib`` only.
- Opt-in: a no-op unless ``SCISTUDIO_ALPHA_CHECKIN_URL`` is set, so source
  checkouts and CI stay silent. The desktop app injects the URL from a
  gitignored config (see desktop/main.js); the URL is never committed.

The endpoint is a Slack incoming webhook, which accepts only ``{"text": ...}``;
the fingerprint and build are folded into a single human-readable line so the
channel can be eyeballed or exported and de-duplicated by fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
import threading
import urllib.request

# Must match desktop/activation.js machineFingerprint() byte-for-byte so a
# check-in can be cross-referenced against the issued-token ledger, which is
# keyed by the same fingerprint. See desktop/activation.js:36-68.
_FP_PREFIX = "scistudio-alpha-v1:"  # parity constant, not a version marker (#1848)
_TIMEOUT_S = 2


def _raw_machine_id() -> str:
    """Stable per-machine id mirroring desktop/activation.js rawMachineId()."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout
            for line in out.splitlines():
                if '"IOPlatformUUID"' in line:
                    rhs = line.split("=", 1)[-1].strip()
                    if rhs.startswith('"') and rhs.endswith('"') and len(rhs) > 2:
                        return f"mac:{rhs[1:-1]}"
        elif platform.system() == "Windows":
            out = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout
            for tok in out.split():
                if tok.count("-") >= 4 and len(tok) >= 32:
                    return f"win:{tok}"
    except Exception:
        # Fall through to the hostname-based fallback below.
        pass
    return f"host:{socket.gethostname()}"


def machine_fingerprint() -> str:
    """sha256 hex of the prefixed raw machine id (matches the gate's value)."""
    return hashlib.sha256((_FP_PREFIX + _raw_machine_id()).encode("utf-8")).hexdigest()


def _slack_text(fp: str, build: str, plat: str, name: str | None) -> str:
    who = f" name={name}" if name else ""
    return f"alpha_launch fp={fp} build={build} {plat}{who}"


def _post(url: str, text: str) -> None:
    try:
        data = json.dumps({"text": text}).encode("utf-8")
        # ``url`` is an operator-configured https webhook, not user input.
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=_TIMEOUT_S).read()
    except Exception:
        # Offline / firewalled / bad URL: a check-in is best-effort, never fatal.
        pass


def fire_and_forget() -> bool:
    """Dispatch a best-effort launch check-in. Returns immediately.

    Returns ``True`` when a POST was dispatched on a background daemon thread,
    ``False`` when no endpoint is configured (the opt-in no-op). The network
    call never blocks the caller and never raises.
    """
    url = (os.environ.get("SCISTUDIO_ALPHA_CHECKIN_URL") or "").strip()
    if not url:
        return False

    # Reuse the fingerprint Electron already computed when present (saves the
    # ioreg call); fall back to computing it so direct-backend launches still
    # report.
    fp = (os.environ.get("SCISTUDIO_ALPHA_FP") or "").strip() or machine_fingerprint()
    text = _slack_text(
        fp=fp,
        build=os.environ.get("SCISTUDIO_BUILD_NUMBER") or "unknown",
        plat=f"{platform.system()}/{platform.machine()}",
        name=(os.environ.get("SCISTUDIO_ALPHA_NAME") or "").strip() or None,
    )
    threading.Thread(target=_post, args=(url, text), daemon=True).start()
    return True
