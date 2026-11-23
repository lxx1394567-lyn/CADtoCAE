param(
    [string]$Python = '',
    [Parameter(Mandatory=$true)][string]$SmokeFolder
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $Root
if (!$Python) { $Python = Join-Path $Root '.venv_step06_build\Scripts\python.exe' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$SmokeFolder = (Resolve-Path -LiteralPath $SmokeFolder).Path
$Name = 'CADtoCAE_Step06_HoleSetup'
$Release = Join-Path $Root "dist\$Name"
$ReleaseExe = Join-Path $Release "$Name.exe"
function Assert-Closed {
    $Running = Get-Process -Name $Name -ErrorAction SilentlyContinue
    if ($Running) { throw 'Step06 EXE is running. Please close CADtoCAE_Step06_HoleSetup.exe and retry; fixed release was not replaced.' }
}
Assert-Closed
$Stage = Join-Path $Root ('build\step06-release-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $Stage | Out-Null
$BasePrefix = & $Python -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Step06 build interpreter' }
$NativeDirs = @((Join-Path $BasePrefix 'Library\bin'), (Join-Path $BasePrefix 'DLLs'))
$BuildArgs = @('-m','PyInstaller','--clean','--noconfirm','--onedir','--windowed','--name',$Name,'--paths',(Join-Path $Root 'src'),'--add-data',((Join-Path $Root 'config')+';config'),'--collect-all','openpyxl')
foreach ($Module in @('hole_runtime','hoop_hole_runtime','beam_brace_tie_runtime','analysis_runtime','hole_transforms','hole_derived_runtime','analysis_geometry','purlin_bolt_preset_runtime','connector_b1_runtime','connector_groups_runtime','support_beam_connector_runtime','connector_integration_runtime','connector_geometry','connector_b1_plan','connector_groups','support_beam_connector')) {
    $BuildArgs += @('--add-data', ((Join-Path $Root "src/cadtocae/$Module.py")+';cadtocae'))
}
foreach ($Dll in @('tcl86t.dll','tk86t.dll','ffi.dll')) {
    foreach ($Directory in $NativeDirs) {
        $Candidate = Join-Path $Directory $Dll
        if (Test-Path -LiteralPath $Candidate) { $BuildArgs += @('--add-binary', "$Candidate;."); break }
    }
}
$BuildArgs += @('--distpath', (Join-Path $Stage 'dist'),'--workpath',(Join-Path $Stage 'work'),'--specpath',$Stage,'scripts/step06_hole_setup_gui.py')
$PriorPath = $env:PATH
$PriorCache = $env:PYINSTALLER_CONFIG_DIR
try {
    $env:PATH = ($NativeDirs -join ';') + ';' + $PriorPath
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $Stage 'cache'
    & $Python @BuildArgs
    if ($LASTEXITCODE -ne 0) { throw 'Step06 EXE build failed; fixed release unchanged' }
} finally { $env:PATH = $PriorPath; $env:PYINSTALLER_CONFIG_DIR = $PriorCache }
$Package = Join-Path $Stage "dist\$Name"
Copy-Item -LiteralPath docs/step06_hole_setup.md -Destination (Join-Path $Package 'Step06_usage.md')
$SmokeReport = Join-Path $Stage 'smoke.json'
$Process = Start-Process -FilePath (Join-Path $Package "$Name.exe") -ArgumentList @('--ui-smoke','--smoke-folder',('"'+$SmokeFolder+'"'),'--report',('"'+$SmokeReport+'"')) -WindowStyle Hidden -PassThru -Wait
if ($Process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $SmokeReport)) { throw 'Packaged GUI smoke failed; fixed release unchanged' }
$Smoke = Get-Content -LiteralPath $SmokeReport -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Smoke.status -ne 'SUCCESS') { throw 'Packaged GUI smoke failed; fixed release unchanged' }
Assert-Closed
$Backup = Join-Path $Stage 'previous-release'
# Verify all final move targets are inside this worktree before touching the release.
foreach ($Target in @($Release,$Package,$Backup)) {
    $Absolute = [IO.Path]::GetFullPath($Target)
    if (!$Absolute.StartsWith($Root + '\',[StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe release target: $Absolute" }
}
$HadRelease = Test-Path -LiteralPath $Release
if ($HadRelease) { Move-Item -LiteralPath $Release -Destination $Backup }
try { Move-Item -LiteralPath $Package -Destination $Release }
catch {
    if ($HadRelease -and !(Test-Path -LiteralPath $Release)) { Move-Item -LiteralPath $Backup -Destination $Release }
    throw
}
@{version=$Smoke.step06_version;exe=$ReleaseExe;smoke_report=$SmokeReport;previous_release=$Backup;status='SUCCESS'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Stage 'release.json') -Encoding UTF8
Write-Host "Fixed Step06 EXE: $ReleaseExe"
Write-Host "Release record: $Stage\release.json"


