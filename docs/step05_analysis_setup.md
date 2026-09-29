# Step05 A1 + A2: front-brace connection regions

Only `INCLINED_BEAM` / `BRACE_FRONT` at station C is enabled. Half-length is
analysis input (confirmed benchmark: 0.080 m). No geometry is removed. No rear
connection, constraints, reference points, holes, connectors, loads or mesh jobs
are created. The runtime operates on an existing model and never recreates it.

## Generate and run

Use the worktree's `.venv_step05_build` Python 3.11 environment:

```powershell
.\.venv_step05_build\Scripts\python.exe scripts\step05_generate_analysis_setup.py --summary PATH_TO_SUMMARY --analysis PATH_TO_ANALYSIS --output-dir PATH_TO_OUTPUT
```

The generator writes `<project_id>_analysis_setup.py` and
`<project_id>_analysis_plan.json`. It does not require Abaqus or read any Assembly
script. It prints the intended `<project_id>_analysis_setup_report.json` path;
that report is only written when the generated script runs in Abaqus/CAE.
Its absolute path is embedded, so moving the files to another computer requires
regeneration or an explicit update of REPORT_PATH.

Run the script after the matching Step02/Step04 model has been built. Save any
working CAE model under a user-chosen name before validation. This script does
not save/open a CAE file and does not roll back already completed partitions on
failure. Failure reports include the traceback and completed mutation list.

## Input contract

Accept JSON or an Excel workbook with exactly two sheets. Literal values only;
formula cells are rejected, preventing stale Excel cache values from being used.

`Project_Info` columns: `key`, `value`.

| key | value |
| --- | --- |
| schema_version | 1 |
| project_id | Must match summary project_id and model_name |
| length_unit | m |
| geometry_tolerance_m | Optional, default 0.000001; maximum 0.0001 |

`Partition_Region` columns:

| field | A2 example |
| --- | --- |
| region_id | REGION_BEAM_BRACE_FRONT |
| connection_id | BEAM_BRACE_FRONT |
| target_role | INCLINED_BEAM |
| reference_station | C |
| half_length_m | 0.080 |
| partition_rule | BEAM_LOCAL_PATCH |
| enabled | TRUE |

Optional disambiguators: `instance_id`, `connection_group`, `brace_instance_id`.
Duplicate connection/region definitions are errors, even if identical. A2 permits
one enabled row; the brace region is derived by the engineering rule. The file
`examples/step05/analysis_a2.json` is a synthetic project example, not real project
geometry. Replace its project_id only when using an actual matching summary.

## Plan and validation

The plan contains project metadata, resolved instances, three partition intents,
two regions, validation status and empty ties/reference_points/couplings. It also
records disabled future defaults: program-selected main/secondary in A3,
adjust/position tolerance DEFAULT, and DISTRIBUTING with all six DOFs enabled in
A7. None of those future objects is executed in A2.

No structure_type branching is used. Role resolution uses canonical_role with
component_code fallback. Summary provides length, identity and C. Actual shell
geometry and SectionAssignments provide shape, thickness, offset and normals;
there is no second user-supplied thickness or physical-side guess.

Generation checks identities, input values, semantic names, role uniqueness,
station presence, length and placement metadata. It explicitly leaves geometry
validation as RUNTIME_REQUIRED. Before any mesh or geometry mutation the runtime:

1. Checks expected model, native dependent Part instances and all sharing instances.
2. Fits a proper rigid transform using corresponding Part/Instance vertices;
   verifies every vertex plus face connectivity and normals.
3. Tests that measured pose against all possible translation insertion positions
   in legacy summary rotation_steps. This is runtime disambiguation, not a guess
   or a change to Step04. Unknown/mismatching transforms fail-fast.
4. Projects supplied global C into the measured beam local frame. If
   SET_BEAM_SEC_C exists, verifies it is the complete edge section at this local
   station. Invalid existing Sets are errors; missing Sets use verified summary
   C with a warning and do not trigger another center partition.
5. Computes C +/- half_length_m, requires both boundaries inside beam length,
   verifies the flange and the brace intersection before mutation.

## Physical surface convention

Initial geometry support is planar shell C_CHANNEL from the existing profile
convention (local Z length, local Y height). Solids, orphan meshes, curved faces,
nonuniform/geometry-based thickness, field offsets and ambiguous topology are
rejected. The actual transformed local height axis must identify a unique lower
flange. Its full width is used; longitudinal extent is exactly the input patch.
Partial-width patches require a later explicit rule and are not silently guessed.

Geometry is the shell reference surface, not necessarily its midsurface. For
positive face normal n, thickness t and dimensionless section offset o:

```
physical SIDE1 = reference geometry + ( 0.5 - o) * t * n
physical SIDE2 = reference geometry + (-0.5 - o) * t * n
```

MIDDLE_SURFACE, TOP_SURFACE, BOTTOM_SURFACE and SINGLE_VALUE are supported.
The beam region records FACE, SIDE1/SIDE2, thickness, reference-to-physical
displacement, and full offset interpretation. Beam partitions act on reference
shell geometry, while the brace partition plane is the beam PHYSICAL outer plane.

The brace target is a connected intersection chain near one end of its reference
shell geometry, entirely within the finite beam patch footprint. No intersection,
multiple disconnected regions, intersection spanning the brace midpoint, or a
partially out-of-patch intersection is rejected before edits. A2 does not trim
material or manufacture an exposed end face. Therefore the brace output is an
EDGE Set, with physical_side=EDGE_ON_BEAM_PHYSICAL_OUTER_PLANE and adjacent-face
thickness/offset/normal records. SIDE1/SIDE2 is not falsely assigned to an internal
intersection edge. A3 must select the appropriate interaction formulation; this
edge Set is not claimed to be an already validated Tie surface.

## Mutation, mesh and idempotency

Only necessary planes/face partitions are created; existing correct boundaries
are reused. Construction datum points, planes and partitions all receive stable
STEP05_ names. Beam/brace partitions precede Set/Surface creation. After all
partitions the assembly is regenerated, fresh geometry is selected, and shell
area is checked against the pre-partition value to detect unexpected changes.

Affected native meshes are deleted only on Parts with pending geometry partitions;
this is recorded as mesh_removed_parts. Such Parts are marked remesh_required.
No unrelated mesh is touched; no final meshing occurs. This is a conservative
native-mesh invalidation policy, not a trial partition followed by a broad retry.

Repeated execution with the same successful report/plan fingerprint revalidates
geometry, Sets and surface side and reuses them. Conflicting or partial STEP05
objects without a matching successful report fail rather than delete/replace
features. Keep the runtime report with the model. A failure report records the
partial state; manual recovery is required before retry if features were created.

## Runtime report

Always includes project_id, model_name, phase=A2, status, plan_fingerprint,
reference_station=C, patch_half_length_m, partition_locations, beam_part,
brace_part, beam_region, brace_region, partitions, surfaces, sets,
existing_objects_reused, semantic_mapping, affected_instances, pose_verification
(when resolved), mesh_removed, mesh_removed_parts, remesh_required,
remesh_required_parts, warnings, errors, material_removed=false and
tie_created=false. Region records contain geometric_region_type and physical_side.
Failures add traceback. Empty future object lists make scope explicit.

## Validation and handoff

### Real project input

Run from the Step05 worktree with its isolated Python environment:

```powershell
$env:PYTHONPATH='src'
& .\.venv_step05_build\Scripts\python.exe scripts/step05_generate_analysis_setup.py --project-folder '<case-folder>'
```

The nonrecursive discovery first reads the unique `*_assembly_summary.json`
identity, then requires unique matching components/coordinate workbooks and
create_parts_in_cae/assembly_frame scripts. Excel lock files are ignored. Missing,
multiple or mismatched candidates fail before output is written. Python inputs
are checked only for existence and filenames; their content is never parsed.
The runtime assembly report cannot substitute for the assembly summary.

For files in separate directories use `--components <xlsx> --coordinate <xlsx>
--assembly-summary <json>`, optionally `--part-script <py> --assembly-script <py>`.
`--output-dir` overrides the default `<summary-folder>/step05_validation`.

Components are normalized with the existing workbook exporter. Coordinate input
uses the existing Step04 parameter solver or numeric named-point reader (including
the newer 状态 header). Numeric C must match the summary; C/G_global must align
with the beam axis when used to derive the station. There is no synthetic fallback
and no structure-type-specific connection implementation. The approved real-case
scope is front brace at C +/- 0.080 m, with no material trimming.

Generation writes `<project_id>_analysis_setup.py` and `_analysis_plan.json`.
Only execution in Abaqus writes `_analysis_setup_report.json`. Run the existing
create_parts_in_cae script, assembly_frame script, then analysis_setup script in
the same model. Step05 verifies the actual C-channel dimensions, shell thickness,
pose and C station before mutation. Physical SIDE1/SIDE2 remains explicitly
runtime-required in the offline plan because actual face normals and section
offsets must be checked in CAE.

Real-mode output includes `STEP05_C_MINUS_80`, `STEP05_C_PLUS_80`, the named beam
and brace region Sets, a beam Surface, and diagnostic console output. Inspect
these with Display Group/Highlight. No Tie, RP, Coupling or other interaction is
created. The brace region remains an intersection edge Set, not a trimmed face.

Tests use synthetic geometry only. The independent polygon-clipping CAE double
checks the full generated executor, preflight-before-mutation, area preservation,
correct patch selection, mesh scope and repeat execution. These tests do not
validate the Abaqus geometry kernel. Real engineering input remains external to
Git and must be specified by the user. A synthetic generated script will require
a matching synthetic model and must not be renamed to impersonate a real model.

In Abaqus verify C +/- 80 mm, lower-flange side, brace intersection, preserved
brace material and report warnings. A2 success does not imply that a physical
contact/Tie has been validated. Only after manual acceptance proceed to A3.

API references checked: Abaqus Face.getNormal/getVertices/getSize,
SectionAssignment offsetType/thicknessAssignment, Surface side1Faces/side2Faces,
DatumPointByCoordinate/DatumPlaneByThreePoints/PartitionFaceByDatumPlane.
See https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-featurepyc.htm
and https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-sectionassignmentpyc.htm.
## Current production direction: BEAM_BRACE_TIE (2026-09-27)

Real project CLI mode now uses `beam_brace_tie.py` and the standalone
`beam_brace_tie_runtime.py`. The A2 material below is historical. Use
`--legacy-a2` only to reproduce an old geometry-only experiment; it is not the
default project-folder path. Existing standalone Macro/Extend Face experiments
remain as history and are not imported or parsed by the current rule.

Inputs are components.xlsx, coordinate.xlsx, assembly_summary.json and
analysis.xlsx. Components still use the existing Step02 workbook normalization.
The project-folder reader discovers either `analysis.xlsx` or a unique
`*_analysis.xlsx`; pass `--analysis <file>` to override. Missing or ambiguous
configuration fails; it never silently falls back to A2.

`Tie_Config` has exactly these six columns and one data row:

| rule_id | enabled | beam_half_length_mm | brace_end_length_mm | beam_shell_side | brace_shell_side |
|---|---|---|---|---|---|
| BEAM_BRACE_TIE | TRUE | 50 | 50 | SIDE2 | SIDE2 |

Lengths must be positive numbers. Blank shell-side cells default to SIDE2;
SIDE1 is supported. Unknown rules, invalid sides and overlapping end zones fail.
FALSE produces a disabled plan without creating geometry or constraints.

The role map is FRONT: B -> C, REAR: D -> E. Both use the same loop. GC_mm and
GE_mm are read directly from the coordinate parameter table in mm; B/C/D/E
numeric coordinate values are checked against the summary. No angle/family
branch or placement transform is used. Exactly one instance per role is required
in this first rule; shared Parts or ambiguous roles fail explicitly.

All Part-local Z partitions finish before regions and Ties: the beam is cut at
GC/GE +/- half-length; each brace is cut at end-length and L-end-length. Native
mesh is deleted only on Parts needing new partitions. Existing geometric
boundaries are reused. Final meshing is deferred.

Beam WEB faces are selected using the Step02 C-channel local convention X=0,
within the beam interval. Total selected area must equal interval length times
web height. Brace candidates lie wholly in [L-end-length,L]. Their already
assembled face normals must be parallel/antiparallel to the beam web. Minimum
normal gap wins; tangential center distance breaks ties. An unresolved tie fails.
These distances are reported for manual inspection; no custom Tie tolerance is
invented and no exact intersection or shell-offset plane is constructed.

Assembly Sets and Surfaces use STEP05_REGION_* / STEP05_SURF_* names. Brace is
master, beam is slave. Tie explicitly uses COMPUTED, adjust=ON,
tieRotations=ON and thickness=ON; other parameters retain Abaqus defaults.
Both front/rear regions are selected before any Tie creation. Matching objects
are reused; different definitions or a partial run without a matching successful
report fail. Preserve the runtime report with the model for repeat execution.

Use a fresh Step02 + Step04 model for this new rule. Older Extend Face experiments
made braces independent and are not a compatible starting state for Part-local
edits. This rule does not silently rebuild or replace those instances. No Step02
or Step04 source is modified. ANG28 manual validation precedes ANG18/ANG33 tests.
## Abaqus runtime compatibility contract

All ten Step05 CAE templates use explicit loops instead of generator expressions.
The desktop-only `runtime_compatibility.py` lint rejects GeneratorExp, DictComp,
Yield and YieldFrom in final emitted code. Both production/legacy analysis script
writers and the historical minimal validation writers run the lint before writing.
Desktop input parsing is separate and is not embedded into the CAE process.

Run `python scripts/step05_check_runtime_compatibility.py --script <generated.py>`
to scan the templates and a generated artifact independently of regular tests.
The lint is a coding-contract check, not proof of Abaqus kernel compatibility.
Tests also run the simple executor with reducers that reject generator inputs.

The current BEAM_BRACE_TIE runtime no longer collects whole-Part area_before /
area_after statistics. The WEB patch completeness check still explicitly sums
`float(face.getSize(printResults=False))` in a loop; it is part of region selection.
Historical executor area checks remain, implemented as loops for regression parity.

### ANG28 manual validation and repository name compatibility

User-confirmed Abaqus/CAE 2020 result (SP_SC_ANG28_1042110101170S-T0204):

- Beam C +/- 50 mm partition: PASS.
- Beam E +/- 50 mm partition: PASS.
- BRACE_FRONT 50 mm end partitions: PASS.
- BRACE_REAR 50 mm end partitions: PASS.

The subsequent Set creation failed because Python 2 JSON Unicode names reached
Abaqus object creation unchanged. This is a naming compatibility defect, not a
geometry failure. Part-local XY datum planes, face selection, SIDE2, brace master /
beam slave, and Tie parameters are unchanged. Set/Surface/Tie creation still needs
manual verification with the regenerated script from a clean Step02 + Step04 model.

The formal executor uses `abaqus_name` at repository lookup and creation boundaries:
Python 2 Unicode ASCII becomes byte str; Python 3 uses native str; None becomes an
empty string; non-ASCII names fail explicitly. Set/Surface/Tie and Feature changeKey
arguments are checked by the generated-script compatibility gate. Any future RP,
Coupling, Connector, Boundary or Load implementation must apply the same helper;
no such objects are implemented by this fix. JSON report text is not renamed.

### COLUMN_COLUMN_TIE: entire actual overlap

Both `STEP05_TIE_BEAM_BRACE_FRONT` and `STEP05_TIE_BEAM_BRACE_REAR` have
user-confirmed Abaqus/CAE 2020 success on the real ANG28 model. Their runtime
functions and engineering rules remain frozen; the generated entry point runs
the independent column rule afterward.

The former two end bands and `column_tie_length_mm` have been removed. Both
real and example `analysis.xlsx` now contain `Column_Tie_Config!A1:B2`:

| rule_id | enabled |
| --- | --- |
| COLUMN_COLUMN_TIE | TRUE |

FALSE disables column resolution/execution. An absent sheet preserves older
beam-only workbooks. Old length-based schemas are rejected explicitly. No
coordinates, overlap lengths, radii, names, masks or sides are user inputs.

`column_axis.py` contains small shared Python 2.7-compatible axial calculations,
used by the planner and embedded runtime. It derives +local-Z direction from
placement rotations, or an explicit final axis_direction, and uses the lower
column direction as the common axis. Axial coordinates are scalar projections
from the global origin onto that direction (equal to global Z for ANG28).
Parallel and antiparallel local axes are allowed; nonparallel or noncoaxial
columns fail. Both endpoints are checked against the common axis line.

The Part-local origin comes from summary final_origin when present, otherwise
translation. Runtime independently checks actual Instance cylinder bounds and
Part/Instance vertex axial correspondence. Thus stale or ambiguous summary
placement fails instead of guessing translation/rotation order. No _s5_pose,
macro, general pose inference, cut or material removal is introduced.

Global ranges are sorted projections of each Part's two endpoints. Their
intersection must exceed 1e-6 m, otherwise fail with
`COLUMN_COLUMN_TIE has no valid axial overlap`. Each boundary is converted
back into that Part's local station, including reversed local axes. Only
strictly interior stations create XY datum planes and Part-local partitions;
natural endpoints create no Datum or Partition. The same helper protects
against redundant cuts if called at a natural endpoint.

After regeneration, the complete local-overlap cylindrical faces are selected.
Local bounds exclude end faces and outside regions. Instance curvature, radius
and radial normal checks identify cylindrical shell faces. Shell physical side
uses normal versus the direction perpendicular to the actual column axis:
upper OUTER, lower INNER; reversed normals reverse SIDE1/SIDE2. Ambiguity fails.
The three-coordinate sample sent to the normal/curvature API excludes any normal
payload in shell pointOn. API reference:
[Abaqus Face object](https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-facepyc.htm).

Selected face boundary vertices are projected onto the common axis to measure
both actual surface ranges. Both must equal the computed overlap within 1e-6 m
before any column Set, Surface or Tie is created; otherwise fail with
`COLUMN_COLUMN_TIE regions do not share the same overlap interval`. No automatic
expansion, movement or geometric repair using Tie adjust is performed.

Stable names remain `STEP05_REGION_COLUMN_UP_DOWN`,
`STEP05_REGION_COLUMN_DOWN_UP`, corresponding `STEP05_SURF_...`, and
`STEP05_TIE_COLUMN_UP_DOWN`. Lower column is master, upper column slave;
COMPUTED / adjust ON / tieRotations ON / thickness ON remain unchanged.

Real ANG28 planned values, in metres:

| Item | Range / value |
| --- | --- |
| Upper length / OD / thickness | 2.506 / 0.168 / 0.0045 |
| Lower length / OD / thickness | 1.600 / 0.177 / 0.0045 |
| Upper global axial range | 1.050 to 3.556 |
| Lower global axial range | 0.000 to 1.600 |
| Actual overlap | 1.050 to 1.600 (length 0.550) |
| Upper local overlap / interior partition | 0.000 to 0.550 / 0.550 |
| Lower local overlap / interior partition | 1.050 to 1.600 / 1.050 |
| Both selected global surface ranges | 1.050 to 1.600 |

The old 100 mm rule correctly rejected nonoverlapping bands, but has been
superseded. The new entire-overlap success path, rotated and antiparallel axes,
natural-boundary reuse, invalid inputs and selection-range failures are tested
synthetically. The user has now confirmed the full-overlap column regions and Tie in real Abaqus/CAE 2020; this rule is frozen.

The beam report status/fingerprint retain their frozen reuse semantics. The
column_column_tie subsection has its own fingerprint, status, partitions,
computed ranges, sides, semantic mapping, mesh changes and errors; overall_status
reflects the combined result. The entry point reads the previous column report
before executing the beam rule. Same successful definition reuses; conflicting
or unverified existing column features fail. Reopen a clean Step02 + Step04 model
when changing from the old rule. Only affected Part meshes are removed and final
meshing is deferred. Material removed remains False.

### COLUMN_HOOP_TIE: two independent half-hoop connections

The three existing Beam/Brace and Column/Column Ties are user-confirmed on real
SP_SC ANG28 and frozen. Their planner output and runtime functions are preserved.
`Column_Hoop_Tie_Config` adds only `rule_id = COLUMN_HOOP_TIE`, `enabled = TRUE`.
No dimensions or side inputs are added; FALSE/absent sheet leaves this rule off.

The resolver selects one complete canonical HOOP group (legacy HOOP and
HOOP_ASSEMBLY_n codes supported) with A/B semantic pair members and one unique
COLUMN_DOWN Part owner. Multiple groups/candidates fail, rather than guessing.
The instances and Part names are read from the summary; normalized components
supply native PIPE shell and HOOP_BAND solid dimensions.

ANG28 planned values:

| Item | Value |
| --- | --- |
| Group | HOOP_01 |
| Instances | HOOP_01_A / HOOP_01_B |
| Shared unmodified solid Part | P_SP_SC_ANG28_HOOP |
| Column | COLUMN_DOWN_01 / P_SP_SC_ANG28_COLUMN_DOWN |
| Hoop inner radius / width | 0.0885 / 0.080 m |
| Column shell midsurface / physical outer radius | 0.08625 / 0.0885 m |
| Expected hoop band and column overlap | 1.260 to 1.340 m |
| Column-local axial cuts | 1.260 and 1.340 m |

Runtime uses actual Instance vertex projections along the verified column axis
for A/B bands and overlap. Both hoop widths and bands must agree. Non-overlap
fails with `COLUMN_HOOP_TIE has no valid axial overlap`. Hoop inner faces must
have the normalized inner radius, cylindrical curvature, inward radial normal,
and the overlap axial range; outer arcs, fillets, ears and end faces are rejected.
If a partially protruding hoop has no existing faces bounded by the overlap,
execution fails explicitly instead of modifying the HOOP solid or tying beyond
the overlap. No hoop mesh is touched.

The two inner-face area-weighted centroids must point to opposite sides of the
column axis. Their direction defines the through-axis divider. An actual
corresponding Part/Instance radial vertex expresses this direction in the column
cross-section basis; no generic pose fit, macro or guessed global plane is used.
Three stable datum points define the through-axis datum plane in the Part;
only the hoop axial band faces are partitioned circumferentially. Axial cuts use
XY datum planes and skip natural or existing boundaries. API reference:
[Abaqus DatumPlaneByThreePoints](https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-featurepyc.htm).

The existing frozen `cct_faces` resolver selects the full cylindrical band and
resolves physical OUTER. It is not duplicated. The new rule divides this band
into two equal-area half-regions, checks empty face intersection and complete
union, then pairs representative points to A/B by unique nearest distance.
Ambiguity, a face crossing the divider, incomplete coverage or duplicated column
half faces fails before either new Tie. Solid hoop surfaces use native side1Faces;
this is the solid-face API argument, not a shell SIDE1/SIDE2 engineering choice.

Names are STEP05_REGION_COLUMN_DOWN_HOOP_A/B and
STEP05_REGION_HOOP_A/B_COLUMN_DOWN, corresponding STEP05_SURF names, and
STEP05_TIE_COLUMN_DOWN_HOOP_A/B. Master is the matched shell column OUTER half;
slave is the respective solid hoop INNER surface. COMPUTED/ON/ON/ON parameters are
unchanged, and every object name passes through the ASCII compatibility helper.

Because the hoop band is inside the column-column overlap, generation schedules:
beam regions -> hoop geometry preparation -> column-column regions ->
hoop regions -> global slave preflight -> create all five Ties. This completes
all topology and slave checks before creating any new constraint. The original 550 mm column-column surface remains the
complete region, now including the extra subfaces. Starting the new rule on an
old model already containing the column Tie requires reopening clean Step02 +
Step04; it must not modify topology underneath that existing constraint.

On a successful repeat, matching hoop fingerprint/features/regions/constraints
are reused. A partial or conflicting hoop run fails. The main entry point reads
all prior rule reports before the beam report is rewritten. column_hoop_tie holds
partitions, band/ranges, side, radii, selected face IDs, pairings, two created flags,
mesh changes and errors; overall_status reflects the final stage. Only affected
column mesh is removed, final meshing is deferred, and Material removed = False.

Synthetic validation includes all five Ties and a second full reuse run,
non-overlap, mismatched pair bands, wrong faces, ambiguous mapping, duplicate
slave faces, no-op half partition, flipped shell normals, tilted column basis,
unchanged frozen functions and generated-script execution order. Real hoop
face IDs, physical shell side and both new Ties still require Abaqus manual
validation from a clean Step02 + Step04 model.

Physical-side and constraint hierarchy update:

- COLUMN_COLUMN: COLUMN_DOWN INNER master / COLUMN_UP OUTER slave, retaining
  the full actual axial overlap and existing PIPE physical-side resolver.
- COLUMN_HOOP A/B: COLUMN_DOWN OUTER half master / corresponding HOOP INNER
  solid face slave. COLUMN_DOWN is never slave in these three rules.
- Runtime prints COLUMN_DOWN INNER, COLUMN_DOWN OUTER and COLUMN_UP OUTER
  with their resolved SIDE1/SIDE2. No shell side is inferred from role alone.
- Shell SIDE1 and SIDE2 share midsurface nodes. Choosing opposite sides does
  not remove constraint conflicts.

The generated entry point stages every planned Tie, including reused Ties, in
Step05TieBatch. Before any new model.Tie call it checks slave face identities
(Instance + face index, ignoring physical side) only; node access is skipped during this geometry-first phase. Active existing unrelated
Ties are included; unresolved/empty slave regions fail closed. Identical indices
on different Instances are allowed, as is master region reuse. Geometry-only
models have no final mesh nodes to inspect; this check is not a solver-level
proof that the future mesh is free of overconstraints.

Duplicate slaves fail with instance, Tie names and overlapping region names.
Reports use PENDING_TIE_PREFLIGHT until the batch finishes, then record actual
Tie presence, creation and slave_preflight status. On preflight failure no new
Tie is created; successfully prepared geometry remains for inspection.

CAE geometry point compatibility update:

The formal generated executor uses one point3 helper in its shared runtime.
It normalizes flat and singleton-nested coordinate sequences and pointOn-bearing
objects to three finite floats. Shell Face.pointOn objects can carry six values;
only their coordinate triplet is extracted, preserving the former [:3] behavior.
Wrong dimensions and invalid coordinates fail explicitly; point/direction pairs
are supported by the subsequent compatibility update below.
The Face API documents pointOn as a tuple of tuples and shell normal payloads:
https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-facepyc.htm

cht_center still uses getCentroid (not the arbitrary face.pointOn sample), with
float area weights and explicit sx/sy/sz accumulation. Nested getCentroid results
are normalized before multiplication; empty/negligible total area fails. The
original failure was a raw getCentroid component multiplied by a float. The
exact real return structure is not inferred from the exception alone.

All coordinate/normal API inputs in the formal beam, column and hoop runtimes
are normalized before arithmetic: vertex positions, axial projections, shell
face points, face normals, hoop centroids and pairing representatives.
getVertices remains a sequence of topology IDs; getSize is cast to float.
Each hoop identification pass prints at most three radius-matching candidates,
including index, raw pointOn, normalized point, area, radius and raw centroid.
Malformed point/centroid diagnostics include the raw value before failure.
Partition rules, AnalysisPlan, physical sides, Tie hierarchy/parameters and
duplicate-slave preflight are unchanged. Nested-centroid fixtures exercise all
five Ties including repeat execution.

Confirmed CAE 2020 pointOn pair compatibility:

point3 now accepts ((x,y,z),(nx,ny,nz)) and array-like payloads whose first
entry is a finite numeric triple. It checks the payload itself first, then its
first entry, preserving singleton wrappers and existing six-scalar shell object
support. is_numeric_triple checks exactly three float-convertible finite values.
Invalid leading coordinates are never replaced by a later valid vector.
vector3 is separate: getNormal results use it, and it rejects point/direction
pairs and pointOn objects. Axis and placement inputs retain their existing path.
cht_center continues to normalize getCentroid and preserve area weighting.
Hoop diagnostics retain raw pointOn, normalized coordinate, area, radius and
centroid, and now include the explicit getNormal result. Tests include the exact
real failure sample and run the five-Tie regression with point/direction faces.

No-mesh slave preflight update:

Step05TieBatch.slave_geometry_keys now returns (ASCII instance_name, int face_index)
keys only. Physical shell side is deliberately ignored. Same face in the same
Instance conflicts; different faces in one Instance, or identical face indices
in distinct HOOP Instances, are allowed. Empty/non-geometric regions fail closed.
No getNodes, connectivity access or mesh generation is used in the preflight.
Node-level secondary validation is not implemented in this phase and always
reports skipped, even if a mesh exists. Instance.nodes length is read only for
mesh-availability diagnostics; it is never a prerequisite for Tie creation.
Per-Tie face IDs, geometry keys and mesh availability are printed and written to
slave_preflight.geometry_checks. All geometry checks finish before any new Tie.
Tests force getNodes to raise for mesh-free faces, covering successful creation
and genuine duplicate-face failure without node access or premature remeshing.

CAE Surface/Region naming compatibility:

Surface names travel explicitly from the stable REGION-to-SURF naming rule.
TieBatch stores tie_name, master/slave Surface objects, master/slave surface
repository keys, instance names and slave face IDs in region_records. Only
Abaqus Tie arguments are forwarded to model.Tie; metadata stays separate.
Preflight reports and errors use the supplied slave_surface_name. Geometry
keys remain (instance_name, face_index), independent of names and shell side.
Existing Tie reuse uses the stored Region-name tuple, or a unique identity
match in assembly.surfaces, to resolve repository keys; it never reads a Surface
name property. An unresolved/ambiguous key fails closed. Part/Feature names
retain their existing usage. All 13 Surface/Region .name accesses were removed
from the formal preflight and three executor reuse paths. Nameless Surface
fixtures test all five Ties on first execution and reuse, plus explicit report
names, unchanged conflict detection and no mesh dependency.

RP and distributing Couplings (pending real CAE validation):

The user has confirmed all five ANG28 Ties and slave preflight in CAE 2020.
Their engineering rules and runtime modules are frozen. The independent
column_beam_coupling planner/runtime adds one STEP05_RP_COLUMN_UP at the actual
column origin + local axis * length, verified against runtime PIPE geometry.
Two Couplings share that RP: STEP05_COUPLING_COLUMN_UP and
STEP05_COUPLING_BEAM_F. Both use DISTRIBUTING, WHOLE_SURFACE, UNIFORM weighting,
adjust=OFF, localCsys=None and all six u/ur switches ON.

Coupling_Config contains rule_id, enabled, column_top_length_mm, coupling_type,
u1, u2, u3, ur1, ur2, ur3. The supported enabled rule is COLUMN_BEAM_COUPLING.
Missing/disabled sheet preserves the previous Tie-only generation path.
Blank column_top_length_mm resolves to 50; this first version uses the natural
top ring EDGE region, so that reserved length does not create a face band.
The real and example workbooks include this sheet; their three Tie sheets are
unchanged.

STEP05_REGION_COLUMN_UP_TOP / STEP05_SURF_COLUMN_UP_TOP contain top ring edges.
STEP05_REGION_BEAM_F / STEP05_SURF_BEAM_F contain the F cross-section edges.
An existing SET_BEAM_SEC_F is validated and reused. If station edges already
exist without the Set, they are reused without partitioning. Only a missing F
section triggers one local XY datum partition, before the frozen Tie pipeline;
an already constrained model with missing F geometry fails and requests clean
Step02 + Step04 input. Only affected beam mesh may be removed; no final mesh or
native-node selection is used. Geometry edges become side1Edges Surfaces before
being passed to Coupling; an edge Set is not passed as a Surface.

API references:
https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-surfacepyc.htm
https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-couplingpyc.htm
https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-assemblypyc.htm

Couplings are created after the five-Tie batch finishes. Same-name RP, regions
and Couplings reuse matching definitions; conflicting coordinates, geometry
or parameters fail without deleting existing objects. The report adds a
column_beam_coupling section with selected edge IDs, F Set reuse, both Couplings,
mesh effects and the semantic RP name -> actual ReferencePoint ID mapping.
The actual ID is determined only inside CAE; coordinates use getCoordinates.

Current SP_SC_ANG28_1042110101170S-T0204 inputs resolve RP=(0,0,3.556) m,
F=(-0.05,0,3.586) m and beam-local F station=2.070 m. Desktop fixtures and
generated-script compatibility checks do not replace the next manual CAE run.
