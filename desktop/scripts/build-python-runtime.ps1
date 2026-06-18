$ErrorActionPreference = "Stop"

$PythonVersion = if ($env:SCISTUDIO_DESKTOP_PYTHON_VERSION) { $env:SCISTUDIO_DESKTOP_PYTHON_VERSION } else { "3.12.10" }
$PythonTag = $PythonVersion
$PythonMinor = ($PythonVersion.Split(".")[0..1] -join "")

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $DesktopRoot "..")
$ResourcesRoot = Join-Path $DesktopRoot "resources"
$PythonRoot = Join-Path $ResourcesRoot "python"
$CacheRoot = Join-Path $DesktopRoot ".cache\python-runtime"
$ZipPath = Join-Path $CacheRoot "python-$PythonTag-embed-amd64.zip"
$GetPipPath = Join-Path $CacheRoot "get-pip.py"
$PythonUrl = "https://www.python.org/ftp/python/$PythonTag/python-$PythonTag-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

function Reset-Directory {
    param([string] $Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Download-If-Missing {
    param(
        [string] $Url,
        [string] $Path
    )
    if (Test-Path $Path) {
        return
    }
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Path
}

New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ResourcesRoot | Out-Null

Download-If-Missing -Url $PythonUrl -Path $ZipPath
Download-If-Missing -Url $GetPipUrl -Path $GetPipPath

Reset-Directory $PythonRoot
Expand-Archive -LiteralPath $ZipPath -DestinationPath $PythonRoot -Force

$PthPath = Join-Path $PythonRoot "python$PythonMinor._pth"
if (-not (Test-Path $PthPath)) {
    throw "Expected embedded Python path file at $PthPath"
}

$PthLines = Get-Content $PthPath
$PthLines = $PthLines | ForEach-Object {
    if ($_ -eq "#import site") { "import site" } else { $_ }
}
if ($PthLines -notcontains "Lib\site-packages") {
    $PthLines = @($PthLines[0..($PthLines.Length - 2)] + "Lib\site-packages" + $PthLines[-1])
}
$PthLines | Set-Content -Encoding ASCII $PthPath

$PythonExe = Join-Path $PythonRoot "python.exe"
& $PythonExe $GetPipPath --no-warn-script-location
if ($LASTEXITCODE -ne 0) {
    throw "get-pip.py failed with exit code $LASTEXITCODE"
}

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

"" | Set-Content -NoNewline -Encoding ASCII (Join-Path $PythonRoot ".scistudio-python-runtime")
Write-Host "Portable Python runtime is ready at $PythonRoot"
