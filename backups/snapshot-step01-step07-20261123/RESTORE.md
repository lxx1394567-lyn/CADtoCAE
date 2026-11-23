# Restore and verification procedure

## 1. Restore committed sources and evidence

Clone the backup branch or check out the tag:

```powershell
git clone --branch backup/step01-step07-20261123 --single-branch https://github.com/lxx1394567-lyn/CADtoCAE.git CADtoCAE-backup-restore
git -C CADtoCAE-backup-restore rev-parse HEAD
git -C CADtoCAE-backup-restore rev-parse snapshot-step01-step07-20261123-r2^{commit}
```

The branch commit and tag target must match the published snapshot commit.

## 2. Download release assets

Download all assets from the prerelease associated with `snapshot-step01-step07-20261123-r2`. With GitHub CLI:

```powershell
gh release download snapshot-step01-step07-20261123-r2 --repo lxx1394567-lyn/CADtoCAE --dir release-assets
```

## 3. Verify asset hashes

Compare every downloaded ZIP with `manifests/release_assets.csv` using SHA-256. There must be exactly nine ZIP assets and each `asset_sha256` must match.

```powershell
Import-Csv .\backups\snapshot-step01-step07-20261123\manifests\release_assets.csv | ForEach-Object {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path .\release-assets $_.asset_name)).Hash
    [pscustomobject]@{ asset=$_.asset_name; expected=$_.asset_sha256; actual=$actual; match=($actual -eq $_.asset_sha256) }
}
```

## 4. Extract and verify complete runtime packages

Each ZIP contains one top-level runtime package directory. Extract it without changing files, then verify every file against the corresponding `manifests/runtime_packages/<candidate>_files.csv`. At minimum, verify the selected main EXE against `manifests/selected_runtime_packages.csv`.

The runtime package is the entire extracted directory, not only its EXE. Keep `_internal`, DLLs, runtime modules, configuration, templates/resources, logs or usage notes that are present in the package.

## 5. Verify committed snapshot files

Use `manifests/source_snapshot_files.csv` to verify the committed backup materials. The manifest deliberately excludes itself and records all other files under this snapshot directory.

## 6. Runtime policy

Restoration verification is file-integrity verification only. It does not require running the EXE, Abaqus, or rebuilding packages. Functional revalidation should be performed separately if required by a future deployment.

