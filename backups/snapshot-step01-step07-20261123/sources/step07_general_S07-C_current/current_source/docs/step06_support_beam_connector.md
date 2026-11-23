# Support–Beam connectors, P01–P04

## Current shared PURLIN_BOLT preset

CARTESIAN; LINEAR / UNCOUPLED; components F1/F2/F3 (U1/U2/U3) only. D11=5.0E8 N/m, D22=2.0E8 N/m, D33=2.0E8 N/m. No rotational or off-diagonal stiffness, nonlinear, plasticity, damage, friction or failure behavior is defined.

All eight Support-Purlin and Support-Beam connectors share STEP06_CONNECTOR_SECTION_PURLIN_BOLT. Reports record parameter_source=TEMPORARY_PRESET and behavior_status=PRESET_FOR_WORKFLOW_VALIDATION; these are not final calibrated values. Local 1 remains the bolt axis, local 2 the projected slot major axis, and local 3 their cross product.

For an existing completed Step06-B CAE, run `<project>_step06_b_purlin_bolt_preset_update.py`. It first verifies all eight wire assignments and all sixteen KINEMATIC translation-only couplings, then changes only the shared Section's behavior options. It writes an independent preset report. It does not create or modify loads: the existing 20000 N local-component-1 Connector Force preload is preserved. No BC, contact, placement, RP, wire or orientation is changed. New-build scripts create the same preset directly.

The original no-behavior benchmark described below is historical and is superseded by this preset.


## Formal Bolt Connector Coupling Rule (2026-10-11)

All sixteen Step06-B bolt couplings (P01-P04, Support-Purlin and Support-Beam, both sides) use **KINEMATIC, translations only**: U1/U2/U3=ON; UR1/UR2/UR3=OFF. Names, RP positions, hole regions, wires and orientations are unchanged. This rule was confirmed by the user's real Abaqus SP_SC ANG18 Connector Force preload case; no Step04 placement correction is required.

For an existing eight-connector CAE, run `<project>_step06_b_kinematic_coupling_update.py`. It preflights all sixteen names and calls Coupling.setValues only. It neither recreates connectors nor edits Section, K1/K2/K3 (5.0e8/2.0e8/2.0e8 N/m), preload, contact, Step04 placement or Step05 constraints. An independent `_step06_b_coupling_update_report.json` records the update; historical creation reports are retained. The fresh-build scripts also create the new coupling rule, but should not be rerun over existing connectors.

Local stabilizing BCs belong to future Step07. No BC, Load, Step or Job is added by this update. The existing creation generator's uncalibrated Section behavior is unchanged in this coupling-only task; the migration preserves the user's existing constitutive settings and preload.


Run the independent `<project>_step06_b_support_beam_connector_setup.py` on a CAE with successful Step06-A holes and all four Support–Purlin connectors. Keep the matching successful `_step06_b_connector_report.json` beside the script. Existing Purlin names are prerequisites; only the new SUPPORT_BEAM names are duplicate blockers.

The generator consumes the matching Step06-A plan/report, checks SHORT_LEG PS_TO_BEAM and the beam TOP_FLANGE local plane, and uses the reported centers and axes. Four supports target four distinct slots on INCLINED_BEAM_01. No hole operations are embedded in the new execution path.

The original Purlin source files are unchanged. The adapter calls the original executor with its original code and a private naming function binding. The solid wall and shell edge resolvers, translations-only kinematic DOFs, weighting, wire, section assignment and orientation APIs are reused. All four groups are resolved and checked before mutation; equal or overlapping Beam edge sets raise BEAM_HOLE_REGION_DUPLICATE. Live indices are diagnostic keys, never input selectors.

One existing empty-behavior CARTESIAN `STEP06_CONNECTOR_SECTION_PURLIN_BOLT` is required and reused. New objects: 8 RPs, 8 couplings, 4 wires, 4 orientations, 0 sections. Behavior remains TO_BE_CALIBRATED.

The report preserves original `connections` and adds `support_purlin_connections` and `support_beam_connections`. Unexpected kernel errors roll back only this batch's new objects using the validated rollback helper. A failed rollback requires reopening the CAE saved after Support–Purlin completion. No automatic CAE save occurs.

Regression checks compare existing Purlin RP coordinates/feature IDs, coupling parameters, wire lengths and datum axes. Wire edge indices are intentionally excluded because the assembly renumbers edges when new wires are created.

Generate with `scripts/step06_generate_support_beam_connector.py --folder <project-folder> --project <project-id>` using the Step06 build environment and PYTHONPATH=src. The Abaqus 2020 synthetic integration test is `tests/abaqus_support_beam_probe.py`; actual ANG18 CAE validation remains the user's acceptance step.
