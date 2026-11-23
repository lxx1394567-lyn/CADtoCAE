param(
    [string]$BackupWorktree = 'F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-backup-step01-step07-20261123',
    [string]$AssetsRoot = 'F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-backup-assets-20261123'
)

$ErrorActionPreference = 'Stop'
$SnapshotRoot = Join-Path $BackupWorktree 'backups\snapshot-step01-step07-20261123'
$DefinitionsPath = Join-Path $SnapshotRoot 'manifests\runtime_package_definitions.json'
$OutputManifest = Join-Path $SnapshotRoot 'manifests\release_assets.csv'
$definitions = @(Get-Content -LiteralPath $DefinitionsPath -Raw | ConvertFrom-Json)

New-Item -ItemType Directory -Force -Path $AssetsRoot | Out-Null
$rows = [System.Collections.Generic.List[object]]::new()

foreach ($definition in $definitions) {
    $package = [IO.Path]::GetFullPath([string]$definition.Package)
    $parent = Split-Path -Parent $package
    $leaf = Split-Path -Leaf $package
    $assetName = "$($definition.Id)_$leaf.zip"
    $assetPath = Join-Path $AssetsRoot $assetName
    if (Test-Path -LiteralPath $assetPath) {
        Write-Host "Reusing and verifying existing asset $assetName"
    } else {
        Write-Host "Creating $assetName"
        & tar.exe -a -c -f $assetPath -C $parent $leaf
        if ($LASTEXITCODE -ne 0) { throw "Archive creation failed: $assetName" }
    }

    $sourceFiles = @(Get-ChildItem -LiteralPath $package -Recurse -File -Force)
    $archiveEntries = @(& tar.exe -t -f $assetPath | Where-Object { $_ -notmatch '[\\/]$' })
    if ($LASTEXITCODE -ne 0) { throw "Archive listing failed: $assetName" }
    if ($archiveEntries.Count -ne $sourceFiles.Count) {
        throw "Archive entry count mismatch for ${assetName}: archive=$($archiveEntries.Count), source=$($sourceFiles.Count)"
    }

    $exe = Join-Path $package ([string]$definition.ExeName)
    $exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($exeHash -ne ([string]$definition.ExpectedExeSha256).ToUpperInvariant()) {
        throw "Selected EXE changed before archive creation: $($definition.Id)"
    }

    $asset = Get-Item -LiteralPath $assetPath
    $rows.Add([pscustomobject]@{
        candidate = $definition.Id
        asset_name = $assetName
        asset_path = $assetPath
        asset_bytes = $asset.Length
        asset_sha256 = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToUpperInvariant()
        package_directory_name = $leaf
        package_files = $sourceFiles.Count
        package_bytes = ($sourceFiles | Measure-Object Length -Sum).Sum
        main_exe = $definition.ExeName
        main_exe_sha256 = $exeHash
        source_evidence = $definition.Evidence
    })
}

$rows | Export-Csv -LiteralPath $OutputManifest -NoTypeInformation -Encoding utf8
Write-Host "Created $($rows.Count) release assets."
$rows | Select-Object candidate,asset_name,asset_bytes,asset_sha256 | Format-Table -AutoSize
