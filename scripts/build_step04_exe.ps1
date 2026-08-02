param(
    [string]$Python = "python",
    [string]$Name = "CADtoCAE_Step04_AssemblyScript"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "Building Step04 GUI executable from $RepoRoot"

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "This project should be packaged with Python 3.10 or newer."
    Write-Host "Current launcher '$Python' is too old. Pass a newer Python path, for example:"
    Write-Host "  .\scripts\build_step04_exe.ps1 -Python C:\Python312\python.exe"
    exit 2
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller is not installed in this Python environment."
    Write-Host "Install build dependencies first:"
    Write-Host "  $Python -m pip install -r requirements.txt -r requirements-build.txt"
    exit 2
}

$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", $Name,
    "--paths", "src",
    "--paths", "scripts",
    "--add-data", "config;config",
    "--collect-all", "openpyxl",
    "scripts\step04_assembly_script_gui.py"
)

& $Python @PyInstallerArgs

$ReadmeSource = Join-Path $RepoRoot "docs\step04_assembly_script_usage.md"
$ReadmeTargetDir = Join-Path $RepoRoot "dist\$Name"
if (Test-Path $ReadmeSource) {
    New-Item -ItemType Directory -Force -Path $ReadmeTargetDir | Out-Null
    Copy-Item -LiteralPath $ReadmeSource -Destination (Join-Path $ReadmeTargetDir "Step04_usage.md") -Force
}

Write-Host ""
Write-Host "Done."
Write-Host "Executable:"
Write-Host "  dist\$Name\$Name.exe"
