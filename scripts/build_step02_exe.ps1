param(
    [string]$Python = "python",
    [string]$Name = "CADtoCAE_Step02_PartScript"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "Building Step02 GUI executable from $RepoRoot"

$BuildRoot = Join-Path $RepoRoot "build\step02"
$SpecRoot = Join-Path $BuildRoot "spec"
$WorkRoot = Join-Path $BuildRoot "work"
$ConfigSource = Join-Path $RepoRoot "config"
New-Item -ItemType Directory -Force -Path $SpecRoot, $WorkRoot | Out-Null

function Invoke-PythonCheck {
    param(
        [string[]]$Arguments
    )
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Python @Arguments 2>$null
    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    return $ExitCode
}

$PythonVersionStatus = Invoke-PythonCheck -Arguments @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)")
if ($PythonVersionStatus -ne 0) {
    Write-Host "This project should be packaged with Python 3.10 or newer."
    Write-Host "Current launcher '$Python' is too old. Pass a newer Python path, for example:"
    Write-Host "  .\scripts\build_step02_exe.ps1 -Python C:\Python312\python.exe"
    exit 2
}

$PyInstallerStatus = Invoke-PythonCheck -Arguments @("-c", "import PyInstaller")
if ($PyInstallerStatus -ne 0) {
    Write-Host "PyInstaller is not installed in this Python environment."
    Write-Host "Install build dependencies first:"
    Write-Host "  $Python -m pip install -r requirements.txt -r requirements-build.txt"
    exit 2
}

$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", $Name,
    "--specpath", $SpecRoot,
    "--workpath", $WorkRoot,
    "--distpath", "dist",
    "--paths", "src",
    "--paths", "scripts",
    "--add-data", "$ConfigSource;config",
    "--collect-all", "openpyxl",
    "scripts\step02_part_script_gui.py"
)

& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$ReadmeSource = Join-Path $RepoRoot "docs\step02_part_script_usage.md"
$ReadmeTargetDir = Join-Path $RepoRoot "dist\$Name"
if (Test-Path $ReadmeSource) {
    New-Item -ItemType Directory -Force -Path $ReadmeTargetDir | Out-Null
    Copy-Item -LiteralPath $ReadmeSource -Destination (Join-Path $ReadmeTargetDir "Step02_usage.md") -Force
}

Write-Host ""
Write-Host "Done."
Write-Host "Executable:"
Write-Host "  dist\$Name\$Name.exe"
