#!/usr/bin/env bash
# Fetch portable git binary for macOS / Linux desktop bundle (ADR-039 §3.1)
#
# Downloads git's source release, builds a static binary per platform,
# installs into desktop/resources/git/. Called from the electron-builder
# pre-pack step (ADR-037 packaging pipeline).
#
# Per ADR §3.1 lines 84-88:
# - macOS: universal2 build (Intel + Apple Silicon) using clang with
#   ``-arch x86_64 -arch arm64`` flags; size ~25 MB.
# - Linux: static musl-libc build (no dynamic dependencies), size ~25 MB.
#
# Why source build, not Homebrew / apt
# ------------------------------------
# - We need a self-contained binary that runs on machines without git
#   installed. Homebrew's git pulls dynamic libs we cannot ship.
# - Source build pins exactly the version we test against, eliminating
#   "works on my machine" variance across distros.
# - Quarterly refresh per ADR §3.1 line 87 + CVE tracking per §7.3
#   line 578.
#
# IMPORTANT: ADR-037 packaging pipeline integration
# -------------------------------------------------
# If ``desktop/package.json`` does not exist yet (ADR-037 work pending):
# the electron-builder bundle config must include
# ``desktop/resources/git/`` in its assets list. This is documented in
# the cascade checklist row D39-2.2a; coordinate with ADR-037 implementer.
#
# Skeleton phase (D39-2.2a)
# -------------------------
# Body raises an error. Impl agent (D39-2.2b) implements per the steps
# below.

set -euo pipefail

# Pinned version. Bump quarterly per ADR §3.1 line 87.
GIT_VERSION="2.49.0"
GIT_TARBALL_URL="https://www.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz"

# SHA-256 of the published tarball. Verify on first download with
# ``shasum -a 256 git-${GIT_VERSION}.tar.xz`` then paste here. Mismatch
# = poisoned mirror; abort.
EXPECTED_SHA256="<PASTE-VERIFIED-SHA-256-HERE-D39-2.2b>"

# Destination — relative to repo root. Verified against ADR §5.1
# line 432 and §3.1 line 57.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCE_ROOT="${SCRIPT_DIR}/../resources/git"

# Implementation steps (D39-2.2b)
# -------------------------------
#
# 1. Idempotence check:
#    if [ -x "${RESOURCE_ROOT}/bin/git" ] && \
#       [ "$(cat "${RESOURCE_ROOT}/VERSION" 2>/dev/null)" = "${GIT_VERSION}" ]; then
#        echo "OK: git ${GIT_VERSION} already installed"
#        exit 0
#    fi
#
# 2. Detect platform:
#    PLATFORM=$(uname -s)
#    case "$PLATFORM" in
#        Darwin) build_macos ;;
#        Linux)  build_linux ;;
#        *) echo "Unsupported platform: $PLATFORM"; exit 1 ;;
#    esac
#
# 3. Common: download + verify
#    TMPDIR=$(mktemp -d)
#    trap "rm -rf $TMPDIR" EXIT
#    cd "$TMPDIR"
#    curl -L -o "git-${GIT_VERSION}.tar.xz" "$GIT_TARBALL_URL"
#    actual_sha=$(shasum -a 256 "git-${GIT_VERSION}.tar.xz" | cut -d' ' -f1)
#    if [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
#        echo "SHA256 mismatch: expected $EXPECTED_SHA256 got $actual_sha"
#        exit 1
#    fi
#    tar -xJf "git-${GIT_VERSION}.tar.xz"
#    cd "git-${GIT_VERSION}"
#
# 4. build_macos() — universal2:
#    export CFLAGS="-arch x86_64 -arch arm64 -mmacosx-version-min=10.15"
#    export LDFLAGS="-arch x86_64 -arch arm64"
#    make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 prefix="$RESOURCE_ROOT" -j$(sysctl -n hw.ncpu)
#    make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 prefix="$RESOURCE_ROOT" install
#    # Verify universal2:
#    lipo -info "$RESOURCE_ROOT/bin/git"
#    # Should print: "Architectures in the fat file: ... x86_64 arm64"
#
# 5. build_linux() — static musl:
#    # Requires musl-gcc toolchain in CI image; document in
#    # .github/workflows/build-desktop.yml (ADR-037 territory).
#    export CC=musl-gcc
#    export CFLAGS="-static -Os"
#    export LDFLAGS="-static"
#    make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 NO_OPENSSL=1 \
#         CURL_LDFLAGS="-static" \
#         prefix="$RESOURCE_ROOT" -j$(nproc)
#    make ... install
#    # Verify static linking:
#    if ldd "$RESOURCE_ROOT/bin/git" 2>&1 | grep -v 'not a dynamic'; then
#        echo "ERROR: git is not statically linked"; exit 1
#    fi
#
# 6. Smoke test:
#    "$RESOURCE_ROOT/bin/git" --version
#    # Must print "git version ${GIT_VERSION}" (allow patch-level drift)
#
# 7. Write sentinel:
#    echo "$GIT_VERSION" > "$RESOURCE_ROOT/VERSION"
#
# 8. Strip unneeded files to reduce bundle size:
#    rm -rf "$RESOURCE_ROOT/share/doc" \
#           "$RESOURCE_ROOT/share/locale" \
#           "$RESOURCE_ROOT/share/man" \
#           "$RESOURCE_ROOT/libexec/git-core/git-cvs"* \
#           "$RESOURCE_ROOT/libexec/git-core/git-svn"* \
#           "$RESOURCE_ROOT/libexec/git-core/git-p4"*
#    # SciEasy never uses cvs/svn/p4 bridges.
#
# 9. Print "OK: git ${GIT_VERSION} installed at $RESOURCE_ROOT"
#
# Edge cases
# ----------
# - Network failure → curl exits non-zero; set -e propagates.
# - SHA mismatch → explicit exit 1 (step 3).
# - Build failure (missing toolchain) → make exits non-zero;
#   print helpful "missing musl-gcc?" hint in trap on ERR.
# - macOS code-signing (notarization) — out of scope for this script;
#   the electron-builder post-pack step handles it. The binary may need
#   ad-hoc signing (``codesign --force --sign -`` ) to run from the
#   bundle on Apple Silicon; document in ADR-037 once finalized.
# - Pre-existing partial install — remove $RESOURCE_ROOT contents at
#   step 1 if VERSION mismatches, before re-extracting.
#
# ADR references
# --------------
# - §3.1 lines 56-88 (macOS / Linux build strategy).
# - §5.1 line 432 (desktop/resources/git/ destination).
# - §5.2 line 483 (electron-builder bundle entry — must include).
# - §7.3 line 578 (quarterly refresh + CVE tracking).

echo "D39-2.2a skeleton — body filled by D39-2.2b. See comments above for the implementation algorithm." >&2
exit 1
