"""Central first-release rules; mesh sizes are workflow defaults, not design approval."""
import copy
import hashlib

RULE_VERSION = 'stage1-two-static-steps-1'
STAGE1_STEPS = [
    dict(name='STEP07_PRELOAD', previous='Initial', nlgeom=False, timePeriod=1.0,
         timeIncrementationMethod='AUTOMATIC', initialInc=0.01, minInc=1e-7, maxInc=1.0, maxNumInc=1000000),
    dict(name='STEP07_LOADING', previous='STEP07_PRELOAD', nlgeom=False, timePeriod=1.0,
         timeIncrementationMethod='AUTOMATIC', initialInc=0.01, minInc=1e-7, maxInc=1.0, maxNumInc=1000000),
]
# Names reserved only; stages 2-5 remain disabled and unimplemented.
STAGE_NAMES = {1:'step07_01_step',2:'step07_02_bc',3:'step07_03_mesh',4:'step07_04_load',5:'step07_05_inp'}
DEFAULTS = dict(units='m-N-Pa',
    step=dict(name='STEP07_STATIC',previous='Initial',nlgeom=False,
              initialInc=1.,maxInc=1.,minInc=1e-7,maxNumInc=1000),
    mesh=dict(size=.05,local_size=.008,by_role={
        'COLUMN_DOWN':.008,'COLUMN_UP':.025,'COLUMN_FRONT':.008,
        'COLUMN_REAR':.008,'HOOP':.008,'PURLIN_SUPPORT':.005}),
    enable_column_tie_correction=False,
    validation_assumptions=dict(fix_purlin_rp_rotations=False,fix_support_beam_rp_rotations=False))

def configuration(summary,cae,connection,loads):
    c=copy.deepcopy(DEFAULTS)
    roles={r['canonical_role'] for r in summary['instances']}
    c['mesh']['by_role']={k:v for k,v in c['mesh']['by_role'].items() if k in roles}
    c.update(model_name=summary['model_name'],input_cae=str(cae),
             connection_plan=str(connection),loads=copy.deepcopy(loads),rule_version=RULE_VERSION)
    c['job']=dict(name='Step07_'+hashlib.sha256(summary['project_id'].encode('utf-8')).hexdigest()[:16],submit=False)
    return c
