"""Run with Abaqus 2020 cae noGUI, in outputs/step06_b1 after generating probe_runtime.py.

Creates only an unsaved synthetic model. Does not open or save user CAE files.
"""
from abaqus import mdb
from abaqusConstants import *
import part, assembly, interaction, section
import json, traceback, math

ns = {'__name__':'probe_runtime'}
execfile('probe_runtime.py',ns)
batch = ns['PLAN']
plan = batch['connections'][0]
result = {}


def slot(sketch):
    r=.006; h=.014
    sketch.Line(point1=(-h,-r),point2=(h,-r))
    sketch.ArcByCenterEnds(center=(h,0),point1=(h,-r),point2=(h,r),direction=COUNTERCLOCKWISE)
    sketch.Line(point1=(h,r),point2=(-h,r))
    sketch.ArcByCenterEnds(center=(-h,0),point1=(-h,r),point2=(-h,-r),direction=COUNTERCLOCKWISE)


try:
    m=mdb.Model(name='B1_SYNTHETIC_TEST')
    for name,solid in ((plan['source_part'],True),(plan['target_part'],False)):
        name=str(name)
        s=m.ConstrainedSketch(name=name,sheetSize=.2)
        s.rectangle(point1=(-.05,-.04),point2=(.05,.04))
        slot(s)
        p=m.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY)
        if solid:p.BaseSolidExtrude(sketch=s,depth=.005)
        else:p.BaseShell(sketch=s)
    a=m.rootAssembly
    for number,plan in enumerate(batch['connections']):
        a.Instance(name=str(plan['source_instance']),part=m.parts[str(plan['source_part'])],dependent=ON)
        a.Instance(name=str(plan['target_instance']),part=m.parts[str(plan['target_part'])],dependent=ON)
        a.translate(instanceList=(str(plan['target_instance']),),vector=(0,0,.0075))
        # Exercise global instance geometry after rotation and translation.
        names=(str(plan['source_instance']),str(plan['target_instance']))
        angle=-108.+10.*number; rad=angle*math.pi/180.
        a.rotate(instanceList=names,axisPoint=(0,0,0),axisDirection=(0,1,0),angle=angle)
        shift=(-1.7+number*.2,.02,2.6+number*.1)
        a.translate(instanceList=names,vector=shift)
        def rotate(v):return (math.cos(rad)*v[0]+math.sin(rad)*v[2],v[1],-math.sin(rad)*v[0]+math.cos(rad)*v[2])
        for key in ('rp_support','rp_purlin'):
            plan[key]=ns['add'](rotate(plan[key]),shift)
        for key in ('bolt_axis','slot_major_axis'):plan[key]=rotate(plan[key])
    a.regenerate()
    original_state=ns['bg_state'](m)
    last=batch['connections'][-1]
    original_center=last['rp_purlin']
    last['rp_purlin']=ns['add'](original_center,(.001,0,0))
    try:
        ns['execute_connector_groups'](batch,mdb,'bad_last_group_report.json')
        raise AssertionError('Invalid P04 accepted')
    except ValueError:
        assert ns['bg_state'](m)==original_state
        result['p04_preflight_zero_mutation']='PASS'
    finally:
        last['rp_purlin']=original_center
    original_execute=ns['execute_connector_b1']
    def injected_failure(p,*args,**kwargs):
        r=original_execute(p,*args,**kwargs)
        if p['connection_group']=='P03':raise ValueError('Injected P03 failure after mutation')
        return r
    ns['execute_connector_b1']=injected_failure
    try:
        ns['execute_connector_groups'](batch,mdb,'rollback_report.json')
        raise AssertionError('Failure injection did not run')
    except ValueError:
        assert ns['bg_state'](m)==original_state
        result['rollback_after_p03']='PASS'
    finally:
        ns['execute_connector_b1']=original_execute
    report=ns['execute_connector_groups'](batch,mdb,'synthetic_connector_report.json')
    result['chain']=report['status']
    result['part_preservation']=[r['part_regression_status'] for r in report['connections']]
    result['couplings']=len(m.constraints)
    result['rps']=len(a.referencePoints)
    result['assignments']=len(a.sectionAssignments)
    result['orientations']=len(a.connectorOrientations)
    result['behavior_options']=len(m.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT'].behaviorOptions)
    try:
        ns['bg_preflight'](batch,mdb)
        raise AssertionError('Duplicate run was not rejected')
    except ValueError as exc:
        if 'Existing B1 object' not in str(exc):raise
        result['duplicate_guard']='PASS'
    assert result['rps']==8 and result['couplings']==8 and result['assignments']==4 and result['orientations']==4
    assert len(m.sections)==1
    result['status']='SUCCESS'
except Exception:
    result['status']='FAILED';result['error']=traceback.format_exc()
with open('synthetic_probe_result.json','w') as h:json.dump(result,h,indent=2)
