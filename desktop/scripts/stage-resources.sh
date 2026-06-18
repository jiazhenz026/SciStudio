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
Both locations are scanned by the same package discovery path. Neither path
downloads dependencies; packages must be compatible with the bundled Python
environment.
EOF

echo "Staged desktop resources under $RESOURCES_ROOT"
