#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESKTOP_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd -- "$DESKTOP_ROOT/.." && pwd)
RESOURCES_ROOT="$DESKTOP_ROOT/resources"
FRONTEND_DIST="$REPO_ROOT/frontend/dist"
FRONTEND_TARGET="$RESOURCES_ROOT/frontend"
LEGACY_APP_ROOT="$RESOURCES_ROOT/app"
BACKEND_ROOT="$RESOURCES_ROOT/backend"
SRC_TARGET="$BACKEND_ROOT/src"

reset_dir() {
  rm -rf "$1"
  mkdir -p "$1"
}

# Pre-flight: the frontend build below needs frontend/node_modules (tsc, vite).
# Without them it fails with a cryptic "tsc: command not found", aborts this
# script before the backend tree is staged, and the resulting installer ships a
# broken app whose runtime cannot import scistudio (#1805). Fail early with the
# fix instead.
if [ ! -d "$REPO_ROOT/frontend/node_modules" ]; then
  echo "error: frontend dependencies are not installed." >&2
  echo "       Run 'npm --prefix frontend ci' (or 'npm --prefix frontend install') before staging." >&2
  exit 1
fi

echo "Building frontend..."
npm --prefix "$REPO_ROOT/frontend" run build

if [ ! -d "$FRONTEND_DIST" ]; then
  echo "Expected frontend build output at $FRONTEND_DIST" >&2
  exit 1
fi

mkdir -p "$RESOURCES_ROOT"
rm -rf "$LEGACY_APP_ROOT"
reset_dir "$FRONTEND_TARGET"
cp -R "$FRONTEND_DIST"/. "$FRONTEND_TARGET"/

mkdir -p "$BACKEND_ROOT"
reset_dir "$SRC_TARGET"
cp -R "$REPO_ROOT/src"/. "$SRC_TARGET"/

# #1775: Drop build metadata that may ride along from a local editable install.
# It is not needed at runtime (scistudio loads from this source tree on
# PYTHONPATH) and only leaks paths into the bundle and OTA snapshot.
rm -rf "$SRC_TARGET/scistudio.egg-info"

# Refresh the packaged SPA (scistudio/api/static) from the frontend build we
# just produced. This is the ONLY frontend a bundled desktop app serves
# (scistudio.api.app._resolve_spa_static_dir, SCISTUDIO_BUNDLED=1). The repo
# copy is a gitignored build artifact that the wheel build hook
# (setup.py _has_prebuilt_spa) skips refreshing once populated, so it can go
# stale and ship an old SPA. Overwriting the staged copy guarantees the DMG
# always carries the current frontend. (#1747)
STAGED_SPA="$SRC_TARGET/scistudio/api/static"
reset_dir "$STAGED_SPA"
cp -R "$FRONTEND_DIST"/. "$STAGED_SPA"/

# Fail loudly if the staged backend is incomplete instead of shipping a broken
# installer (#1805): the bundled runtime imports scistudio from this tree on
# PYTHONPATH and serves the SPA from scistudio/api/static.
if [ ! -f "$SRC_TARGET/scistudio/__init__.py" ]; then
  echo "error: staged backend is missing scistudio ($SRC_TARGET/scistudio/__init__.py)" >&2
  exit 1
fi
if [ ! -f "$STAGED_SPA/index.html" ]; then
  echo "error: staged SPA is missing ($STAGED_SPA/index.html)" >&2
  exit 1
fi

mkdir -p "$RESOURCES_ROOT/packages" "$RESOURCES_ROOT/git" "$RESOURCES_ROOT/python"
: > "$RESOURCES_ROOT/packages/.gitkeep"
: > "$RESOURCES_ROOT/git/.gitkeep"
: > "$RESOURCES_ROOT/python/.gitkeep"
cat > "$RESOURCES_ROOT/packages/README.md" <<'EOF'
Place bundled SciStudio source packages here for desktop builds.

Expected shape:

packages/
  scistudio-blocks-example/
    pyproject.toml
    src/scistudio_blocks_example/__init__.py

The GUI local package installer writes user-installed packages to the
user-scoped plugin directory instead of this bundled resources directory.
Both locations are scanned by the same package discovery path. User-installed
packages may resolve Python runtime dependencies with the bundled interpreter,
but dependency files stay in the user-scoped plugin directory.
EOF

# #1775: Stamp the OTA channel config the desktop client reads at launch
# (main.js loadOtaConfig). A local/dev build leaves SCISTUDIO_OTA_CHANNEL unset
# and gets OTA disabled, so a developer testing a local build is never disturbed
# or overwritten by a published patch. A release build sets the channel (and
# optionally the manifest URL) to enable launch-time update checks.
OTA_CHANNEL="${SCISTUDIO_OTA_CHANNEL:-}"
if [ -n "$OTA_CHANNEL" ]; then
  OTA_MANIFEST_URL="${SCISTUDIO_OTA_MANIFEST_URL:-https://github.com/jiazhenz026/SciStudio/releases/download/ota-$OTA_CHANNEL/manifest.json}"
  cat > "$RESOURCES_ROOT/ota-config.json" <<EOF
{
  "enabled": true,
  "channel": "$OTA_CHANNEL",
  "manifestUrl": "$OTA_MANIFEST_URL"
}
EOF
  echo "OTA enabled for channel '$OTA_CHANNEL' (manifest: $OTA_MANIFEST_URL)"
else
  cat > "$RESOURCES_ROOT/ota-config.json" <<'EOF'
{
  "enabled": false,
  "channel": "dev",
  "manifestUrl": null
}
EOF
  echo "OTA disabled (local/dev build; set SCISTUDIO_OTA_CHANNEL to enable)"
fi

echo "Staged desktop resources under $RESOURCES_ROOT"
