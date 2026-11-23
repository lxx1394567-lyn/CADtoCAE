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
    sbns={'__name__':'sbtest'}
    execfile('support_beam_runtime.py',sbns)
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
    sbplan=dict(project_id=batch['project_id'],support_purlin_connections=report['connections'],connections=[])
    for p in batch['connections']:
        c=dict(p);c.update(connection_family='SUPPORT_BEAM',target_instance='INCLINED_BEAM_01',target_part='beam',
            total_length_m=.025,support_hole_id='PS_TO_BEAM',target_surface='INCLINED_BEAM_TOP_FLANGE',
            beam_hole_feature='STEP06_HOLE_BEAM_'+p['connection_group']+'_FROM_SUPPORT',
            rp_support=ns['add'](p['rp_support'],(0,.022,0)),rp_purlin=ns['add'](p['rp_purlin'],(0,.022,0)))
        sbplan['connections'].append(c)
    before_beam=sbns['bg_state'](m)
    p04=sbplan['connections'][-1];saved=p04['rp_purlin']
    p04['rp_purlin']=ns['add'](saved,(.001,0,0))
    try:
        sbns['execute_support_beam'](sbplan,mdb,'synthetic_connector_report.json')
        raise AssertionError('Invalid Beam P04 accepted')
    except ValueError:
        assert sbns['bg_state'](m)==before_beam
        result['beam_p04_zero_mutation']='PASS'
    finally:p04['rp_purlin']=saved
    original_sb=sbns['sb_execute_one']
    def fail_sb(p,*args):
        r=original_sb(p,*args)
        if p['connection_group']=='P03':raise ValueError('Injected beam failure')
        return r
    sbns['sb_execute_one']=fail_sb
    try:
        sbns['execute_support_beam'](sbplan,mdb,'synthetic_connector_report.json')
        raise AssertionError('Injection missing')
    except ValueError:
        assert sbns['bg_state'](m)==before_beam
        result['beam_rollback_preserves_purlin']='PASS'
    finally:sbns['sb_execute_one']=original_sb
    sb=sbns['execute_support_beam'](sbplan,mdb,'synthetic_connector_report.json')
    assert len(a.referencePoints)==16 and len(m.constraints)==16 and len(a.sectionAssignments)==8
    assert len(m.sections)==1
    result['support_beam']=sb['support_beam_status']
    result['beam_regions_unique']=sb['beam_region_uniqueness']
    result['existing_purlin_regression']=sb['purlin_regression_status']
    result['total_rps']=len(a.referencePoints)
    result['total_couplings']=len(m.constraints)
    result['total_wires']=len(a.sectionAssignments)
    result['total_sections']=len(m.sections)
    try:
        sbns['sb_preflight'](sbplan,mdb)
        raise AssertionError('Duplicate Beam family accepted')
    except ValueError as exc:
        assert 'Existing SUPPORT_BEAM object' in str(exc)
        result['beam_duplicate_guard']='PASS'
    update_ns={'__name__':'update_test'}
    execfile('coupling_update.py',update_ns)
    names=update_ns['bolt_coupling_names']()
    for name in names:
        c=m.constraints[name]
        assert c.couplingType==KINEMATIC
        assert (c.u1,c.u2,c.u3,c.ur1,c.ur2,c.ur3)==(ON,ON,ON,OFF,OFF,OFF)
    result['new_kinematic_couplings']=16
    # Existing-model migration: emulate the former distributing settings.
    for name in names:m.constraints[name].setValues(couplingType=DISTRIBUTING,ur1=ON,ur2=ON,ur3=ON)
    sec=m.sections['STEP06_CONNECTOR_SECTION_PURLIN_BOLT']
    import connectorBehavior
    sec.setValues(behaviorOptions=(connectorBehavior.ConnectorElasticity(components=(1,2,3),table=((5.0e8,2.0e8,2.0e8),)),))
    tables=[tuple(b.table) for b in sec.behaviorOptions]
    import step, load
    m.StaticStep(name='fixture_preload_step',previous='Initial')
    m.ConnectorForce(name='fixture_preload',createStepName='fixture_preload_step',
        region=a.sets['STEP06_WIRE_P01_PURLIN_BOLT'],f1=20000.)
    preload=m.steps['fixture_preload_step'].loadStates['fixture_preload'].f1
    before_parts=ns['b1_snapshot'](m)
    before_state=ns['bg_state'](m)
    before_axes=[]
    for feature in a.features.values():
        if str(feature.name).startswith('STEP06_CSYS'):
            d=a.datums[feature.id];before_axes.append((feature.id,tuple(d.axis1.direction),tuple(d.axis2.direction),tuple(d.axis3.direction)))
    update_ns['update_bolt_couplings'](mdb,'coupling_update_report.json',m.name)
    assert before_parts==ns['b1_snapshot'](m) and before_state==ns['bg_state'](m)
    assert tables==[tuple(b.table) for b in sec.behaviorOptions]
    assert m.steps['fixture_preload_step'].loadStates['fixture_preload'].f1==preload
    result['connector_force_preload_preserved']='PASS'
    for id,e1,e2,e3 in before_axes:
        d=a.datums[id];assert (e1,e2,e3)==(tuple(d.axis1.direction),tuple(d.axis2.direction),tuple(d.axis3.direction))
    result['existing_updated_couplings']=16
    result['section_and_orientation_preserved']='PASS'
    preset_ns={'__name__':'preset_test'}
    execfile('preset_runtime.py',preset_ns)
    preset_ns['validate_bolt_preset'](sec)
    # Change only the synthetic old stiffness to verify replacement of existing values.
    sec.setValues(behaviorOptions=(connectorBehavior.ConnectorElasticity(components=(1,2,3),table=((1.e8,1.e8,1.e8),)),))
    preset_ns['update_existing_bolt_preset'](mdb,'preset_update_report.json',m.name)
    preset_ns['validate_bolt_preset'](sec)
    assert before_parts==ns['b1_snapshot'](m) and before_state==ns['bg_state'](m)
    assert m.steps['fixture_preload_step'].loadStates['fixture_preload'].f1==20000.
    for id,e1,e2,e3 in before_axes:
        d=a.datums[id];assert (e1,e2,e3)==(tuple(d.axis1.direction),tuple(d.axis2.direction),tuple(d.axis3.direction))
    result['preset_existing_update']='PASS'
    result['preload_20000N_preserved']='PASS'
    result['status']='SUCCESS'
except Exception:
    result['status']='FAILED';result['error']=traceback.format_exc()
with open('synthetic_probe_result.json','w') as h:json.dump(result,h,indent=2)
