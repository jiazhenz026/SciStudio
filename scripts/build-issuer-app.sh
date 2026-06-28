#!/usr/bin/env bash
# #1848: assemble a tiny no-Electron macOS .app that launches the alpha token
# issuer GUI. Double-click the resulting app to open the issuer in your browser;
# it runs the bundled Node scripts and reads the signing key from
# ~/.scistudio/alpha-signing.key. Use the GUI's "Quit issuer" button to stop it.
#
# Usage:  bash scripts/build-issuer-app.sh [dest-dir]   (default dest: ~/Desktop)
#
# The .app is a build artifact (not committed). Requires Node.js on the machine
# that runs it. ALPHA-ONLY; delete in beta with the rest of the gate (#1848).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
DEST_DIR="${1:-$HOME/Desktop}"
APP="$DEST_DIR/Alpha Token Issuer.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Self-contained: bundle the issuer scripts so the app works wherever it lives.
cp "$SCRIPT_DIR/alpha-token.js" "$APP/Contents/Resources/alpha-token.js"
cp "$SCRIPT_DIR/alpha-token-gui.js" "$APP/Contents/Resources/alpha-token-gui.js"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Alpha Token Issuer</string>
  <key>CFBundleDisplayName</key><string>Alpha Token Issuer</string>
  <key>CFBundleIdentifier</key><string>org.scistudio.alpha-token-issuer</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/run" <<'RUN'
#!/bin/bash
# Launched by LaunchServices with a minimal PATH; add common Node locations.
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v node >/dev/null 2>&1; then
  osascript -e 'display alert "Node.js not found" message "Install Node.js, then reopen Alpha Token Issuer."' >/dev/null 2>&1
  exit 1
fi
exec node "$RES/alpha-token-gui.js"
RUN
chmod +x "$APP/Contents/MacOS/run"

echo "Built: $APP"
echo "Double-click it (or move it anywhere, e.g. /Applications) to launch the issuer."
