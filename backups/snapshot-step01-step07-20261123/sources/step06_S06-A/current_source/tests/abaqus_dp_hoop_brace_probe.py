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
for c in batch['connections']:c['behavior_status']='PRESET_FOR_WORKFLOW_VALIDATION'
plan = batch['connections'][0]
result = {}


def slot(sketch):
    r=.006; h=.014
    sketch.Line(point1=(-h,-r),point2=(h,-r))
    sketch.ArcByCenterEnds(center=(h,0),point1=(h,-r),point2=(h,r),direction=COUNTERCLOCKWISE)
    sketch.Line(point1=(h,r),point2=(-h,r))
    sketch.ArcByCenterEnds(center=(-h,0),point1=(-h,r),point2=(-h,-r),direction=COUNTERCLOCKWISE)


try:
    m=mdb.Model(name=str(batch['project_id']))
    for name,solid in ((plan['source_part'],True),(plan['target_part'],False)):
        name=str(name)
        s=m.ConstrainedSketch(name=name,sheetSize=.2)
        s.rectangle(point1=(-.05,-.04),point2=(.05,.04))
        slot(s)
        if solid:
            h=.0065;r=.006;y=.022
            s.Line(point1=(-h,y-r),point2=(h,y-r))
            s.ArcByCenterEnds(center=(h,y),point1=(h,y-r),point2=(h,y+r),direction=COUNTERCLOCKWISE)
            s.Line(point1=(h,y+r),point2=(-h,y+r))
            s.ArcByCenterEnds(center=(-h,y),point1=(-h,y+r),point2=(-h,y-r),direction=COUNTERCLOCKWISE)
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
        angle=0.; rad=angle*math.pi/180.
        a.rotate(instanceList=names,axisPoint=(0,0,0),axisDirection=(0,1,0),angle=angle)
        shift=(-1.7+number*.2,.02,2.6)
        a.translate(instanceList=names,vector=shift)
        def rotate(v):return (math.cos(rad)*v[0]+math.sin(rad)*v[2],v[1],-math.sin(rad)*v[0]+math.cos(rad)*v[2])
        for key in ('rp_support','rp_purlin'):
            plan[key]=ns['add'](rotate(plan[key]),shift)
        for key in ('bolt_axis','slot_major_axis'):plan[key]=rotate(plan[key])
    a.regenerate()
    beam=m.Part(name='beam',dimensionality=THREE_D,type=DEFORMABLE_BODY)
    sk=m.ConstrainedSketch(name='beam',sheetSize=2)
    sk.rectangle(point1=(-.05,-.04),point2=(.65,.05))
    for n in range(4):
        x=n*.2;y=.022;h=.0065;r=.006
        sk.Line(point1=(x-h,y-r),point2=(x+h,y-r))
        sk.ArcByCenterEnds(center=(x+h,y),point1=(x+h,y-r),point2=(x+h,y+r),direction=COUNTERCLOCKWISE)
        sk.Line(point1=(x+h,y+r),point2=(x-h,y+r))
        sk.ArcByCenterEnds(center=(x-h,y),point1=(x-h,y+r),point2=(x-h,y-r),direction=COUNTERCLOCKWISE)
    beam.BaseShell(sketch=sk)
    a.Instance(name='INCLINED_BEAM_01',part=beam,dependent=ON)
    a.translate(instanceList=('INCLINED_BEAM_01',),vector=(-1.7,.02,2.6075))
    a.regenerate()
    sbplan=dict(project_id=batch['project_id'],support_purlin_connections=[],connections=[])
    for p in batch['connections']:
        c=dict(p);c.update(connection_family='SUPPORT_BEAM',target_instance='INCLINED_BEAM_01',target_part='beam',
            total_length_m=.025,support_hole_id='PS_TO_BEAM',target_surface='INCLINED_BEAM_TOP_FLANGE',
            beam_hole_feature='STEP06_HOLE_BEAM_'+p['connection_group']+'_FROM_SUPPORT',
            rp_support=ns['add'](p['rp_support'],(0,.022,0)),rp_purlin=ns['add'](p['rp_purlin'],(0,.022,0)))
        sbplan['connections'].append(c)
    integrated={'__name__':'integration_probe'}
    execfile('integrated_runtime.py',integrated)
    integrated['build_group_plan']=lambda holes,report,structure_type=None:batch
    integrated['build_support_beam_geometry']=lambda holes,report,structure_type=None:sbplan
    a.Set(name='STEP05_SET',vertices=a.instances[str(batch['connections'][0]['source_instance'])].vertices[0:1])
    m.Equation(name='STEP05_COUPLING_PROBE',terms=((1.0,'STEP05_SET',1),(-1.0,'STEP05_SET',2)))
    for suffix in ('-Copy','-origin'):
        mdb.Model(name=str(batch['project_id'])+suffix,objectToCopy=m)
    others={}
    for name in mdb.models.keys():
        if name!=m.name:others[name]=integrated['bg_state'](mdb.models[name])
    before=integrated['bg_state'](m)
    with open('input_report.json','w') as handle:json.dump({'status':'SUCCESS'},handle)
    ip=dict(integrated['PLAN']);ip['hole_report_path']='input_report.json'
    saved=sbplan['connections'][-1]['rp_purlin']
    sbplan['connections'][-1]['rp_purlin']=ns['add'](saved,(.001,0,0))
    try:
        integrated['execute_integrated_connectors'](ip,mdb,'integrated_report.json')
        raise AssertionError('Missing beam P04 geometry accepted')
    except ValueError as error:
        assert 'coaxial/parallel validation failed' in str(error),str(error)
        assert integrated['bg_state'](m)==before
        result['all_eight_preflight_zero_mutation']='PASS'
    finally:sbplan['connections'][-1]['rp_purlin']=saved
    original=integrated['sb_execute_one']
    def failure(p,*args):
        r=original(p,*args)
        if p['connection_group']=='P03':raise ValueError('Injected beam P03 failure')
        return r
    integrated['sb_execute_one']=failure
    try:
        integrated['execute_integrated_connectors'](ip,mdb,'integrated_report.json')
        raise AssertionError('Injection did not run')
    except ValueError as error:
        assert 'Injected beam P03 failure' in str(error),str(error)
        assert integrated['bg_state'](m)==before
        result['both_families_rollback']='PASS'
    finally:integrated['sb_execute_one']=original
    report=integrated['execute_integrated_connectors'](ip,mdb,'integrated_report.json')
    assert report['status']=='SUCCESS'
    assert report['structure_type']=='DP'
    assert report['created_rps']==report['expected_rps']==16
    assert report['created_couplings']==report['expected_couplings']==16
    assert report['created_wires']==report['expected_wires']==8
    assert report['created_connectors']==report['expected_connectors']==8
    assert len(a.referencePoints)==16 and len(m.constraints)==17 and len(a.sectionAssignments)==8
    assert len(m.sections)==1 and 'STEP05_COUPLING_PROBE' in m.constraints.keys()
    count=0
    for name,c in m.constraints.items():
        if name.startswith('STEP06_'):
            assert c.couplingType==KINEMATIC
            assert (c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3)==(ON,ON,ON,OFF,OFF,OFF)
            count+=1
    assert count==16 and len(m.loads)==0
    for name in others:
        assert integrated['bg_state'](mdb.models[name])==others[name]
    result['other_models_unchanged']='PASS'
    result.update(status='SUCCESS',rps=16,couplings=16,wires=8,connectors=8,sections=1,step05='PRESERVED',loads_created=0)
    hb={'__name__':'hb_probe'}
    execfile('hoop_runtime.py',hb)
    hp=hb['PLAN']
    with open('hoop_input.json') as handle:fixture=json.load(handle)
    members=dict((x['instance_name'],x) for x in fixture['summary']['instances'])
    holes=fixture['holes']['hoop_hole_plan']
    name=str(hp['connections'][0]['hoop_part'])
    sk=m.ConstrainedSketch(name='dp_hoop',sheetSize=1.)
    sk.rectangle(point1=(-.09,0.),point2=(.15,.04))
    for hole in holes['driving_holes']:
        x,z=hole['local_center_m'][0],hole['local_center_m'][2]
        r=hole['width_m']/2.;h=(hole['total_length_m']-hole['width_m'])/2.
        sk.Line(point1=(x-h,z-r),point2=(x+h,z-r))
        sk.ArcByCenterEnds(center=(x+h,z),point1=(x+h,z-r),point2=(x+h,z+r),direction=COUNTERCLOCKWISE)
        sk.Line(point1=(x+h,z+r),point2=(x-h,z+r))
        sk.ArcByCenterEnds(center=(x-h,z),point1=(x-h,z+r),point2=(x-h,z-r),direction=COUNTERCLOCKWISE)
    hoop=m.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY)
    hoop.BaseSolidExtrude(sketch=sk,depth=.003)
    def place(instance,placement):
        translation,pre,post=hb['step04_placement_phases'](placement)
        for rot in pre:a.rotate(instanceList=(instance,),axisPoint=tuple(rot['axis_point']),axisDirection=tuple(rot['axis_direction']),angle=rot['angle_deg'])
        a.translate(instanceList=(instance,),vector=tuple(translation))
        for rot in post:a.rotate(instanceList=(instance,),axisPoint=tuple(rot['axis_point']),axisDirection=tuple(rot['axis_direction']),angle=rot['angle_deg'])
    for c in hp['connections']:
        name=str(c['hoop_instance']);a.Instance(name=name,part=hoop,dependent=ON)
        a.rotate(instanceList=(name,),axisPoint=(0,0,0),axisDirection=(1,0,0),angle=90.)
        a.translate(instanceList=(name,),vector=(0,.003,0))
        place(name,members[c['hoop_instance']]['placement'])
        name=str(c['brace_part']);sk=m.ConstrainedSketch(name=name,sheetSize=1.)
        sk.Line(point1=(.03,0),point2=(0,0));sk.Line(point1=(0,0),point2=(0,.05));sk.Line(point1=(0,.05),point2=(.03,.05))
        brace=m.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY);brace.BaseShellExtrude(sketch=sk,depth=.2)
        for station in (.05,.15):
            datum=brace.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE,offset=station)
            brace.PartitionFaceByDatumPlane(faces=brace.faces[:],datumPlane=brace.datums[datum.id])
        name=str(c['brace_instance']);a.Instance(name=name,part=brace,dependent=ON);place(name,c['brace_placement'])
    rp=a.ReferencePoint(point=(0,0,0));a.features.changeKey(fromName=rp.name,toName='STEP05_RP_DP_PROBE')
    a.regenerate()
    before_hb=hb['bg_state'](m);saved=hp['connections'][1]['brace_rp_global']
    hp['connections'][1]['brace_rp_global']=hb['add'](saved,(0,.001,0))
    try:
        hb['execute_hoop_brace'](hp,mdb,'bad_hoop_report.json')
        raise AssertionError('Invalid rear accepted')
    except ValueError as error:
        assert 'SPACING' in str(error),str(error)
        assert hb['bg_state'](m)==before_hb
    finally:hp['connections'][1]['brace_rp_global']=saved
    original=hb['dp_hb_preserved']
    def failure(*args):raise ValueError('Injected regression failure')
    hb['dp_hb_preserved']=failure
    try:
        hb['execute_hoop_brace'](hp,mdb,'rollback_hoop_report.json')
        raise AssertionError('Injection did not run')
    except ValueError as error:
        assert 'Injected regression failure' in str(error),str(error)
        assert hb['bg_state'](m)==before_hb
    finally:hb['dp_hb_preserved']=original
    report=hb['execute_hoop_brace'](hp,mdb,'hoop_report.json')
    assert report['status']=='SUCCESS'
    assert len(a.referencePoints)==21 and len(a.sectionAssignments)==10 and len(m.sections)==2
    for c in hp['connections']:
        names=hb['dp_hb_names'](c['side'])
        for side in ('hoop','brace'):
            obj=m.constraints[str(names[side+'_coupling'])]
            assert obj.couplingType==KINEMATIC and (obj.u1,obj.u2,obj.u3,obj.ur1,obj.ur2,obj.ur3)==(ON,ON,ON,OFF,OFF,OFF)
        assert abs(a.getFeatureEdges(name=str(names['wire']))[0].getSize(printResults=False)-.003)<1.e-6
    assert len(m.loads)==0
    result.update(dp_hoop_status='SUCCESS',new_rps=4,new_couplings=4,new_wires=2,new_sections=1,
                  existing_eight_preserved='PASS',step05_preserved='PASS',preflight_zero_mutation='PASS',hoop_rollback='PASS')

except Exception:
    result['status']='FAILED';result['error']=traceback.format_exc()
with open('synthetic_probe_result.json','w') as h:json.dump(result,h,indent=2)


