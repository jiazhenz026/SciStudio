$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $DesktopRoot "..")
$ResourcesRoot = Join-Path $DesktopRoot "resources"
$FrontendDist = Join-Path $RepoRoot "frontend\dist"
$FrontendTarget = Join-Path $ResourcesRoot "frontend"
$LegacyAppRoot = Join-Path $ResourcesRoot "app"
$BackendRoot = Join-Path $ResourcesRoot "backend"
$SrcTarget = Join-Path $BackendRoot "src"
$SrcSource = Join-Path $RepoRoot "src"

function Ensure-Directory {
    param([string] $Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Reset-Directory {
    param([string] $Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

Write-Host "Building frontend..."
npm --prefix (Join-Path $RepoRoot "frontend") run build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $FrontendDist)) {
    throw "Expected frontend build output at $FrontendDist"
}

Ensure-Directory $ResourcesRoot
if (Test-Path $LegacyAppRoot) {
    Remove-Item -LiteralPath $LegacyAppRoot -Recurse -Force
}
Reset-Directory $FrontendTarget
Copy-Item -Path (Join-Path $FrontendDist "*") -Destination $FrontendTarget -Recurse -Force

Ensure-Directory $BackendRoot
Reset-Directory $SrcTarget
Copy-Item -Path (Join-Path $SrcSource "*") -Destination $SrcTarget -Recurse -Force

# #1775: Drop build metadata that may ride along from a local editable install.
# It is not needed at runtime (scistudio loads from this source tree on
# PYTHONPATH) and only leaks paths into the bundle and OTA snapshot.
$EggInfo = Join-Path $SrcTarget "scistudio.egg-info"
if (Test-Path $EggInfo) {
    Remove-Item -LiteralPath $EggInfo -Recurse -Force
}

# Refresh the packaged SPA (scistudio/api/static) from the frontend build we just
# produced. This is the ONLY frontend a bundled desktop app serves
# (scistudio.api.app._resolve_spa_static_dir, SCISTUDIO_BUNDLED=1). The repo copy
# is a gitignored build artifact that the wheel build hook
# (setup.py _has_prebuilt_spa) skips refreshing once populated, so it can go
# stale and ship an old SPA. Overwriting the staged copy guarantees the installer
# always carries the current frontend. Mirrors stage-resources.sh. (#1747)
$StagedSpa = Join-Path $SrcTarget "scistudio\api\static"
Reset-Directory $StagedSpa
Copy-Item -Path (Join-Path $FrontendDist "*") -Destination $StagedSpa -Recurse -Force

Ensure-Directory (Join-Path $ResourcesRoot "packages")
Ensure-Directory (Join-Path $ResourcesRoot "git")
Ensure-Directory (Join-Path $ResourcesRoot "python")

"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "packages\.gitkeep")
"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "git\.gitkeep")
"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "python\.gitkeep")

@"
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
"@ | Set-Content -Encoding ASCII (Join-Path $ResourcesRoot "packages\README.md")

# #1775: Stamp the OTA channel config the desktop client reads at launch
# (main.js loadOtaConfig). A local/dev build leaves SCISTUDIO_OTA_CHANNEL unset
# and gets OTA disabled, so a developer testing a local build is never disturbed
# or overwritten by a published patch. A release build sets the channel (and
# optionally the manifest URL) to enable launch-time update checks. Mirrors
# stage-resources.sh.
$OtaChannel = $env:SCISTUDIO_OTA_CHANNEL
$OtaConfigPath = Join-Path $ResourcesRoot "ota-config.json"
if (-not [string]::IsNullOrEmpty($OtaChannel)) {
    $OtaManifestUrl = if (-not [string]::IsNullOrEmpty($env:SCISTUDIO_OTA_MANIFEST_URL)) {
        $env:SCISTUDIO_OTA_MANIFEST_URL
    } else {
        "https://github.com/jiazhenz026/SciStudio/releases/download/ota-$OtaChannel/manifest.json"
    }
    $OtaConfig = [ordered]@{ enabled = $true; channel = $OtaChannel; manifestUrl = $OtaManifestUrl }
    ($OtaConfig | ConvertTo-Json) | Set-Content -Encoding ASCII $OtaConfigPath
    Write-Host "OTA enabled for channel '$OtaChannel' (manifest: $OtaManifestUrl)"
} else {
    $OtaConfig = [ordered]@{ enabled = $false; channel = "dev"; manifestUrl = $null }
    ($OtaConfig | ConvertTo-Json) | Set-Content -Encoding ASCII $OtaConfigPath
    Write-Host "OTA disabled (local/dev build; set SCISTUDIO_OTA_CHANNEL to enable)"
}

Write-Host "Staged desktop resources under $ResourcesRoot"
