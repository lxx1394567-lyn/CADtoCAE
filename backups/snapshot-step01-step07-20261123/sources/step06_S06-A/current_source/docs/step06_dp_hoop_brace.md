# Step06 0.2.9 — DP HOOP ↔ BRACE

This family appends two connectors after the eight validated PURLIN connectors.
It does not create holes, partitions, meshes, loads or jobs. SP_SC retains its
existing single-group engineering rule and execution path.

## Mapping and geometry

- Resolve FRONT/REAR from summary hoop-group column/brace associations. When absent,
  require one unique group on the corresponding actual column axis. Never use group
  suffix order. Ambiguity raises `DP_HOOP_GROUP_MAPPING_AMBIGUOUS`.
- Half A for both sides is explicit in Plan, with separate configurable half fields.
- Search enabled holes only on that group's actual Part. Prefer explicit target
  semantics; otherwise use unique minimum distance to the brace start web midpoint,
  projected perpendicular to the actual hole axis. Ties within 1e-6 m fail with
  `DP_HOOP_BRACE_HOLE_AMBIGUOUS`. Hole names do not encode brace usage.
- HOOP RP is the planned hole center transformed by actual summary placement.
  Compare the two thickness-offset candidates with the finite 0–50 mm WEB rectangle
  in brace-local coordinates; require a unique closer side. Equal distances fail
  with `DP_BRACE_RP_SIDE_AMBIGUOUS`. Runtime verifies the existing patch geometry.
- Read ROUND/SLOT width, length, major axis and Part thickness from the Hole Plan.
  Reuse `b1_resolve` for hole walls and `hb_web` for the existing partitioned web.
  The slot major axis locates wall geometry; the brace axis defines connector local-2.

## Mechanics and preservation

Four KINEMATIC couplings, U123 ON / UR123 OFF; two wires; four RP; two orientations.
New shared `STEP06_CONNECTOR_SECTION_HOOP_BOLT`: CARTESIAN, LINEAR, UNCOUPLED,
D11=5e8 and D22=D33=2e8 N/m, TEMPORARY_PRESET / PRESET_FOR_WORKFLOW_VALIDATION.
Preload is metadata only: 20000 N, component 1, PRESERVE_EXISTING_NO_LOAD_CREATED.

All front/rear checks finish before mutation. Kernel failures roll back only new
objects. Snapshot existing PURLIN RP/coupling/wire/orientation/section bindings,
Part geometry, and the safe Step05 name/ID/type/suppression contract. Never enumerate
Feature members. The separate HOOP-Brace report carries the prior eight connection
records without overwriting their original successful report.

## ANG14 validation handoff

Summary explicitly maps HOOP_01 to COLUMN_FRONT_01 and HOOP_02 to COLUMN_REAR_01.
Both A halves select their own HOOP_RIGHT_01 by distance among three slot candidates.
Slot size: 14×25 mm; thickness: 3 mm. Global coordinates in metres:

| Side | HOOP RP | BRACE RP |
| --- | --- | --- |
| FRONT | (-1.28, +0.0015, 0.50) | (-1.28, -0.0015, 0.50) |
| REAR | (+1.28, -0.0015, 0.53) | (+1.28, +0.0015, 0.53) |

After user execution, expected totals: 20 RP, 20 couplings, 10 wires/connectors,
two bolt sections. Actual ANG14 model validation is pending. ANG35 generator
regression uses actual summary/components with explicitly synthetic hole inputs
in an isolated copy; it does not certify engineering dimensions.


## v0.2.11: live CAE prerequisite

DP HOOP-Brace validates all eight existing PURLIN connectors directly in the current CAE: RP features/sets, KINEMATIC U123 Couplings, single-edge Wires, Connector orientations and PURLIN_BOLT assignments/preset. Missing or invalid live objects fail with PURLIN_CONNECTORS_REQUIRED before mutation.

The Plan optional_audit_path (legacy purlin_report_path) is supplementary. Missing reports produce PURLIN_REPORT_MISSING; invalid project/status/family records produce PURLIN_REPORT_INVALID. Neither replaces live checks. Valid reports retain historical family records; otherwise the output records LIVE_CAE evidence. Hole geometry, RP positions, stiffness and orientation generation are unchanged.
