param([string]$Python='', [string]$ReleaseSubdir='CADtoCAE_Step07_AnalysisSetup')
$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $Root
if ((git branch --show-current) -ne 'feature/step07-analysis-setup') { throw 'Build must run on the Step07 development branch' }
if (!$Python) { $Python=Join-Path $Root '../CADtoCAE-feature-step06-development/.venv_step06_build/Scripts/python.exe' }
$Python=(Resolve-Path -LiteralPath $Python).Path
$Name='CADtoCAE_Step07_AnalysisSetup'
 $Release=[IO.Path]::GetFullPath((Join-Path (Join-Path $Root 'dist') $ReleaseSubdir))
if (!$Release.StartsWith((Join-Path $Root 'dist')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Release must stay under worktree dist' }
if (Get-Process -Name $Name -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $Release ($Name+'.exe')) }) { throw 'Close the target Step07 EXE before rebuilding' }
$Stage=Join-Path $Root ('build/step07-'+(Get-Date -Format yyyyMMdd-HHmmss)+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
$BasePrefix=& $Python -c 'import sys; print(sys.base_prefix)'
$NativeDirs=@((Join-Path $BasePrefix 'Library/bin'),(Join-Path $BasePrefix 'DLLs'))
$BuildArgs=@('-m','PyInstaller','--clean','--noconfirm','--onedir','--windowed','--name',$Name,'--paths',(Join-Path $Root 'src'),'--add-data',((Join-Path $Root 'src/cadtocae/step07_runtime.py')+';cadtocae'))
$BuildArgs+=@('--add-data',((Join-Path $Root 'src/cadtocae/step07_mesh_runtime.py')+';cadtocae'))
$BuildArgs+=@('--add-data',((Join-Path $Root 'src/cadtocae/step07_postprocess_runtime.py')+';cadtocae'))
foreach ($Runtime in @('hole_transforms.py','step07_tie_runtime.py','step07_bc_runtime.py','step07_pipeline_runtime.py','step07_mesh_cleanup_runtime.py','step07_quality_runtime.py','step07_source_guard_runtime.py','step07_inplace_runtime.py','step07_load_runtime.py','step07_inp_runtime.py','step07_multitype_runtime.py','step07_identity_runtime.py','step07_hoop_region_runtime.py')) { $BuildArgs+=@('--add-data',((Join-Path $Root ('src/cadtocae/'+$Runtime))+';cadtocae')) }
foreach ($Dll in @('tcl86t.dll','tk86t.dll','ffi.dll')) {
    foreach ($Directory in $NativeDirs) {
        $Candidate=Join-Path $Directory $Dll
        if (Test-Path -LiteralPath $Candidate) { $BuildArgs+=@('--add-binary',"$Candidate;.");break }
    }
}
$BuildArgs+=@('--distpath',(Join-Path $Stage 'dist'),'--workpath',(Join-Path $Stage 'work'),'--specpath',$Stage,'scripts/step07_analysis_setup_gui.py')
$PriorPath=$env:PATH;$PriorCache=$env:PYINSTALLER_CONFIG_DIR
try {
    $env:PATH=($NativeDirs -join ';')+';'+$PriorPath
    $env:PYINSTALLER_CONFIG_DIR=Join-Path $Stage 'cache'
    & $Python @BuildArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
} finally { $env:PATH=$PriorPath;$env:PYINSTALLER_CONFIG_DIR=$PriorCache }
$Package=Join-Path $Stage "dist/$Name"

$Backup=Join-Path $Stage 'previous-release'
foreach ($Target in @($Package,$Release,$Backup)) {
    $Absolute=[IO.Path]::GetFullPath($Target)
    if (!$Absolute.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe target: $Absolute" }
}
if (Get-Process -Name $Name -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $Release ($Name+'.exe')) }) { throw 'Target Step07 EXE became active; release not replaced' }
New-Item -ItemType Directory -Force (Split-Path $Release) | Out-Null
if (Test-Path -LiteralPath $Release) { Move-Item -LiteralPath $Release -Destination $Backup }
Move-Item -LiteralPath $Package -Destination $Release
if (Test-Path docs/step07_inplace_usage.md) { Copy-Item docs/step07_inplace_usage.md (Join-Path $Release 'Step07_usage.md') }
if (Test-Path docs/step07_odb_usage.md) { Copy-Item docs/step07_odb_usage.md (Join-Path $Release 'Step07_ODB_usage.md') }
$SourceFiles=@('src/cadtocae/step07_setup.py','src/cadtocae/step07_runtime.py','src/cadtocae/step07_desktop.py','src/cadtocae/step07_batch.py','src/cadtocae/step07_rules.py','scripts/step07_analysis_setup_gui.py')
$SourceFiles+=@('src/cadtocae/step07_mesh_setup.py','src/cadtocae/step07_mesh_runtime.py','src/cadtocae/step07_mesh_rules.py','src/cadtocae/step07_mesh_desktop.py')
$SourceFiles+=@('src/cadtocae/step07_pipeline.py','src/cadtocae/step07_pipeline_runtime.py','src/cadtocae/step07_pipeline_desktop.py','src/cadtocae/step07_tie_runtime.py','src/cadtocae/step07_bc_runtime.py')
$SourceFiles+=@('src/cadtocae/step07_mesh_cleanup_runtime.py','src/cadtocae/step07_runtime_bundle.py')
$SourceFiles+=@('src/cadtocae/step07_quality_runtime.py')
$SourceFiles+=@('src/cadtocae/step07_source_guard_runtime.py')
$SourceFiles+=@('src/cadtocae/step07_inplace.py','src/cadtocae/step07_inplace_runtime.py')
$SourceFiles+=@('src/cadtocae/step07_load_input.py','src/cadtocae/step07_load_runtime.py','src/cadtocae/step07_tributary.py','src/cadtocae/step07_inp_runtime.py','src/cadtocae/step07_multitype_runtime.py','src/cadtocae/step07_identity_runtime.py','src/cadtocae/step07_projects.py','src/cadtocae/step07_output.py','src/cadtocae/step07_hoop_region_runtime.py')
$SourceFiles+=@('src/cadtocae/step07_luan_load.py')
$SourceFiles+=@('src/cadtocae/step07_postprocess.py','src/cadtocae/step07_postprocess_runtime.py','src/cadtocae/step07_postprocess_desktop.py')
$Hashes=foreach ($File in $SourceFiles) { @{path=$File;sha256=(Get-FileHash -LiteralPath $File).Hash} }
@{status='BUILT_PENDING_EXE_UI_TEST';exe=(Join-Path $Release "$Name.exe");branch=(git branch --show-current);baseline=(git rev-parse HEAD);sources=$Hashes} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Release 'build_manifest.json') -Encoding UTF8
Write-Host "EXE: $Release\$Name.exe"
