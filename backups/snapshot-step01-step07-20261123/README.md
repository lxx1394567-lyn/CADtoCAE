# CADtoCAE Step01—Step07 backup snapshot r2 (2026-11-23)

This directory is the source-and-evidence portion of the authorized backup snapshot.

- Branch: `backup/step01-step07-20261123`
- Tag: `snapshot-step01-step07-20261123-r2`
- Base commit: `a0092c033675dd5dffb7ad58d5c7acc19e2ac660`
- Runtime packages: distributed as nine ZIP assets on the prerelease associated with the tag
- EXE policy: selected EXEs were not rebuilt, edited, or executed

## Selected backup objects

| Scope | Candidate | Evidence status | Release asset |
|---|---|---|---|
| Step01 material table OCR | S01-A | B | `S01-A_CADtoCAE_Step01_MaterialTable.zip` |
| Step02 TkFix part scripts | S02-B | B | `S02-B_CADtoCAE_Step02_PartScript_TkFix.zip` |
| Step03 coordinate workbooks | scripts/templates only | no standalone EXE | committed under `sources/step03_scripts_templates` |
| Step04 DP/folder assembly | S04-A | B | `S04-A_CADtoCAE_Step04_AssemblyScript.zip` |
| Step05 analysis setup | S05-A | B | `S05-A_CADtoCAE_Step05_AnalysisSetup.zip` |
| Step06 hole/connector setup | S06-A | A | `S06-A_CADtoCAE_Step06_HoleSetup.zip` |
| Step07 V3 D1 isolated load | S07-A | A | `S07-A_CADtoCAE_Step07_V3_D1_Luan.zip` |
| Step07 general analysis/ODB | S07-C | A for manifest snapshot | `S07-C_CADtoCAE_Step07_AnalysisSetup.zip` |
| BatchRunner GUI V40 | BAT-A | B | `BAT-A_CADtoCAE_BatchRunner_V40.zip` |
| BatchRunner CLI V40 | BAT-B | B | `BAT-B_CADtoCAE_BatchRunner_CLI_V40.zip` |

This r2 revision changes only the selected Step02 runtime package from S02-A to S02-B. The original tag and Release remain unchanged. S07-B, Selection, historical packages, diagnostic packages, and duplicate mirrors were intentionally not selected as primary runtime packages. Their original local files were not moved or deleted.

## Layout

- `sources/`: module-separated current source snapshots plus Step07 EXE-matched snapshots.
- `evidence/`: Git state, build manifests, release/smoke records, usage notes, and the first-stage review.
- `manifests/`: per-file runtime package hashes, selected package summary, Step07 source resolution, release asset hashes, and committed snapshot hashes.
- `tools/`: collection, packaging, and verification procedures used for this snapshot.
- `RESTORE.md`: recovery and integrity-check procedure.
- `SOURCE_PROVENANCE.md`: source origin and unresolved correspondence limitations.

Complete runtime directories are not committed to Git. They are stored intact inside the release ZIP assets so `_internal`, DLLs, runtime modules, resources, configuration, templates, and usage files remain together.

