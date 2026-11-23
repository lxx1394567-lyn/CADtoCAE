param([string]$Python = "python", [string]$OutputSuffix = "_V40")
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
if ($OutputSuffix -notmatch '^[_A-Za-z0-9-]*$') { throw "Invalid output suffix" }
$GuiName = "CADtoCAE_BatchRunner$OutputSuffix"
$CliName = "CADtoCAE_BatchRunner_CLI$OutputSuffix"
foreach ($Name in @($GuiName, $CliName)) {
    $ExePath = Join-Path (Get-Location) "dist/$Name/$Name.exe"
    if (Test-Path -LiteralPath $ExePath) {
        $Probe = [System.IO.File]::Open($ExePath, 'Open', 'ReadWrite', 'None')
        $Probe.Dispose()
    }
}
$RuntimeJson = & $Python scripts/step02_tk_runtime.py
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect Tcl/Tk runtime" }
$Runtime = $RuntimeJson | ConvertFrom-Json
$GuiArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', $GuiName, '--paths', 'src', '--add-data', 'src/cadtocae/batch_runner/cae_worker.py;cadtocae/batch_runner', '--add-data', 'src/cadtocae/batch_runner/delivery_worker.py;cadtocae/batch_runner', '--add-data', 'src/cadtocae/batch_runner/step07_verify.py;cadtocae/batch_runner', '--add-data', 'src/cadtocae/batch_runner/step07_adapter.py;cadtocae/batch_runner')
foreach ($Binary in $Runtime.binaries) { $GuiArgs += @('--add-binary', "$Binary;.") }
$GuiArgs += 'scripts/batch_runner_gui.py'
& $Python @GuiArgs
if ($LASTEXITCODE -ne 0) { throw "BatchRunner GUI build failed" }
& $Python scripts/step02_tk_runtime.py --package "dist/$GuiName"
if ($LASTEXITCODE -ne 0) { throw "Incomplete Tcl/Tk package" }
& $Python -m PyInstaller --noconfirm --clean --onedir --console --name $CliName --paths src --add-data "src/cadtocae/batch_runner/cae_worker.py;cadtocae/batch_runner" --add-data "src/cadtocae/batch_runner/delivery_worker.py;cadtocae/batch_runner" --add-data "src/cadtocae/batch_runner/step07_verify.py;cadtocae/batch_runner" --add-data "src/cadtocae/batch_runner/step07_adapter.py;cadtocae/batch_runner" scripts/batch_runner.py
if ($LASTEXITCODE -ne 0) { throw "BatchRunner CLI build failed" }
Copy-Item docs/batch_runner_usage.md "dist/$GuiName/usage.md"
