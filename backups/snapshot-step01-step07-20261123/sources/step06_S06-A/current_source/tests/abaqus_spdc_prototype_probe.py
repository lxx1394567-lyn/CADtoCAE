"""Unsaved synthetic native solids only; never opens a user's CAE."""
from abaqus import mdb
from abaqusConstants import *
import part,assembly,mesh,interaction,load,json,traceback,copy
ns={'__name__':'probe'}
execfile('runtime.py',ns)
profile={}
execfile('profile.py',profile)
result={}
try:
    with open('components.json') as f:components=json.load(f)
    plan=ns['PLAN'];m=mdb.Model(name=str(plan['project_id']));a=m.rootAssembly
    for c in components:
        sketch=m.ConstrainedSketch(name='PROFILE',sheetSize=2.)
        profile['_draw_hoop_band_profile'](sketch,c)
        p=m.Part(name=str(c['part_name']),dimensionality=THREE_D,type=DEFORMABLE_BODY)
        p.BaseSolidExtrude(sketch=sketch,depth=c['section_params_m']['width_m'])
        del m.sketches['PROFILE']
        p.seedPart(size=.03)
        p.setMeshControls(regions=p.cells[:],elemShape=TET,technique=FREE)
        p.generateMesh()
    placements={}
    for pair in plan['hoop_hole_plan']['prototype_inheritance']['pairs']:
        for side in ('source','target'):placements[pair[side+'_instance']]=pair[side+'_placement']
    for member in plan['hoop_hole_plan']['instance_mapping']:
        name=str(member['instance_name']);p=m.parts[str(member['part_name'])]
        a.Instance(name=name,part=p,dependent=ON)
        translation,pre,post=ns['step04_placement_phases'](placements[name])
        for rotation in pre:
            a.rotate(instanceList=(name,),axisPoint=tuple(rotation['axis_point']),axisDirection=tuple(rotation['axis_direction']),angle=rotation['angle_deg'])
        a.translate(instanceList=(name,),vector=translation)
        for rotation in post:
            a.rotate(instanceList=(name,),axisPoint=tuple(rotation['axis_point']),axisDirection=tuple(rotation['axis_direction']),angle=rotation['angle_deg'])
    a.regenerate()
    before={}
    for name,p in m.parts.items():before[name]=(len(p.nodes),ns['s6h_volume'](p))
    bad=copy.deepcopy(plan);bad['hoop_hole_plan']['instance_mapping'].pop()
    try:
        ns['s6h_prepare'](bad,m,dict(parts=[]))
        raise AssertionError('incomplete pattern accepted')
    except ValueError as e:assert 'SPDC_HOOP_REFERENCE_MISMATCH' in str(e)
    for name,p in m.parts.items():assert before[name]==(len(p.nodes),ns['s6h_volume'](p))
    moved=str(plan['hoop_hole_plan']['prototype_inheritance']['pairs'][0]['target_instance'])
    a.translate(instanceList=(moved,),vector=(.001,0.,0.));a.regenerate()
    try:
        ns['s6h_prepare'](plan,m,dict(parts=[]))
        raise AssertionError('incorrect live placement accepted')
    except ValueError as e:assert 'ACTUAL_PLACEMENT_MISMATCH' in str(e),str(e)
    a.translate(instanceList=(moved,),vector=(-.001,0.,0.));a.regenerate()
    report=dict(parts=[]);prepared=ns['s6h_prepare'](plan,m,report)
    ns['s6h_execute'](m,prepared,report)
    assert report['status']=='SUCCESS'
    assert report['prototype_inheritance']['global_hole_geometry_status']=='PASS'
    assert len(report['prototype_inheritance']['global_hole_geometry_checks'])==24
    assert report['unique_part_cut_count']==8 and report['assembly_instance_hole_count']==24
    for entry in report['parts']:
        assert entry['actual_cut_features']==4 and entry['mesh_removed']
        assert entry['volume_validation']==entry['cut_geometry_status']==entry['assembly_inheritance_status']=='PASS'
    assert len(a.referencePoints)==len(m.constraints)==len(m.loads)==0
    result=dict(status='SUCCESS',report=report,incomplete_pattern_zero_mutation='PASS')
except Exception:result=dict(status='FAILED',error=traceback.format_exc(),report=locals().get('report'))
with open('kernel_result.json','w') as f:json.dump(result,f,indent=2)
