# SP_SC HOOP-Brace — v0.2.12

Generate Selected / Generate All Ready now emits separate HOOP-Brace Plan and
setup script for SP_SC. Structure is read from assembly_summary, not project
prefix or angle. Both Front and Rear use HOOP_01_A by explicit engineering rule.
DP retains distinct front/rear groups.

The shared geometry builder selects a unique enabled hole by projected brace
start distance (or explicit semantic assignment), uses actual ROUND/SLOT profile
and hoop thickness, and selects the closer of the two axis-offset Brace RP
candidates. Ambiguous holes or offset direction stop before model mutation.
No global-Y, 5-mm, 16-mm or LEFT/RIGHT-name assumptions remain.

Run in order: hole_setup.py, connector_setup.py, hoop_brace_connector_setup.py.
The final script appends four RP, four KINEMATIC U123-only Couplings, two wires,
two orientations and one HOOP_BOLT Cartesian linear uncoupled Section.
Temporary stiffness is 5e8 / 2e8 / 2e8 N/m. No Load or preload is created.

Both sides use actual hole wall faces and existing Step05 start-50-mm brace WEB.
No holes or partitions are created. Live CAE validation of the existing eight
PURLIN connectors is mandatory; external PURLIN report is optional audit data.
All Front/Rear geometry and prerequisites pass before creation. Step05 and
existing PURLIN objects are compared before/after; failure rolls back additions.

ANG18, ANG28 and ANG33 real input Plans and isolated completed CAE copies have
been checked. Original user CAEs and workbooks are not changed. Manual validation
of the generated append scripts remains the final engineering acceptance.
