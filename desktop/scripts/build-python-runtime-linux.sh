#!/usr/bin/env bash
set -euo pipefail

# #1895: Build the portable Python runtime bundled into the Linux AppImage.
#
# Mirrors build-python-runtime-macos.sh but targets the python-build-standalone
# linux-gnu triples. The bundled interpreter is glibc-based (like the numpy /
# pyarrow / zarr / matplotlib manylinux wheels it installs), so the AppImage
# must be built on the oldest supported glibc baseline (see
# .github/workflows/desktop-linux-appimage.yml, which pins ubuntu-22.04) to run
# across distros. `pty` is stdlib on Linux, so no PTY backend needs installing.

PYTHON_VERSION_PREFIX="${SCISTUDIO_DESKTOP_PYTHON_VERSION_PREFIX:-3.12}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DESKTOP_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$DESKTOP_ROOT/.." && pwd)"
RESOURCES_ROOT="$DESKTOP_ROOT/resources"
PYTHON_ROOT="$RESOURCES_ROOT/python"
CACHE_ROOT="$DESKTOP_ROOT/.cache/python-runtime"
ASSET_JSON="$CACHE_ROOT/python-build-standalone-release.json"

case "$(uname -m)" in
  x86_64|amd64)
    TARGET_TRIPLE="x86_64-unknown-linux-gnu"
    ;;
  aarch64|arm64)
    TARGET_TRIPLE="aarch64-unknown-linux-gnu"
    ;;
  *)
    echo "Unsupported Linux architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

mkdir -p "$CACHE_ROOT" "$RESOURCES_ROOT"

if [ ! -f "$ASSET_JSON" ]; then
  curl -fsSL "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest" \
    -o "$ASSET_JSON"
fi

ASSET_URL="$(
  python3 - "$ASSET_JSON" "$PYTHON_VERSION_PREFIX" "$TARGET_TRIPLE" <<'PY'
import json
import re
import sys

release_path, version_prefix, target = sys.argv[1:]
data = json.load(open(release_path, encoding="utf-8"))
pattern = re.compile(
    rf"^cpython-{re.escape(version_prefix)}\.\d+\+\d+-{re.escape(target)}-install_only_stripped\.tar\.gz$"
)
assets = [
    asset
    for asset in data.get("assets", [])
    if pattern.match(asset.get("name", ""))
]
if not assets:
    fallback = re.compile(
        rf"^cpython-{re.escape(version_prefix)}\.\d+\+\d+-{re.escape(target)}-install_only\.tar\.gz$"
    )
    assets = [
        asset
        for asset in data.get("assets", [])
        if fallback.match(asset.get("name", ""))
    ]
if not assets:
    names = "\n".join(asset.get("name", "") for asset in data.get("assets", []))
    raise SystemExit(f"No python-build-standalone asset for {version_prefix} {target}.\n{names}")
print(assets[0]["browser_download_url"])
PY
)"

# #1895: Key the cache by the resolved asset filename (which encodes the exact
# CPython version + target triple + variant), not a fixed path. A fixed name
# would make the download guard reuse a stale interpreter after the version
# prefix, selected release, or architecture changes, silently packaging the
# wrong Python. Strip any URL query before taking the basename.
ASSET_NAME="$(basename "${ASSET_URL%%\?*}")"
TARBALL="$CACHE_ROOT/$ASSET_NAME"

if [ ! -f "$TARBALL" ]; then
  echo "Downloading $ASSET_URL"
  curl -fL "$ASSET_URL" -o "$TARBALL"
fi

rm -rf "$PYTHON_ROOT" "$CACHE_ROOT/extract"
mkdir -p "$CACHE_ROOT/extract"
tar -xzf "$TARBALL" -C "$CACHE_ROOT/extract"
mv "$CACHE_ROOT/extract/python" "$PYTHON_ROOT"

PYTHON_BIN="$PYTHON_ROOT/bin/python3"
"$PYTHON_BIN" -m pip install --no-warn-script-location --upgrade pip setuptools wheel
"$PYTHON_BIN" -m pip install --no-warn-script-location "$REPO_ROOT"
"$PYTHON_BIN" -c "import scistudio, fastapi, uvicorn, pty; print('SciStudio Linux portable Python ready:', scistudio.__version__)"

# #1775: The bundled runtime loads scistudio from resources/backend/src via
# PYTHONPATH (desktop/main.js runtimeEnv), and OTA patches load it from a
# userData directory. The pip install above is only needed to resolve the
# third-party dependencies into the interpreter; the scistudio package it also
# installs is a redundant second copy that wastes space and can shadow the
# source tree if PYTHONPATH ordering ever changes. Remove just scistudio,
# keeping its dependencies, so the source tree is the single source of truth.
"$PYTHON_BIN" -m pip uninstall -y scistudio
"$PYTHON_BIN" -c "import fastapi, uvicorn, pty; print('SciStudio Linux runtime deps verified (scistudio loads from source/OTA)')"

: > "$PYTHON_ROOT/.scistudio-python-runtime"
echo "Portable Linux Python runtime is ready at $PYTHON_ROOT"
