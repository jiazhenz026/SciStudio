#!/usr/bin/env bash
# Fetch portable git binary for macOS / Linux desktop bundle (ADR-039 §3.1)
#
# Downloads git's source release, builds a static binary per platform,
# installs into desktop/resources/git/. Called from the electron-builder
# pre-pack step (ADR-037 packaging pipeline).
#
# Updating the version
# --------------------
# 1. Bump GIT_VERSION below.
# 2. Run once; the SHA-256 check WILL fail.
# 3. Copy the printed hash into EXPECTED_SHA256.
# 4. Cross-verify against https://www.kernel.org/pub/software/scm/git/sha256sums.asc
# 5. Commit GIT_VERSION + EXPECTED_SHA256 together.

set -euo pipefail

# Pinned version. Bump quarterly per ADR §3.1 line 87.
GIT_VERSION="2.49.0"
GIT_TARBALL_URL="https://www.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz"

# SHA-256 of the published tarball.
#
# DESKTOP MAINTAINER ACTION REQUIRED before first release: this is a
# placeholder. Run the script with SCISTUDIO_SKIP_GIT_SHA_VERIFY=1, copy the
# computed hash printed to stderr, cross-verify it against
# https://www.kernel.org/pub/software/scm/git/sha256sums.asc (kernel.org's
# GPG-signed checksum manifest), then paste it here and commit. After that
# the script enforces integrity on every CI run. The bypass env var is for
# the one-time bring-up only — release pipelines must run with verification
# ON.
EXPECTED_SHA256="<PASTE-VERIFIED-SHA-256-HERE>"

# Destination — relative to script location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCE_ROOT="${SCRIPT_DIR}/../resources/git"

# 1. Idempotence.
if [ -x "${RESOURCE_ROOT}/bin/git" ] && \
   [ -f "${RESOURCE_ROOT}/VERSION" ] && \
   [ "$(cat "${RESOURCE_ROOT}/VERSION")" = "${GIT_VERSION}" ]; then
    echo "OK: git ${GIT_VERSION} already installed at ${RESOURCE_ROOT}"
    exit 0
fi

rm -rf "${RESOURCE_ROOT}"
mkdir -p "${RESOURCE_ROOT}"

PLATFORM="$(uname -s)"

# 2. Common: download + verify.
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

echo "Downloading ${GIT_TARBALL_URL} ..."
if command -v curl >/dev/null 2>&1; then
    curl -L --fail -o "git-${GIT_VERSION}.tar.xz" "$GIT_TARBALL_URL"
elif command -v wget >/dev/null 2>&1; then
    wget -O "git-${GIT_VERSION}.tar.xz" "$GIT_TARBALL_URL"
else
    echo "ERROR: neither curl nor wget available" >&2
    exit 1
fi

# Hash verify.
if command -v shasum >/dev/null 2>&1; then
    ACTUAL_SHA=$(shasum -a 256 "git-${GIT_VERSION}.tar.xz" | cut -d' ' -f1)
elif command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA=$(sha256sum "git-${GIT_VERSION}.tar.xz" | cut -d' ' -f1)
else
    echo "ERROR: no sha256 tool (shasum / sha256sum)" >&2
    exit 1
fi
if [ "${SCISTUDIO_SKIP_GIT_SHA_VERIFY:-}" = "1" ]; then
    echo "WARN: SCISTUDIO_SKIP_GIT_SHA_VERIFY=1, hash=${ACTUAL_SHA}"
elif [ "$ACTUAL_SHA" != "$EXPECTED_SHA256" ]; then
    echo "ERROR: SHA256 mismatch" >&2
    echo "  expected $EXPECTED_SHA256" >&2
    echo "  got      $ACTUAL_SHA" >&2
    echo "  Update EXPECTED_SHA256 in this script after verifying against kernel.org/sha256sums.asc" >&2
    exit 1
fi

tar -xJf "git-${GIT_VERSION}.tar.xz"
cd "git-${GIT_VERSION}"

# 3. Build per platform.
NCPU=2
if command -v nproc >/dev/null 2>&1; then NCPU="$(nproc)"; fi
if command -v sysctl >/dev/null 2>&1; then NCPU="$(sysctl -n hw.ncpu 2>/dev/null || echo 2)"; fi

case "$PLATFORM" in
    Darwin)
        echo "Building universal2 git for macOS (this can take several minutes) ..."
        export CFLAGS="-arch x86_64 -arch arm64 -mmacosx-version-min=10.15 -Os"
        export LDFLAGS="-arch x86_64 -arch arm64"
        make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 prefix="${RESOURCE_ROOT}" -j"${NCPU}"
        make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 prefix="${RESOURCE_ROOT}" install
        if command -v lipo >/dev/null 2>&1; then
            echo "Verifying universal2 ..."
            lipo -info "${RESOURCE_ROOT}/bin/git" || \
                echo "WARN: lipo verification skipped"
        fi
        ;;
    Linux)
        echo "Building static git for Linux ..."
        if ! command -v musl-gcc >/dev/null 2>&1; then
            echo "WARN: musl-gcc not found; building against system libc (will require glibc on target)" >&2
        else
            export CC=musl-gcc
        fi
        export CFLAGS="-static -Os"
        export LDFLAGS="-static"
        make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 NO_OPENSSL=1 \
             CURL_LDFLAGS="-static" \
             prefix="${RESOURCE_ROOT}" -j"${NCPU}"
        make NO_GETTEXT=1 NO_TCLTK=1 NO_PERL=1 NO_OPENSSL=1 \
             CURL_LDFLAGS="-static" \
             prefix="${RESOURCE_ROOT}" install
        if command -v ldd >/dev/null 2>&1; then
            if ldd "${RESOURCE_ROOT}/bin/git" 2>&1 | grep -qv 'not a dynamic'; then
                if ! ldd "${RESOURCE_ROOT}/bin/git" 2>&1 | grep -q 'statically linked\|not a dynamic'; then
                    echo "WARN: git is not statically linked (will work only on same libc)" >&2
                fi
            fi
        fi
        ;;
    *)
        echo "ERROR: unsupported platform: $PLATFORM" >&2
        exit 1
        ;;
esac

# 4. Smoke test.
"${RESOURCE_ROOT}/bin/git" --version

# 5. Strip unneeded files to reduce bundle size.
rm -rf "${RESOURCE_ROOT}/share/doc" \
       "${RESOURCE_ROOT}/share/locale" \
       "${RESOURCE_ROOT}/share/man" 2>/dev/null || true
find "${RESOURCE_ROOT}/libexec/git-core/" -maxdepth 1 -name 'git-cvs*' -delete 2>/dev/null || true
find "${RESOURCE_ROOT}/libexec/git-core/" -maxdepth 1 -name 'git-svn*' -delete 2>/dev/null || true
find "${RESOURCE_ROOT}/libexec/git-core/" -maxdepth 1 -name 'git-p4*' -delete 2>/dev/null || true

# 6. Sentinel.
echo -n "${GIT_VERSION}" > "${RESOURCE_ROOT}/VERSION"

echo "OK: git ${GIT_VERSION} installed at ${RESOURCE_ROOT}"
