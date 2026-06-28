#!/bin/bash
# #1848: double-click launcher for the alpha token issuer GUI.
#
# Double-click this file in Finder. It opens the token issuer in your browser so
# you can paste a tester's machine fingerprint and sign a token. Press Ctrl+C in
# the Terminal window it opens to stop the server.
#
# It resolves its own location, so the repo can live anywhere. ALPHA-ONLY;
# delete in beta with the rest of the gate (see issue #1848).

set -e

# This file lives in scripts/, so the repo root is one level up.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v node >/dev/null 2>&1; then
  echo "error: 'node' was not found on your PATH." >&2
  echo "Install Node.js, then double-click this launcher again." >&2
  echo "Press Return to close." >&2
  read -r _
  exit 1
fi

echo "Starting the Alpha Token Issuer…"
echo "(A browser tab will open. Press Ctrl+C here to stop.)"
echo
exec node scripts/alpha-token-gui.js
