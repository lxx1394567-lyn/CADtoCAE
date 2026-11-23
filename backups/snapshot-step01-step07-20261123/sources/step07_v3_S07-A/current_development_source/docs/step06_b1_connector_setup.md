# Step06-B: P01-P04 connector geometry benchmark

## Current shared PURLIN_BOLT preset

CARTESIAN; LINEAR / UNCOUPLED; components F1/F2/F3 (U1/U2/U3) only. D11=5.0E8 N/m, D22=2.0E8 N/m, D33=2.0E8 N/m. No rotational or off-diagonal stiffness, nonlinear, plasticity, damage, friction or failure behavior is defined.

All eight Support-Purlin and Support-Beam connectors share STEP06_CONNECTOR_SECTION_PURLIN_BOLT. Reports record parameter_source=TEMPORARY_PRESET and behavior_status=PRESET_FOR_WORKFLOW_VALIDATION; these are not final calibrated values. Local 1 remains the bolt axis, local 2 the projected slot major axis, and local 3 their cross product.

For an existing completed Step06-B CAE, run `<project>_step06_b_purlin_bolt_preset_update.py`. It first verifies all eight wire assignments and all sixteen KINEMATIC translation-only couplings, then changes only the shared Section's behavior options. It writes an independent preset report. It does not create or modify loads: the existing 20000 N local-component-1 Connector Force preload is preserved. No BC, contact, placement, RP, wire or orientation is changed. New-build scripts create the same preset directly.

The original no-behavior benchmark described below is historical and is superseded by this preset.


## Formal Bolt Connector Coupling Rule (2026-10-11)

All sixteen Step06-B bolt couplings (P01-P04, Support-Purlin and Support-Beam, both sides) use **KINEMATIC, translations only**: U1/U2/U3=ON; UR1/UR2/UR3=OFF. Names, RP positions, hole regions, wires and orientations are unchanged. This rule was confirmed by the user's real Abaqus SP_SC ANG18 Connector Force preload case; no Step04 placement correction is required.

For an existing eight-connector CAE, run `<project>_step06_b_kinematic_coupling_update.py`. It preflights all sixteen names and calls Coupling.setValues only. It neither recreates connectors nor edits Section, K1/K2/K3 (5.0e8/2.0e8/2.0e8 N/m), preload, contact, Step04 placement or Step05 constraints. An independent `_step06_b_coupling_update_report.json` records the update; historical creation reports are retained. The fresh-build scripts also create the new coupling rule, but should not be rerun over existing connectors.

Local stabilizing BCs belong to future Step07. No BC, Load, Step or Job is added by this update. The existing creation generator's uncalibrated Section behavior is unchanged in this coupling-only task; the migration preserves the user's existing constitutive settings and preload.


The current generator discovers P01-P04 from Step06-A instance metadata and requires exactly one support and one local purlin per group. The validated P01 frame, region resolver and modeling calls are reused with group-specific names and coordinates. There are eight RPs, eight kinematic couplings, four wires, four orientations and **one shared CARTESIAN Section**. The single-P01 entry remains available for regression testing. The original P01 contract below describes the method reused for each group.

Every group completes preflight before any object is created. A kernel mutation failure triggers removal of only objects introduced by this batch; rollback failure is reported explicitly and requires reopening clean Step06-A CAE. `tests/abaqus_step06_groups_probe.py` verifies all four chains on shared Parts with independently rotated/translated instances, P04 rejection without mutation, and rollback after an injected P03 creation failure using Abaqus 2020.

Run the generated `<project>_step06_b_connector_setup.py` on a **clean, successful Step06-A CAE**. Do not rerun Step06-A or rerun B1 on a model containing B1 objects. No user CAE is opened or saved automatically. On a partial failure, reopen the clean Step06-A CAE before retrying.

Scope: SP_SC ANG18, PURLIN_SUPPORT_01 ↔ PURLIN_LOCAL_01 only. The independent generator reads the Step06-A plan and SUCCESS report, verifies project identity and the canonical plan SHA-256, and checks source/derived linkage and transformed centers. It never reads Excel or recalculates user hole offsets. Step06-A sources, plans, reports and geometry remain unchanged.

```powershell
$env:PYTHONPATH='src'
.venv_step06_build/Scripts/python.exe scripts/step06_generate_connector_setup.py --plan <step06_plan.json> --report <step06_hole_report.json> --output <project-folder>
```

Outputs have separate `_step06_b_connector_plan.json`, `_step06_b_connector_setup.py`, and runtime `_step06_b_connector_report.json` names. The HoleSetup EXE remains the Step06-A application; this benchmark uses the independent generator above.

## Region and object contract

All duplicate-name and geometry checks occur before mutation. Global capsule boundary probes identify live instance geometry without fixed face/edge indices. Support wall probes cover three thickness levels, test inward normals, and compare total selected area with slot perimeter × thickness. Shell probes check both straight sides and both semicircular ends, and compare perimeter. These checks bind the region to the expected center, 12 mm width and 40 mm length. Live indices are used only to assemble Abaqus GeomSequence objects after semantic resolution.

- RPs and control Sets: `STEP06_RP_P01_SUPPORT`, `STEP06_RP_P01_PURLIN`.
- Hole Sets: `STEP06_REGION_P01_SUPPORT_HOLE`, `STEP06_REGION_P01_PURLIN_HOLE`.
- Surfaces: `STEP06_SURF_P01_SUPPORT_HOLE` (solid wall faces), `STEP06_EDGE_P01_PURLIN_HOLE` (shell edges).
- Couplings: `STEP06_COUPLING_P01_SUPPORT`, `STEP06_COUPLING_P01_PURLIN`, `KINEMATIC`, `WHOLE_SURFACE`, U1/U2/U3 ON and UR1/UR2/UR3 OFF.
- Wire Feature and Set: `STEP06_WIRE_P01_PURLIN_BOLT`, exactly one unmeshable RP-to-RP assembly wire.
- Section: `STEP06_CONNECTOR_SECTION_PURLIN_BOLT`, `translationalType=CARTESIAN`, no behavior options.
- Datum: `STEP06_CSYS_P01_PURLIN_BOLT`; local 1 follows support→purlin, local 2 is the projected slot major direction, local 3 is their cross product. Axis sign is determined by RP order, since the hole axis is undirected.

The report distinguishes `SUCCESS` object creation from `behavior_status=TO_BE_CALIBRATED`. No stiffness, slip, preload, failure or friction is assigned. This benchmark is not a calibrated load-transferring bolt model. No mesh, analysis step, load, boundary condition or job is created.

## Abaqus API evidence

The installed **Abaqus/CAE 2020 kernel** was exercised with `cae noGUI` in a fresh, unsaved synthetic model. It accepted shell edge `Surface(side1Edges=...)`, six-DOF distributing `Coupling`, `ConnectorSection(translationalType=CARTESIAN)` with zero behavior options, `WirePolyLine(points=((rpA,rpB),), mergeType=IMPRINT, meshable=OFF)`, assembly `SectionAssignment`, and `ConnectorOrientation(localCsys1=..., orient2sameAs1=ON)`.

The full synthetic solid-slot/shell-slot chain is in `tests/abaqus_step06_b1_probe.py`. It also tests rotated/translated instances, preservation of all Part feature/topology/mesh/volume snapshots, and duplicate rejection. These tests do not replace manual acceptance on the actual ANG18 CAE.

Primary reference pages (published 2025; the installed 2020 kernel probe is the version-specific check):

- [Coupling constraints and shell-edge tributary lengths](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECSTRefMap/simacst-c-coupling.htm)
- [Surface API](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-surfacepyc.htm)
- [ConnectorSection API](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-connectorsectionpyc.htm)
- [ConnectorOrientation API](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-connectororientationpyc.htm)

## Step06-B 0.2.4: SP_SC capability and inherited hole profiles

The integrated Support-Purlin and Support-Beam families accept structure_type=SP_SC from assembly_summary metadata. Project names (ANG18/ANG28/ANG33) do not gate capability. P01-P04 topology, complete successful Step06-A evidence, source/target profile compatibility, axes and coaxial centers remain required.

Dimensions come from Step06-A Plan/report; 12x40 and 12x25 are no longer runtime requirements. SLOT length may equal width within 1e-9 m. Circular-equivalent profiles use 12 unique uniformly distributed perimeter probes and circumference pi*d; longer slots retain the existing capsule resolver. Source and target dimensions must agree.

Mechanics remain KINEMATIC translations only (U1/U2/U3 ON; UR1/UR2/UR3 OFF), shared CARTESIAN LINEAR UNCOUPLED PURLIN_BOLT (5e8, 2e8, 2e8 N/m), and the existing local frame. Preload is recorded only; no load is created. No HOOP-Brace expansion is included.

Abaqus 2020 synthetic kernel regressions cover both elongated slots and 8x8 mm circular-equivalent holes: 16 RPs, 16 couplings, 8 wires/connectors, one section, rollback, no new loads, and preservation of other models. Actual project geometry still requires manual CAE validation.
