$ErrorActionPreference = "Stop"

# Windows portable Python runtime.
#
# Historically this staged the python.org *embeddable* zip, but that ships a
# ``pythonXX._pth`` file which makes CPython IGNORE the ``PYTHONPATH``
# environment variable. The bundled app loads scistudio from
# ``resources/backend/src`` (and OTA patches from a userData dir) purely through
# ``PYTHONPATH`` (desktop/main.js runtimeEnv), so on Windows the embeddable
# runtime could never find scistudio ("No module named 'scistudio'") and OTA
# patches could never shadow the baseline. macOS never hit this because it uses
# astral-sh/python-build-standalone (a full CPython, no ``._pth``).
#
# This script now stages the SAME python-build-standalone distribution on
# Windows (``x86_64-pc-windows-msvc-install_only``) so PYTHONPATH behaves
# identically to macOS: base launch and OTA both work.

$PythonVersionPrefix = if ($env:SCISTUDIO_DESKTOP_PYTHON_VERSION_PREFIX) {
    $env:SCISTUDIO_DESKTOP_PYTHON_VERSION_PREFIX
} else {
    "3.12"
}
$TargetTriple = "x86_64-pc-windows-msvc"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $DesktopRoot "..")
$ResourcesRoot = Join-Path $DesktopRoot "resources"
$PythonRoot = Join-Path $ResourcesRoot "python"
$CacheRoot = Join-Path $DesktopRoot ".cache\python-runtime"
$AssetJson = Join-Path $CacheRoot "python-build-standalone-release.json"
$ExtractRoot = Join-Path $CacheRoot "extract"

function Reset-Directory {
    param([string] $Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ResourcesRoot | Out-Null

if (-not (Test-Path $AssetJson)) {
    Write-Host "Querying python-build-standalone latest release"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest" `
        -Headers @{ "User-Agent" = "scistudio-desktop-build" } -OutFile $AssetJson
}

$Release = Get-Content $AssetJson -Raw | ConvertFrom-Json
$Escaped = [Regex]::Escape($PythonVersionPrefix)
$StrippedPattern = "^cpython-$Escaped\.\d+\+\d+-$([Regex]::Escape($TargetTriple))-install_only_stripped\.tar\.gz$"
$PlainPattern = "^cpython-$Escaped\.\d+\+\d+-$([Regex]::Escape($TargetTriple))-install_only\.tar\.gz$"

$Asset = $Release.assets | Where-Object { $_.name -match $StrippedPattern } | Select-Object -First 1
if (-not $Asset) {
    $Asset = $Release.assets | Where-Object { $_.name -match $PlainPattern } | Select-Object -First 1
}
if (-not $Asset) {
    $names = ($Release.assets | ForEach-Object { $_.name }) -join "`n"
    throw "No python-build-standalone asset for $PythonVersionPrefix $TargetTriple.`n$names"
}

# Key the cached archive by the selected asset name (which embeds the CPython
# version + build date). Changing SCISTUDIO_DESKTOP_PYTHON_VERSION_PREFIX or a
# newer release selecting a different asset therefore picks a different cache
# file and re-downloads, instead of silently extracting a stale runtime from a
# fixed filename (#1807 review).
$Tarball = Join-Path $CacheRoot $Asset.name

if (-not (Test-Path $Tarball)) {
    Write-Host "Downloading $($Asset.browser_download_url)"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Asset.browser_download_url `
        -Headers @{ "User-Agent" = "scistudio-desktop-build" } -OutFile $Tarball
}

Reset-Directory $ExtractRoot
# Windows 10+ ships bsdtar as tar.exe; it handles gzip tarballs natively.
& tar.exe -xzf $Tarball -C $ExtractRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to extract $Tarball (exit $LASTEXITCODE)"
}

# python-build-standalone tarballs extract to a top-level "python" directory
# with python.exe at its root (Windows layout).
$ExtractedPython = Join-Path $ExtractRoot "python"
if (-not (Test-Path (Join-Path $ExtractedPython "python.exe"))) {
    throw "Expected python.exe under $ExtractedPython after extraction"
}
if (Test-Path $PythonRoot) {
    Remove-Item -LiteralPath $PythonRoot -Recurse -Force
}
Move-Item -LiteralPath $ExtractedPython -Destination $PythonRoot

$PythonExe = Join-Path $PythonRoot "python.exe"

# install_only ships pip; no get-pip bootstrap needed.
& $PythonExe -m pip install --no-warn-script-location --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip bootstrap upgrade failed with exit code $LASTEXITCODE"
}

& $PythonExe -m pip install --no-warn-script-location $RepoRoot
if ($LASTEXITCODE -ne 0) {
    throw "SciStudio runtime dependency install failed with exit code $LASTEXITCODE"
}

& $PythonExe -c "import scistudio, fastapi, uvicorn, winpty; print('SciStudio portable Python ready:', scistudio.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Portable Python runtime verification failed with exit code $LASTEXITCODE"
}

# #1775: The bundled runtime loads scistudio from resources/backend/src via
# PYTHONPATH (desktop/main.js runtimeEnv), and OTA patches load it from a
# userData directory. The pip install above is only needed to resolve the
# third-party dependencies into the interpreter; the scistudio package it also
# installs is a redundant second copy that wastes space and can shadow the
# source tree if PYTHONPATH ordering ever changes. Remove just scistudio,
# keeping its dependencies, so the source tree is the single source of truth.
& $PythonExe -m pip uninstall -y scistudio
if ($LASTEXITCODE -ne 0) {
    throw "Failed to remove the redundant bundled scistudio package (exit $LASTEXITCODE)"
}

& $PythonExe -c "import fastapi, uvicorn, winpty; print('SciStudio runtime deps verified (scistudio loads from source/OTA)')"
if ($LASTEXITCODE -ne 0) {
    throw "Portable Python runtime dependency verification failed with exit code $LASTEXITCODE"
}

"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $PythonRoot ".scistudio-python-runtime")
Write-Host "Portable Python runtime is ready at $PythonRoot"
