# Source provenance and correspondence status

Confirmation of a runtime package means that the package was selected for preservation. It does not upgrade B-level source correspondence to A.

| Module | Archived source | Evidence | Status and limitations |
|---|---|---|---|
| Step01 S01-A | Current clean snapshot from `CADtoCAE-feature-step01-development`; build script/spec/docs/tests included | Commit `4670162...`, PyInstaller spec and build script | **B**: strong association, but no exact build-time source hash manifest |
| Step02 S02-A | Current clean snapshot from `CADtoCAE-fix-step02-hoop-inner-profile` | Commit `cdf5836...`, PR #8 files, Tcl/Tk build checks, docs/tests | **B**: no complete exact source hash manifest for the selected EXE |
| Step03 | Current main Step03 scripts, coordinate module, configuration, templates, examples, tests, and usage material | Main base `a0092c0...` | No standalone EXE; source-only preservation |
| Step04 S04-A | Current clean snapshot from `CADtoCAE-feature-step04-dp-assembly` | Commit `a4ead2b...`, spec/build script/docs/tests | **B**: no complete exact source hash manifest |
| Step05 S05-A | Current snapshot from `CADtoCAE-feature-step05-development`, including modified and untracked source/tests | Git status evidence; package runtime files; spec/build script | **B**: current source contains later work; existing integrity proof refers to another older EXE hash |
| Step06 S06-A | Current snapshot from `CADtoCAE-feature-step06-development`, including untracked source/tests | Exact `release.json`, `smoke.json`, generated spec, selected EXE hash; version 0.2.14 | **A** for the selected release evidence. The current source worktree contains uncommitted files and is preserved separately; the Git commit alone is insufficient |
| Step07 S07-A | `exe_matched_source` reconstructed from the V3-D1-1.0 manifest; current development source stored separately | 108/108 manifest hashes matched: 105 current-source files and 3 files from `Original_Baseline\V3_1_0_before_all_factor` | **A** for the EXE-matched snapshot; current development source is not substituted for the three older files |
| Step07 S07-C | `exe_matched_source` reconstructed from the selected package manifest; current development source stored separately | 34/34 manifest hashes matched: 32 current-worktree files and 2 embedded runtime files from the selected package | **A** for the manifest snapshot. The two changed current runtime files are not represented as original EXE source |
| BatchRunner BAT-A/B | Current snapshot from `CADtoCAE-BatchRunner`, including untracked source/docs/tests | GUI/CLI specs, build script and V4 audit/validation records | **B**: no exact build-time source hash manifest |

## Current-worktree preservation

The archived module snapshots copy source-oriented directories (`src`, `scripts`, `config`, `docs`, `tests`, `templates`, `examples`, and `real_tests`) plus root project metadata. Git evidence records branch, HEAD, recent log, and full porcelain status.

The status evidence includes later or uncommitted work for Step05, Step06, Step07, and BatchRunner. Cache directories, bytecode, virtual environments, build/dist trees, Abaqus replay/state files, large generated solver outputs, and unrelated output directories were excluded. Exclusions encountered inside included source directories are recorded in each `snapshot_exclusions.csv`.

## Step07 resolution details

- `manifests/step07_v3_S07-A_source_resolution.csv` gives the exact origin and hash for every V3 D1 manifest entry.
- `manifests/step07_general_S07-C_source_resolution.csv` gives the exact origin and hash for every general Step07 manifest entry.
- `manifests/step07_resolution_summary.json` records match and missing counts.

No Step07 manifest entry was missing at archive time.

