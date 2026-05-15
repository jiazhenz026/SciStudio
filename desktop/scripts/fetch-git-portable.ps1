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
#   the same team. ~30 MB vs ~250 MB. No installer, no bash, no Perl
#   scripting layer — we just need git.exe + libs.
# - The busybox-64-bit variant ships a tiny BusyBox for the few shell
#   helpers git internally invokes (e.g. ``git pull --rebase`` calls
#   ``sh``). Acceptable for SciEasy's use case.
#
# Skeleton phase (D39-2.2a)
# -------------------------
# Throws "not implemented". Impl agent (D39-2.2b) fills the body per
# the steps documented below.

# Pinned version. Bump this string + update $ExpectedSha256 when
# refreshing per ADR §3.1 line 87.
$GitVersion = "2.49.0"
$BusyboxMinGitUrl = "https://github.com/git-for-windows/git/releases/download/v${GitVersion}.windows.1/MinGit-${GitVersion}-busybox-64-bit.zip"

# SHA-256 of the published archive — verify by downloading once
# manually and running Get-FileHash, then paste here. Mismatch =
# poisoned mirror; abort.
$ExpectedSha256 = "<PASTE-VERIFIED-SHA-256-HERE-D39-2.2b>"

# Destination — relative to repo root. Verified against ADR §5.1
# line 432 and §3.1 line 57.
$ResourceRoot = Join-Path $PSScriptRoot "..\resources\git"

# Implementation steps (D39-2.2b)
# -------------------------------
# 1. Skip if $ResourceRoot already contains bin\git.exe AND the
#    cached version (read from a sentinel file VERSION written below)
#    matches $GitVersion. This makes the script idempotent for CI.
#
# 2. Create $ResourceRoot if absent.
#
# 3. $tempZip = Join-Path $env:TEMP "MinGit-${GitVersion}.zip"
#
# 4. Invoke-WebRequest -Uri $BusyboxMinGitUrl -OutFile $tempZip
#    -UseBasicParsing
#    (TLS 1.2 enforced on older Win10 via:
#      [Net.ServicePointManager]::SecurityProtocol = `
#        [Net.SecurityProtocolType]::Tls12)
#
# 5. Verify SHA-256:
#      $hash = (Get-FileHash -Path $tempZip -Algorithm SHA256).Hash
#      if ($hash -ne $ExpectedSha256) {
#          Remove-Item $tempZip
#          throw "SHA256 mismatch: expected $ExpectedSha256 got $hash"
#      }
#
# 6. Expand-Archive -Path $tempZip -DestinationPath $ResourceRoot
#    -Force
#
# 7. Verify the binary exists:
#      $binPath = Join-Path $ResourceRoot "cmd\git.exe"
#      OR Join-Path $ResourceRoot "mingw64\bin\git.exe"
#      (MinGit layout — exact path varies; the GitBinary locator
#       handles both. Document the final path here once verified.)
#
# 8. Smoke test:
#      & $binPath --version
#    (must print "git version $GitVersion" or close)
#
# 9. Write a sentinel:
#      "$GitVersion" | Out-File (Join-Path $ResourceRoot "VERSION") `
#        -Encoding ascii -NoNewline
#
# 10. Remove $tempZip.
#
# 11. Print "OK: MinGit $GitVersion installed at $ResourceRoot"
#
# Edge cases
# ----------
# - Network failure — propagate Invoke-WebRequest exception with a
#   clear hint ("Check internet connection or proxy settings").
# - SHA mismatch — refuse to extract and clean up.
# - Path with spaces in repo location — quote everything.
# - Existing extraction with WRONG version — delete $ResourceRoot
#   contents before re-extracting (step 6 with -Force handles this
#   but be paranoid about partial files).
#
# ADR references
# --------------
# - §3.1 lines 57-88 (Windows MinGit sourcing strategy).
# - §5.1 line 432 (desktop/resources/git/ destination).
# - §5.2 line 483 (electron-builder bundle entry).
# - §7.3 line 578 (quarterly refresh + CVE tracking).

throw "D39-2.2a skeleton — body filled by D39-2.2b. See comments above for the implementation algorithm."
