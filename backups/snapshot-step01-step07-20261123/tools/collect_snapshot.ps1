param(
    [string]$BackupWorktree = 'F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-backup-step01-step07-20261123'
)

$ErrorActionPreference = 'Stop'
$SnapshotRoot = Join-Path $BackupWorktree 'backups\snapshot-step01-step07-20261123'
$SourcesRoot = Join-Path $SnapshotRoot 'sources'
$EvidenceRoot = Join-Path $SnapshotRoot 'evidence'
$ManifestsRoot = Join-Path $SnapshotRoot 'manifests'

New-Item -ItemType Directory -Force -Path $SourcesRoot, $EvidenceRoot, $ManifestsRoot | Out-Null

function Copy-SnapshotFile {
    param([string]$Source, [string]$Destination)
    if (!(Test-Path -LiteralPath $Source -PathType Leaf)) { return $false }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    return $true
}

function Test-ExcludedSnapshotPath {
    param([System.IO.FileInfo]$File, [string]$Base)
    $relative = [IO.Path]::GetRelativePath($Base, $File.FullName)
    if ($File.Name -like 'abaqus.rpy*' -or $File.Name -eq 'bc_states.json') { return 'Abaqus replay/generated state' }
    if ($relative -match '(^|[\\/])(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules)([\\/]|$)') { return 'cache directory' }
    if ($File.Extension -in @('.pyc','.pyo','.log','.tmp','.bak','.odb','.cae','.sim','.prt','.res','.lck')) { return 'generated/binary output extension' }
    if ($File.Length -gt 50MB) { return 'larger than 50 MiB; not a small source resource' }
    return $null
}

function Write-GitEvidence {
    param([string]$SourceRoot, [string]$Destination)
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $safe = $SourceRoot.Replace('\\','/')
    $head = git -c "safe.directory=$safe" -C $SourceRoot rev-parse HEAD 2>$null
    $branch = git -c "safe.directory=$safe" -C $SourceRoot branch --show-current 2>$null
    $status = git -c "safe.directory=$safe" -C $SourceRoot status --porcelain=v1 --untracked-files=all 2>$null
    $log = git -c "safe.directory=$safe" -C $SourceRoot log -5 --oneline 2>$null
    Set-Content -LiteralPath (Join-Path $Destination 'git_head.txt') -Value $head -Encoding utf8
    Set-Content -LiteralPath (Join-Path $Destination 'git_branch.txt') -Value $branch -Encoding utf8
    Set-Content -LiteralPath (Join-Path $Destination 'git_status_porcelain.txt') -Value $status -Encoding utf8
    Set-Content -LiteralPath (Join-Path $Destination 'git_log_5.txt') -Value $log -Encoding utf8
}

function Copy-ProjectSnapshot {
    param(
        [string]$SourceRoot,
        [string]$Destination,
        [string[]]$IncludeDirectories = @('src','scripts','config','docs','tests','templates','examples','real_tests')
    )
    Write-Host "Copying current source snapshot: $SourceRoot"
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $excluded = [System.Collections.Generic.List[object]]::new()

    foreach ($file in Get-ChildItem -LiteralPath $SourceRoot -File -Force) {
        if ($file.Name -eq '.git') { continue }
        $reason = Test-ExcludedSnapshotPath -File $file -Base $SourceRoot
        if ($reason) {
            $excluded.Add([pscustomobject]@{path=$file.FullName;reason=$reason;bytes=$file.Length})
            continue
        }
        Copy-SnapshotFile -Source $file.FullName -Destination (Join-Path $Destination $file.Name) | Out-Null
    }

    foreach ($name in $IncludeDirectories) {
        $dir = Join-Path $SourceRoot $name
        if (!(Test-Path -LiteralPath $dir -PathType Container)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $dir -Recurse -File -Force -ErrorAction SilentlyContinue) {
            $reason = Test-ExcludedSnapshotPath -File $file -Base $SourceRoot
            if ($reason) {
                $excluded.Add([pscustomobject]@{path=$file.FullName;reason=$reason;bytes=$file.Length})
                continue
            }
            $relative = [IO.Path]::GetRelativePath($SourceRoot, $file.FullName)
            Copy-SnapshotFile -Source $file.FullName -Destination (Join-Path $Destination $relative) | Out-Null
        }
    }

    if ($excluded.Count -gt 0) {
        $excluded | Export-Csv -LiteralPath (Join-Path $Destination 'snapshot_exclusions.csv') -NoTypeInformation -Encoding utf8
    }
}

function Copy-Step03Snapshot {
    param([string]$SourceRoot, [string]$Destination)
    Write-Host 'Copying Step03 scripts, templates, configuration, tests, and documentation'
    $files = @(
        'scripts\step03_generate_coordinate_workbooks.py',
        'scripts\step03_generate_assembly_scripts.py',
        'scripts\make_coordinate_workbook.py',
        'scripts\annotate_coordinates.py',
        'src\cadtocae\coordinate_workbooks.py',
        'tests\test_coordinate_workbooks.py',
        'templates\SP_SC_coordinate_formula_simple_fixed_template.xlsx',
        'examples\sp_sc_ang20_coordinate_layout.json',
        'real_tests\SP_SC_ANG20_coordinate_formula_simple_fixed（关键控制点坐标计算模板）.xlsx',
        'docs\assembly_coordinate_check.md',
        'README.md',
        'requirements.txt',
        'requirements-build.txt',
        'pyproject.toml'
    )
    foreach ($relative in $files) {
        Copy-SnapshotFile -Source (Join-Path $SourceRoot $relative) -Destination (Join-Path $Destination $relative) | Out-Null
    }
    $config = Join-Path $SourceRoot 'config'
    if (Test-Path -LiteralPath $config) {
        foreach ($file in Get-ChildItem -LiteralPath $config -Recurse -File -Force) {
            $relative = [IO.Path]::GetRelativePath($SourceRoot, $file.FullName)
            Copy-SnapshotFile -Source $file.FullName -Destination (Join-Path $Destination $relative) | Out-Null
        }
    }
}

function New-HashIndex {
    param([object[]]$Roots)
    $index = @{}
    foreach ($rootInfo in $Roots) {
        if (!(Test-Path -LiteralPath $rootInfo.Path)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $rootInfo.Path -Recurse -File -Filter *.py -ErrorAction SilentlyContinue) {
            if ($file.FullName -match '\\__pycache__\\') { continue }
            $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
            if (!$index.ContainsKey($hash)) { $index[$hash] = [System.Collections.Generic.List[object]]::new() }
            $index[$hash].Add([pscustomobject]@{path=$file.FullName;kind=$rootInfo.Kind;priority=$rootInfo.Priority})
        }
    }
    return $index
}

function Resolve-ManifestSnapshot {
    param(
        [object[]]$Entries,
        [object[]]$SearchRoots,
        [string]$Destination,
        [string]$ResultCsv
    )
    Write-Host "Resolving manifest snapshot: $ResultCsv"
    $index = New-HashIndex -Roots $SearchRoots
    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $Entries) {
        $expected = $entry.sha256.ToUpperInvariant()
        $matches = @()
        if ($index.ContainsKey($expected)) { $matches = @($index[$expected] | Sort-Object priority,path) }
        if ($matches.Count -eq 0) {
            $results.Add([pscustomobject]@{path=$entry.path;expected_sha256=$expected;actual_sha256='';origin='';origin_kind='';status='MISSING'})
            continue
        }
        $chosen = $matches[0]
        $target = Join-Path $Destination $entry.path
        Copy-SnapshotFile -Source $chosen.path -Destination $target | Out-Null
        $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToUpperInvariant()
        $results.Add([pscustomobject]@{path=$entry.path;expected_sha256=$expected;actual_sha256=$actual;origin=$chosen.path;origin_kind=$chosen.kind;status=if($actual -eq $expected){'MATCH'}else{'MISMATCH'}})
    }
    $results | Export-Csv -LiteralPath $ResultCsv -NoTypeInformation -Encoding utf8
    return $results
}

function Write-RuntimePackageManifest {
    param([object]$Definition)
    Write-Host "Hashing runtime package $($Definition.Id): $($Definition.Package)"
    $exe = Join-Path $Definition.Package $Definition.ExeName
    $exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($exeHash -ne $Definition.ExpectedExeSha256.ToUpperInvariant()) {
        throw "EXE hash mismatch for $($Definition.Id): $exeHash"
    }
    $rows = foreach ($file in Get-ChildItem -LiteralPath $Definition.Package -Recurse -File -Force) {
        [pscustomobject]@{
            candidate = $Definition.Id
            relative_path = [IO.Path]::GetRelativePath($Definition.Package, $file.FullName)
            bytes = $file.Length
            modified_local = $file.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
        }
    }
    $manifestPath = Join-Path $ManifestsRoot ("runtime_packages\$($Definition.Id)_files.csv")
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
    $rows | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8
    return [pscustomobject]@{
        candidate = $Definition.Id
        package_path = $Definition.Package
        exe_name = $Definition.ExeName
        exe_sha256 = $exeHash
        package_files = @($rows).Count
        package_bytes = (@($rows) | Measure-Object -Property bytes -Sum).Sum
        source_evidence = $Definition.Evidence
    }
}

$parent = 'F:\Codex\Wind Resistance of PV Support Structures'
$projects = @(
    [pscustomobject]@{Id='step01_S01-A';Source=(Join-Path $parent 'CADtoCAE-feature-step01-development');Evidence='B'},
    [pscustomobject]@{Id='step02_S02-B';Source=(Join-Path $parent 'CADtoCAE-fix-step02-hoop-inner-profile');Evidence='B'},
    [pscustomobject]@{Id='step04_S04-A';Source=(Join-Path $parent 'CADtoCAE-feature-step04-dp-assembly');Evidence='B'},
    [pscustomobject]@{Id='step05_S05-A';Source=(Join-Path $parent 'CADtoCAE-feature-step05-development');Evidence='B'},
    [pscustomobject]@{Id='step06_S06-A';Source=(Join-Path $parent 'CADtoCAE-feature-step06-development');Evidence='A'},
    [pscustomobject]@{Id='step07_general_S07-C_current';Source=(Join-Path $parent 'CADtoCAE-Step07-Development');Evidence='CURRENT_DEV_NOT_EXE_SNAPSHOT'},
    [pscustomobject]@{Id='batchrunner_BAT-A_BAT-B';Source=(Join-Path $parent 'CADtoCAE-BatchRunner');Evidence='B'}
)

foreach ($project in $projects) {
    Copy-ProjectSnapshot -SourceRoot $project.Source -Destination (Join-Path $SourcesRoot "$($project.Id)\current_source")
    Write-GitEvidence -SourceRoot $project.Source -Destination (Join-Path $EvidenceRoot $project.Id)
}

$mainRoot = Join-Path $parent 'CADtoCAE'
Copy-Step03Snapshot -SourceRoot $mainRoot -Destination (Join-Path $SourcesRoot 'step03_scripts_templates')
Write-GitEvidence -SourceRoot $mainRoot -Destination (Join-Path $EvidenceRoot 'step03_main_source')

$v3Root = 'F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated'
$v3Current = Join-Path $v3Root 'Source\Step07'
Copy-ProjectSnapshot -SourceRoot $v3Current -Destination (Join-Path $SourcesRoot 'step07_v3_S07-A\current_development_source')
Write-GitEvidence -SourceRoot $v3Current -Destination (Join-Path $EvidenceRoot 'step07_v3_S07-A_current')

$v3ManifestPath = Join-Path $v3Root 'Dist\build_manifest.json'
Copy-SnapshotFile -Source $v3ManifestPath -Destination (Join-Path $EvidenceRoot 'step07_v3_S07-A\build_manifest.json') | Out-Null
Copy-SnapshotFile -Source (Join-Path $v3Root 'Test_Results\exe_smoke.json') -Destination (Join-Path $EvidenceRoot 'step07_v3_S07-A\exe_smoke.json') | Out-Null
$v3Manifest = Get-Content -LiteralPath $v3ManifestPath -Raw | ConvertFrom-Json
$v3Entries = foreach ($property in $v3Manifest.source_hashes.PSObject.Properties) {
    [pscustomobject]@{path=$property.Name;sha256=[string]$property.Value}
}
$v3SearchRoots = @(
    [pscustomobject]@{Path=(Join-Path $v3Current 'src');Kind='current_source_when_hash_matches';Priority=1},
    [pscustomobject]@{Path=(Join-Path $v3Root 'Original_Baseline\V3_1_0_before_all_factor');Kind='V3_1_0_original_baseline';Priority=2},
    [pscustomobject]@{Path=(Join-Path $v3Root 'Dist\CADtoCAE_Step07_V3_D1_Luan\_internal\cadtocae');Kind='selected_package_embedded_runtime';Priority=3}
)
$v3Results = Resolve-ManifestSnapshot -Entries $v3Entries -SearchRoots $v3SearchRoots -Destination (Join-Path $SourcesRoot 'step07_v3_S07-A\exe_matched_source') -ResultCsv (Join-Path $ManifestsRoot 'step07_v3_S07-A_source_resolution.csv')

$generalRoot = Join-Path $parent 'CADtoCAE-Step07-Development'
$generalPackage = Join-Path $generalRoot 'dist\CADtoCAE_Step07_AnalysisSetup'
$generalManifestPath = Join-Path $generalPackage 'build_manifest.json'
Copy-SnapshotFile -Source $generalManifestPath -Destination (Join-Path $EvidenceRoot 'step07_general_S07-C\build_manifest.json') | Out-Null
Copy-SnapshotFile -Source (Join-Path $generalPackage 'Step07_usage.md') -Destination (Join-Path $EvidenceRoot 'step07_general_S07-C\Step07_usage.md') | Out-Null
Copy-SnapshotFile -Source (Join-Path $generalPackage 'Step07_ODB_usage.md') -Destination (Join-Path $EvidenceRoot 'step07_general_S07-C\Step07_ODB_usage.md') | Out-Null
$generalManifest = Get-Content -LiteralPath $generalManifestPath -Raw | ConvertFrom-Json
$generalEntries = foreach ($source in $generalManifest.sources) { [pscustomobject]@{path=$source.path;sha256=$source.sha256} }
$generalSearchRoots = @(
    [pscustomobject]@{Path=(Join-Path $generalRoot 'src');Kind='current_worktree_when_hash_matches';Priority=1},
    [pscustomobject]@{Path=(Join-Path $generalRoot 'scripts');Kind='current_worktree_when_hash_matches';Priority=1},
    [pscustomobject]@{Path=(Join-Path $generalPackage '_internal\cadtocae');Kind='selected_package_embedded_runtime';Priority=2},
    [pscustomobject]@{Path=(Join-Path $v3Current 'src');Kind='isolated_source_mirror_when_hash_matches';Priority=3},
    [pscustomobject]@{Path=(Join-Path $v3Current 'scripts');Kind='isolated_source_mirror_when_hash_matches';Priority=3}
)
$generalResults = Resolve-ManifestSnapshot -Entries $generalEntries -SearchRoots $generalSearchRoots -Destination (Join-Path $SourcesRoot 'step07_general_S07-C\exe_matched_source') -ResultCsv (Join-Path $ManifestsRoot 'step07_general_S07-C_source_resolution.csv')

$step06Build = Join-Path $parent 'CADtoCAE-feature-step06-development\build\step06-release-20261101-203643-b24f21fb'
foreach ($name in @('release.json','smoke.json','CADtoCAE_Step06_HoleSetup.spec')) {
    Copy-SnapshotFile -Source (Join-Path $step06Build $name) -Destination (Join-Path $EvidenceRoot "step06_S06-A\release_build\$name") | Out-Null
}

$step02Build = Join-Path $parent 'CADtoCAE-fix-step02-hoop-inner-profile\build\step02'
$step02Evidence = @(
    'rebuild-tkfix.log',
    'smoke-tkfix.log',
    'tk-runtime.json',
    'spec\CADtoCAE_Step02_PartScript_TkFix.spec',
    'work\CADtoCAE_Step02_PartScript_TkFix\warn-CADtoCAE_Step02_PartScript_TkFix.txt',
    'work\CADtoCAE_Step02_PartScript_TkFix\xref-CADtoCAE_Step02_PartScript_TkFix.html',
    'final-hoop-tests.log',
    'final-step02-tests.log',
    'final-full-tests.log'
)
foreach ($relative in $step02Evidence) {
    Copy-SnapshotFile -Source (Join-Path $step02Build $relative) -Destination (Join-Path $EvidenceRoot "step02_S02-B\tkfix_build\$relative") | Out-Null
}

$reviewRoot = 'F:\Codex\CADtoCAE-Version-Review\20261123'
Copy-SnapshotFile -Source (Join-Path $reviewRoot 'FINAL_VERSION_REVIEW.md') -Destination (Join-Path $EvidenceRoot 'version_review\FINAL_VERSION_REVIEW.md') | Out-Null
Copy-SnapshotFile -Source (Join-Path $reviewRoot 'candidate_inventory.csv') -Destination (Join-Path $EvidenceRoot 'version_review\candidate_inventory.csv') | Out-Null

$runtimeDefinitions = @(
    [pscustomobject]@{Id='S01-A';Package=(Join-Path $parent 'CADtoCAE-feature-step01-development\dist\CADtoCAE_Step01_MaterialTable');ExeName='CADtoCAE_Step01_MaterialTable.exe';ExpectedExeSha256='0F1100C487141CFB006CB6AA9D254F13616A085947EDB9DE9BDF261D658B85B1';Evidence='B'},
    [pscustomobject]@{Id='S02-B';Package=(Join-Path $parent 'CADtoCAE-fix-step02-hoop-inner-profile\dist\CADtoCAE_Step02_PartScript_TkFix');ExeName='CADtoCAE_Step02_PartScript_TkFix.exe';ExpectedExeSha256='11A8EE568183A65355898A03288E0E013897DEE01BAAA8E830DA9350C96282C3';Evidence='B'},
    [pscustomobject]@{Id='S04-A';Package=(Join-Path $parent 'CADtoCAE-feature-step04-dp-assembly\dist\CADtoCAE_Step04_AssemblyScript');ExeName='CADtoCAE_Step04_AssemblyScript.exe';ExpectedExeSha256='9C89663D72BD14257BBA03A7F2C362A9F735FA6C21132768CCD0A2A309D4C99E';Evidence='B'},
    [pscustomobject]@{Id='S05-A';Package=(Join-Path $parent 'CADtoCAE-feature-step05-development\dist\CADtoCAE_Step05_AnalysisSetup');ExeName='CADtoCAE_Step05_AnalysisSetup.exe';ExpectedExeSha256='11A92D27A6BF7482636D74200F58119C5B4FCADC1C2A595044461522A870CBE2';Evidence='B'},
    [pscustomobject]@{Id='S06-A';Package=(Join-Path $parent 'CADtoCAE-feature-step06-development\dist\CADtoCAE_Step06_HoleSetup');ExeName='CADtoCAE_Step06_HoleSetup.exe';ExpectedExeSha256='016421FAFAA08B3D6FF3BCE44452304976BDFAB0DED33BC0C813D8DBCE82E653';Evidence='A'},
    [pscustomobject]@{Id='S07-A';Package=(Join-Path $v3Root 'Dist\CADtoCAE_Step07_V3_D1_Luan');ExeName='CADtoCAE_Step07_V3_D1_Luan.exe';ExpectedExeSha256='1D2D401BD24BC0F6D2260147B82FA79B091F7B3D5988BD0E3AC10D181DC21F96';Evidence='A'},
    [pscustomobject]@{Id='S07-C';Package=$generalPackage;ExeName='CADtoCAE_Step07_AnalysisSetup.exe';ExpectedExeSha256='C8CE1BA6D0A7083240909072D1387E1A60F3C37446A4514109DA027B0CB2CD0B';Evidence='A_MANIFEST_SNAPSHOT'},
    [pscustomobject]@{Id='BAT-A';Package=(Join-Path $parent 'CADtoCAE-BatchRunner\dist\CADtoCAE_BatchRunner_V40');ExeName='CADtoCAE_BatchRunner_V40.exe';ExpectedExeSha256='0B75E5707A7CD78E97B4926EBFF765496C009E08D8F41F3CB8276B3314F7D18D';Evidence='B'},
    [pscustomobject]@{Id='BAT-B';Package=(Join-Path $parent 'CADtoCAE-BatchRunner\dist\CADtoCAE_BatchRunner_CLI_V40');ExeName='CADtoCAE_BatchRunner_CLI_V40.exe';ExpectedExeSha256='A1899CFF1E37656ADA9330AAF8C79EBE4B49F48C4405B3D0B212F668E267A5FD';Evidence='B'}
)

$runtimeSummary = foreach ($definition in $runtimeDefinitions) { Write-RuntimePackageManifest -Definition $definition }
$runtimeSummary | Export-Csv -LiteralPath (Join-Path $ManifestsRoot 'selected_runtime_packages.csv') -NoTypeInformation -Encoding utf8

$resolutionSummary = [pscustomobject]@{
    generated_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    step07_v3_manifest_entries = @($v3Results).Count
    step07_v3_matches = @($v3Results | Where-Object status -eq 'MATCH').Count
    step07_v3_missing = @($v3Results | Where-Object status -eq 'MISSING').Count
    step07_general_manifest_entries = @($generalResults).Count
    step07_general_matches = @($generalResults | Where-Object status -eq 'MATCH').Count
    step07_general_missing = @($generalResults | Where-Object status -eq 'MISSING').Count
}
$resolutionSummary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ManifestsRoot 'step07_resolution_summary.json') -Encoding utf8
$runtimeDefinitions | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ManifestsRoot 'runtime_package_definitions.json') -Encoding utf8

Write-Host 'Snapshot collection complete.'
$resolutionSummary | Format-List
