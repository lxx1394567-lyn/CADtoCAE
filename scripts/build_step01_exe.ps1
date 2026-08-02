param(
    [string]$Python = "python",
    [string]$Name = "CADtoCAE_Step01_MaterialTable"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "Building Step01 GUI executable from $RepoRoot"

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "This project should be packaged with Python 3.10 or newer."
    Write-Host "Current launcher '$Python' is too old. Pass a newer Python path, for example:"
    Write-Host "  .\scripts\build_step01_exe.ps1 -Python C:\Python312\python.exe"
    exit 2
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller is not installed in this Python environment."
    Write-Host "Install build dependencies first:"
    Write-Host "  $Python -m pip install -r requirements.txt pyinstaller"
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
    "--add-data", "config;config",
    "--collect-all", "openpyxl",
    "--collect-all", "rapidocr_onnxruntime",
    "--collect-all", "onnxruntime",
    "scripts\step01_pdf_material_gui.py"
)

& $Python @PyInstallerArgs

Write-Host ""
Write-Host "Done."
Write-Host "Executable:"
Write-Host "  dist\$Name\$Name.exe"
Write-Host ""
Write-Host "Input is PNG/JPG material table screenshots. RapidOCR is bundled when installed in the build environment."
