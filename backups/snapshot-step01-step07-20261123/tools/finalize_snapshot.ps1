param(
    [string]$BackupWorktree = 'F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-backup-step01-step07-20261123',
    [string]$AssetsRoot = 'F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-backup-assets-20261123'
)

$ErrorActionPreference = 'Stop'
$SnapshotRoot = Join-Path $BackupWorktree 'backups\snapshot-step01-step07-20261123'
$ManifestsRoot = Join-Path $SnapshotRoot 'manifests'
$releaseManifestPath = Join-Path $ManifestsRoot 'release_assets.csv'
$runtimeManifestPath = Join-Path $ManifestsRoot 'selected_runtime_packages.csv'
$resolutionPath = Join-Path $ManifestsRoot 'step07_resolution_summary.json'
$sourceManifestPath = Join-Path $ManifestsRoot 'source_snapshot_files.csv'

$assets = @(Import-Csv -LiteralPath $releaseManifestPath)
if ($assets.Count -ne 9) { throw "Expected 9 release assets, found $($assets.Count)" }

$assetLines = [System.Collections.Generic.List[string]]::new()
foreach ($asset in $assets) {
    $path = Join-Path $AssetsRoot $asset.asset_name
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing release asset: $path" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $asset.asset_sha256.ToUpperInvariant()) { throw "Release asset changed: $($asset.asset_name)" }
    $assetLines.Add("$actual  $($asset.asset_name)")
}
$assetLines | Set-Content -LiteralPath (Join-Path $ManifestsRoot 'release_asset_SHA256SUMS.txt') -Encoding ascii

$runtime = @(Import-Csv -LiteralPath $runtimeManifestPath)
$resolution = Get-Content -LiteralPath $resolutionPath -Raw | ConvertFrom-Json
$summary = [ordered]@{
    snapshot_date = '2026-11-23'
    base_commit = 'a0092c033675dd5dffb7ad58d5c7acc19e2ac660'
    branch = 'backup/step01-step07-20261123'
    tag = 'snapshot-step01-step07-20261123'
    runtime_asset_count = $assets.Count
    runtime_package_count = $runtime.Count
    runtime_asset_bytes = [int64](($assets | Measure-Object asset_bytes -Sum).Sum)
    step03_standalone_exe = $false
    step07_v3_manifest_entries = [int]$resolution.step07_v3_manifest_entries
    step07_v3_matches = [int]$resolution.step07_v3_matches
    step07_v3_missing = [int]$resolution.step07_v3_missing
    step07_general_manifest_entries = [int]$resolution.step07_general_manifest_entries
    step07_general_matches = [int]$resolution.step07_general_matches
    step07_general_missing = [int]$resolution.step07_general_missing
    exe_execution_performed = $false
    abaqus_execution_performed = $false
    exe_rebuild_performed = $false
}
$summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ManifestsRoot 'archive_summary.json') -Encoding utf8

$rows = foreach ($file in Get-ChildItem -LiteralPath $SnapshotRoot -Recurse -File -Force | Sort-Object FullName) {
    if ($file.FullName -eq $sourceManifestPath) { continue }
    [pscustomobject]@{
        relative_path = [IO.Path]::GetRelativePath($SnapshotRoot, $file.FullName)
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
    }
}
$rows | Export-Csv -LiteralPath $sourceManifestPath -NoTypeInformation -Encoding utf8

$tooLarge = @($rows | Where-Object { [int64]$_.bytes -ge 100MB })
if ($tooLarge.Count -gt 0) { throw 'Snapshot contains a file at or above the GitHub 100 MiB limit.' }

[pscustomobject]@{
    snapshot_files_excluding_self = @($rows).Count
    snapshot_bytes_excluding_self = [int64](($rows | Measure-Object bytes -Sum).Sum)
    release_assets = $assets.Count
    release_asset_bytes = [int64](($assets | Measure-Object asset_bytes -Sum).Sum)
} | Format-List
