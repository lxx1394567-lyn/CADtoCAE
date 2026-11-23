"""First-trial m-N-Pa mesh rules; not convergence-qualified."""
MESH_RULES=dict(version='stage3-3',sizes=dict(COLUMN_DOWN=.08,COLUMN_UP=.08,COLUMN_FRONT=.08,COLUMN_REAR=.08,
    INCLINED_BEAM=.08,BRACE_FRONT=.08,BRACE_REAR=.08,PURLIN_LOCAL=.01,PURLIN_SUPPORT=.01,HOOP=.015),
    local_size=.006,connection_size=.01,hoop_connection_size=.006,max_connection_edge_length=.2,
    hole_face_transition_size=.012,max_hole_face_area_fraction=.25,
    hoop_quality_repair_sizes=[.006,.0055,.005,.0045,.004],max_repair_edge_fraction=.85,
    circumference_divisions=16,deviation_factor=.1,min_size_factor=.1,max_estimated_elements=500000,
    max_actual_elements=500000,aspect_warning=10.,shape_warning=.05,
    role_overrides={},
    project_hoop_uniform_sizes={'SP_DC_ANG19_LUANLUANLUAN-T0203':{'HOOP_01':.008,'HOOP_02':.008,'HOOP_03':.008}},
    project_support_uniform_sizes={'SP_DC_ANG19_LUANLUANLUAN-T0203':.008},
    adjustment_reason='Protected-copy axial partitions for columns and bounded beam hole transitions; physical region membership checked before mesh. Existing mesh rejected. Not convergence validation.')
