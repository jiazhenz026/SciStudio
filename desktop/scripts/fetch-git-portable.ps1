# Fetch portable git binary for Windows desktop bundle (ADR-039 §3.1)
#
# Downloads the official MinGit distribution from Git for Windows
# releases, verifies SHA-256, extracts into desktop/resources/git/.
# Called from the electron-builder pre-pack step (ADR-037 packaging
# pipeline). Pinned version bumped quarterly per ADR §3.1 lines 84-88
# and CVE advisories per §7.3 line 578.
#
# Why MinGit and not full Git for Windows
# ---------------------------------------
# - MinGit is the official trimmed portable distribution maintained by
#   the same team. ~30 MB vs ~250 MB. No installer.
# - The busybox-64-bit variant ships a tiny BusyBox for the shell
#   helpers git invokes internally.
#
# Updating the version
# --------------------
# 1. Bump $GitVersion below.
# 2. Run this script once interactively; the SHA-256 check WILL fail.
# 3. Copy the actual hash printed by the failure and paste it into
#    $ExpectedSha256.
# 4. Verify the hash matches the one published on
#    https://github.com/git-for-windows/git/releases for the same tag.
# 5. Commit the updated $GitVersion + $ExpectedSha256 together.

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Pinned version. Bump this string + update $ExpectedSha256 when
# refreshing per ADR §3.1 line 87.
$GitVersion = "2.49.0"
$BusyboxMinGitUrl = "https://github.com/git-for-windows/git/releases/download/v${GitVersion}.windows.1/MinGit-${GitVersion}-busybox-64-bit.zip"

# SHA-256 of the published archive.
#
# DESKTOP MAINTAINER ACTION REQUIRED before first release: this is a
# placeholder. Run with $env:SCISTUDIO_SKIP_GIT_SHA_VERIFY = "1", copy the
# computed hash printed to stderr, cross-verify against Git for Windows's
# published checksums.txt.gpg, then paste it here and commit. After that
# the script enforces integrity on every CI run. The bypass env var is for
# the one-time bring-up only — release pipelines must run with verification
# ON.
$ExpectedSha256 = "<PASTE-VERIFIED-SHA-256-HERE>"

# Destination — relative to script location.
$ResourceRoot = Join-Path $PSScriptRoot "..\resources\git"
$VersionFile = Join-Path $ResourceRoot "VERSION"
$BinaryPath = Join-Path $ResourceRoot "cmd\git.exe"
$AltBinaryPath = Join-Path $ResourceRoot "mingw64\bin\git.exe"

# 1. Idempotence: skip if already at the right version.
if (-not $Force.IsPresent) {
    if ((Test-Path $VersionFile) -and (Test-Path $BinaryPath -PathType Leaf -ErrorAction SilentlyContinue)) {
        $cachedVersion = Get-Content $VersionFile -Raw -ErrorAction SilentlyContinue
        if ($cachedVersion -and ($cachedVersion.Trim() -eq $GitVersion)) {
            Write-Host "OK: MinGit $GitVersion already installed at $ResourceRoot"
            exit 0
        }
    }
}

# 2. Ensure destination exists; wipe stale contents on version mismatch.
if (Test-Path $ResourceRoot) {
    Remove-Item -Recurse -Force $ResourceRoot
}
New-Item -ItemType Directory -Force -Path $ResourceRoot | Out-Null

# 3. Enforce TLS 1.2 on older Windows 10.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Warning "Could not set TLS 1.2: $($_.Exception.Message)"
}

# 4. Download.
$tempZip = Join-Path $env:TEMP "MinGit-$GitVersion-$([System.Guid]::NewGuid().ToString('N')).zip"
Write-Host "Downloading $BusyboxMinGitUrl ..."
try {
    Invoke-WebRequest -Uri $BusyboxMinGitUrl -OutFile $tempZip -UseBasicParsing
} catch {
    throw "Download failed: $($_.Exception.Message). Check internet connection or proxy settings."
}

try {
    # 5. SHA-256 verify (unless explicitly skipped).
    $hash = (Get-FileHash -Path $tempZip -Algorithm SHA256).Hash
    if ($env:SCISTUDIO_SKIP_GIT_SHA_VERIFY -eq "1") {
        Write-Warning "SCISTUDIO_SKIP_GIT_SHA_VERIFY=1: not verifying $hash"
    } elseif ($hash -ne $ExpectedSha256) {
        throw "SHA256 mismatch:`n  expected $ExpectedSha256`n  got      $hash`nUpdate `$ExpectedSha256 in this script after verifying against Git for Windows release checksums."
    }

    # 6. Extract.
    Write-Host "Extracting to $ResourceRoot ..."
    Expand-Archive -Path $tempZip -DestinationPath $ResourceRoot -Force

    # 7. Verify binary exists.
    if (-not (Test-Path $BinaryPath)) {
        if (Test-Path $AltBinaryPath) {
            $BinaryPath = $AltBinaryPath
        } else {
            throw "git.exe not found at $BinaryPath or $AltBinaryPath after extraction."
        }
    }

    # 8. Smoke test.
    $versionOutput = & $BinaryPath --version
    if ($LASTEXITCODE -ne 0) {
        throw "git --version returned exit code $LASTEXITCODE"
    }
    Write-Host "Smoke test passed: $versionOutput"

    # 9. Write sentinel.
    $GitVersion | Out-File -FilePath $VersionFile -Encoding ascii -NoNewline
} finally {
    Remove-Item -ErrorAction SilentlyContinue -Force $tempZip
}

Write-Host "OK: MinGit $GitVersion installed at $ResourceRoot"
