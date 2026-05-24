$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $DesktopRoot "..")
$ResourcesRoot = Join-Path $DesktopRoot "resources"
$FrontendDist = Join-Path $RepoRoot "frontend\dist"
$FrontendTarget = Join-Path $ResourcesRoot "frontend"
$AppRoot = Join-Path $ResourcesRoot "app"
$SrcTarget = Join-Path $AppRoot "src"
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
Reset-Directory $FrontendTarget
Copy-Item -Path (Join-Path $FrontendDist "*") -Destination $FrontendTarget -Recurse -Force

Ensure-Directory $AppRoot
Reset-Directory $SrcTarget
Copy-Item -Path (Join-Path $SrcSource "*") -Destination $SrcTarget -Recurse -Force

Ensure-Directory (Join-Path $ResourcesRoot "packages")
Ensure-Directory (Join-Path $ResourcesRoot "git")
Ensure-Directory (Join-Path $ResourcesRoot "python")

"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "packages\.gitkeep")
"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "git\.gitkeep")
"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $ResourcesRoot "python\.gitkeep")

@"
Place hard-installed SciStudio source packages here for the ADR-037 MVP.

Expected shape:

packages/
  scistudio-blocks-example/
    pyproject.toml
    src/scistudio_blocks_example/__init__.py

The MVP does not install dependencies. Packages placed here must be compatible
with the bundled Python environment.
"@ | Set-Content -Encoding ASCII (Join-Path $ResourcesRoot "packages\README.md")

Write-Host "Staged desktop resources under $ResourcesRoot"
