param(
    [string]$Python = "$PSScriptRoot\..\.venv_step05_build\Scripts\python.exe",
    [string]$DistPath = 'dist'
)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$BasePrefix = & $Python -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Step05 build interpreter' }
$NativeDirs = @((Join-Path $BasePrefix 'Library\bin'), (Join-Path $BasePrefix 'DLLs'))
$BuildArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'CADtoCAE_Step05_AnalysisSetup', '--paths', 'src', '--add-data', 'config;config', '--add-data', 'src/cadtocae/*runtime.py;cadtocae', '--add-data', 'src/cadtocae/column_axis.py;cadtocae', '--collect-all', 'openpyxl')
# Conda-backed virtual environments may not expose their base DLL directory to
# PyInstaller. Read dependencies from the selected interpreter, never install
# into or modify the system Python. PATH is local to this build process.
foreach ($Dll in @('tcl86t.dll', 'tk86t.dll', 'ffi.dll')) {
    foreach ($Directory in $NativeDirs) {
        $Candidate = Join-Path $Directory $Dll
        if (Test-Path -LiteralPath $Candidate) {
            $BuildArgs += @('--add-binary', "$Candidate;.")
            break
        }
    }
}
$BuildArgs += @('--distpath', $DistPath, 'scripts/step05_analysis_script_gui.py')
$PriorPath = $env:PATH
try {
    $env:PATH = ($NativeDirs -join ';') + ';' + $PriorPath
    & $Python @BuildArgs
    if ($LASTEXITCODE -ne 0) { throw 'Step05 EXE build failed' }
} finally {
    $env:PATH = $PriorPath
}
$Package = Join-Path $DistPath 'CADtoCAE_Step05_AnalysisSetup'
Copy-Item -LiteralPath docs/step05_batch_usage.md -Destination (Join-Path $Package 'Step05_usage.md') -Force
Write-Host ('Development EXE: ' + (Join-Path $Package 'CADtoCAE_Step05_AnalysisSetup.exe'))
