"""Run in prepared outputs/step06_v2/kernel with Abaqus 2020 cae noGUI.

Only unsaved synthetic geometry; never opens/saves any user CAE.
profile.py is the unchanged Step02 tangent-chain drawing helper.
"""
from abaqus import mdb
from abaqusConstants import *
import part, assembly, mesh, interaction, load
import json, traceback, copy

ns={'__name__':'probe'}
execfile('runtime.py',ns)
profile={}
execfile('profile.py',profile)
result={}
try:
    with open('component.json') as f:component=json.load(f)
    plan=ns['PLAN']
    model=mdb.Model(name=str(plan['project_id']))
    sketch=model.ConstrainedSketch(name='HOOP_PROFILE',sheetSize=1.)
    profile['_draw_hoop_band_profile'](sketch,component)
    p=model.Part(name='PART_HOOP',dimensionality=THREE_D,type=DEFORMABLE_BODY)
    p.BaseSolidExtrude(sketch=sketch,depth=component['section_params_m']['width_m'])
    a=model.rootAssembly
    for index,name in enumerate(plan['hoop_hole_plan']['driving_holes'][0]['shared_part_info']['referencing_instances']):
        a.Instance(name=str(name),part=p,dependent=ON)
        a.translate(instanceList=(str(name),),vector=(0.,0.,index*.3))
    a.regenerate()
    p.seedPart(size=.02)
    p.setMeshControls(regions=p.cells[:],elemShape=TET,technique=FREE)
    p.generateMesh()
    assert len(p.nodes)>0
    before=ns['s6h_volume'](p)
    bad=copy.deepcopy(plan)
    duplicate=copy.deepcopy(bad['hoop_hole_plan']['driving_holes'][0])
    duplicate['hole_id']='HOOP_LEFT_03'
    bad['hoop_hole_plan']['driving_holes'].append(duplicate)
    nodes=len(p.nodes)
    try:
        ns['s6h_prepare'](bad,model,dict(parts=[]))
        raise AssertionError('overlap accepted')
    except ValueError as exc:
        assert 'HOOP_HOLE_OVERLAP' in str(exc),str(exc)
    assert len(p.nodes)==nodes and ns['s6h_volume'](p)==before
    report=dict(parts=[])
    prepared=ns['s6h_prepare'](plan,model,report)
    ns['s6h_execute'](model,prepared,report)
    assert report['status']=='SUCCESS'
    entry=report['parts'][0]
    assert entry['created_holes']==3 and entry['mesh_removed']
    assert entry['cut_geometry_status']=='PASS' and entry['volume_validation']=='PASS'
    assert entry['assembly_inheritance_status']=='PASS'
    assert len(entry['instance_inheritance'])==4
    assert len([name for name in p.features.keys() if name.startswith('STEP06_HOLE_')])==3
    assert len(a.referencePoints)==0 and len(model.constraints)==0 and len(model.loads)==0
    result=dict(status='SUCCESS',report=report,overlap_preflight_zero_mutation='PASS',
                profiles=['SLOT_PLATE_LENGTH_16x30','ROUND_16','SLOT_BAND_WIDTH_16x30'])
except Exception:
    result=dict(status='FAILED',error=traceback.format_exc(),report=locals().get('report'))
with open('kernel_result.json','w') as f:json.dump(result,f,indent=2)
