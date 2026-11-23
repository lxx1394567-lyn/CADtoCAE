# Step06 v0.2.10 — SP_DC PURLIN Connector

SP_DC now uses the existing SP_SC / DP two-family Connector runtime, without
changing hole geometry, region resolvers, reference points, Coupling APIs,
Section presets or orientation algorithms. Structure comes from
assembly_summary.structure_type, never the project filename prefix.

Generate All Ready produces `<project>_step06_connector_plan.json` and
`<project>_step06_connector_setup.py`. BatchRunner already discovers this
standard filename as its Connector stage; an additional HOOP script is not
required. Run after the matching successful Step06-A report, on the model
with Step05 and the required Support/Purlin/Beam holes already present.

P01–P04 Support↔Purlin and Support↔Beam create 16 RP, 16 KINEMATIC
translations-only Couplings, eight Wire/Connector objects and one shared
PURLIN_BOLT Section. CARTESIAN, LINEAR, UNCOUPLED stiffness remains
D11=5e8, D22=D33=2e8 N/m (temporary preset). No preload load is created;
20000 N / local-1 remains metadata only. All eight connections are validated
before mutation, including four distinct Beam hole regions. The safe Step05
snapshot and rollback remain unchanged.

SP_DC GUI diagnostics separately show PURLIN_CONNECTOR_READY and
HOOP_CONNECTOR_NOT_DEVELOPED. KNOWN_ISSUE_SP_DC_HOOP_MULTIHOLE is recorded
but not fixed here. HOOP report geometry is not a prerequisite of these two
families; overall matching SUCCESS Step06-A report and actual required hole
geometry remain mandatory. No HOOP features are modified.

ANG17 was checked using its actual completed Plan/report and an isolated copy
of its CAE in Abaqus/CAE 2020. The original CAE and workbooks are preserved.
ANG21/ANG28 generator regressions use actual summary/components but borrowed
ANG17 dimensions in isolated outputs because their user workbooks lack input;
these checks do not constitute engineering validation of their hole locations.
