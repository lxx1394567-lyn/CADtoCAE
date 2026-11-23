"""Run with Abaqus 2020 cae noGUI, in outputs/step06_b1 after generating probe_runtime.py.

Creates only an unsaved synthetic model. Does not open or save user CAE files.
"""
from abaqus import mdb
from abaqusConstants import *
import part, assembly, interaction, section
import json, traceback, math

ns = {'__name__':'probe_runtime'}
execfile('probe_runtime.py',ns)
plan = ns['PLAN']
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
    a.Instance(name=str(plan['source_instance']),part=m.parts[str(plan['source_part'])],dependent=ON)
    a.Instance(name=str(plan['target_instance']),part=m.parts[str(plan['target_part'])],dependent=ON)
    a.translate(instanceList=(str(plan['target_instance']),),vector=(0,0,.0075))
    # Exercise global instance geometry after rotation and translation.
    names=(str(plan['source_instance']),str(plan['target_instance']))
    angle=-108.; rad=angle*math.pi/180.
    a.rotate(instanceList=names,axisPoint=(0,0,0),axisDirection=(0,1,0),angle=angle)
    shift=(-1.7,.02,2.6)
    a.translate(instanceList=names,vector=shift)
    def rotate(v):return (math.cos(rad)*v[0]+math.sin(rad)*v[2],v[1],-math.sin(rad)*v[0]+math.cos(rad)*v[2])
    for key in ('rp_support','rp_purlin'):
        plan[key]=ns['add'](rotate(plan[key]),shift)
    for key in ('bolt_axis','slot_major_axis'):plan[key]=rotate(plan[key])
    a.regenerate()
    report=ns['execute_connector_b1'](plan,mdb,'synthetic_connector_report.json')
    result['chain']=report['status']
    result['part_preservation']=report['part_regression_status']
    result['couplings']=len(m.constraints)
    result['rps']=len(a.referencePoints)
    result['assignments']=len(a.sectionAssignments)
    result['orientations']=len(a.connectorOrientations)
    result['behavior_options']=len(m.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT'].behaviorOptions)
    try:
        ns['b1_preflight'](plan,mdb)
        raise AssertionError('Duplicate run was not rejected')
    except ValueError as exc:
        if 'Existing B1 object' not in str(exc):raise
        result['duplicate_guard']='PASS'
    result['status']='SUCCESS'
except Exception:
    result['status']='FAILED';result['error']=traceback.format_exc()
with open('synthetic_probe_result.json','w') as h:json.dump(result,h,indent=2)
