"""Native-solid API contract tests; actual CAE kernel validation remains manual."""
from copy import deepcopy
import contextlib
import io
import json
import math
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import test_step06_derived as baseline
from test_step06_runtime import Part
from test_step06_project_tables import add_hoop
from cadtocae.hoop_hole_plan import unique_hoop_parts,build_hoop_hole_plan
from cadtocae.hole_setup import script_source
from cadtocae.runtime_compatibility import assert_runtime_compatible


class HoopPart(Part):
    def __init__(self,name,g):
        super().__init__(name,dict(leg_a_m=.2,leg_b_m=.1,t_m=g['thickness_m'],length_m=g['width_m']))
        self.g=g;self.volume=.0003;self.removal_scale=1.;self.faces=NS(findAt=self.face)
        self.vertices=[]
        for y in (0.,g['thickness_m']):
            for low,high in ((g['left_end_x_m'],-g['straight_tangent_x_m']),
                             (g['straight_tangent_x_m'],g['right_end_x_m'])):
                for x,z in ((low,0.),(high,0.),(high,g['width_m']),(low,g['width_m'])):
                    self.vertices.append(NS(pointOn=((x,y,z),)))
        self.nodes=[1,2];self.elements=[1]
    def feature(self,prefix):
        f=super().feature(prefix);f.isSuppressed=lambda:False;return f
    def face(self,*,coordinates,printWarning=False):
        x,y,z=coordinates
        if 0.<y<self.g['thickness_m']:
            for i,cut in enumerate(self.cut_calls):
                origin=cut['sketch'].kwargs['transform'][9:12]
                arcs=[v for k,v in cut['sketch'].calls if k=='arc']
                lines=[v for k,v in cut['sketch'].calls if k=='line']
                if arcs:
                    q=(x-origin[0],z-origin[2]);t=cut['depth']
                    a,b=arcs[0]['center'],arcs[1]['center']
                    def radial(point):
                        q=(point[0]-origin[0],point[2]-origin[2]);d=(b[0]-a[0],b[1]-a[1])
                        f=max(0.,min(1.,sum((q[k]-a[k])*d[k] for k in (0,1))/sum(v*v for v in d)))
                        v=(q[0]-a[0]-f*d[0],q[1]-a[1]-f*d[1]);r=math.hypot(*v)
                        return (-v[0]/r,0.,-v[1]/r)
                    for j,line in enumerate(lines):
                        p1,p2=line['point1'],line['point2'];d=(p2[0]-p1[0],p2[1]-p1[1]);length=math.hypot(*d)
                        along=sum((q[k]-p1[k])*d[k] for k in (0,1))/length
                        cross=(q[0]-p1[0])*d[1]-(q[1]-p1[1])*d[0]
                        if abs(cross)<1.e-10 and 0.<along<length:
                            return NS(index=10+4*i+j,getNormal=radial,getSize=lambda length=length,**kw:length*t)
                    mid=((a[0]+b[0])/2.,(a[1]+b[1])/2.)
                    for j,arc in enumerate(arcs):
                        c=arc['center'];r=math.dist(c,arc['point1'])
                        if abs(math.dist(q,c)-r)<1.e-9 and sum((q[k]-c[k])*(c[k]-mid[k]) for k in (0,1))>0.:
                            return NS(index=12+4*i+j,getNormal=radial,getSize=lambda r=r,**kw:math.pi*r*t)
                    continue
                radius=(cut['sketch'].area()/math.pi)**.5
                dx,dz=x-origin[0],z-origin[2]
                if abs(math.hypot(dx,dz)-radius)<1e-9:
                    return NS(index=10+i,getNormal=lambda point:(-(point[0]-origin[0])/radius,0.,-(point[2]-origin[2])/radius),
                              getSize=lambda **kw:2*math.pi*radius*cut['depth'])
        if abs(y)<1e-9:upper=False
        elif abs(y-self.g['thickness_m'])<1e-9:upper=True
        else:raise ValueError('No native face at specified Y')
        if x < -self.g['straight_tangent_x_m']:side=0
        elif x > self.g['straight_tangent_x_m']:side=1
        else:raise ValueError('Not on ear')
        index=(2 if upper else 0)+side
        return NS(index=index,getNormal=lambda **kw:(0,1 if upper else -1,0),
                  getVertices=lambda:tuple(range(index*4,index*4+4)))
    def MakeSketchTransform(self,**kw):
        return NS(matrix=lambda:(1,0,0,0,0,1,0,-1,0)+kw['origin'])
    def CutExtrude(self,**kw):
        assert kw['depth']==self.g['thickness_m']
        assert kw['flipExtrudeDirection'] is False
        self.cut_calls.append(kw)
        self.volume-=kw['sketch'].area()*kw['depth']*self.removal_scale
        return self.feature('Cut')


class HoopRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.base=baseline.Step06ATests('test_full_chain_one_shared_and_four_beam_holes')
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        summary,components={'instances':[]},[]
        add_hoop(summary,components)
        # Match the user's current ANG18 Part geometry and already-validated centers.
        components[0]['section_params_m'].update(diameter_m=.14,t_m=.005,left_extension_m=.08,right_extension_m=.08,transition_fillet_m=.005)
        rows=[]
        for side in ('LEFT','RIGHT'):
            rows.append(dict(part_name='PART_HOOP',hole_id='HOOP_'+side,end_reference=side,hole_type='ROUND',
                distance_from_end_mm=20,distance_from_side_mm=20,diameter_mm=16,enabled=True))
        hp=build_hoop_hole_plan(unique_hoop_parts(summary,components),rows)
        self.base.plan['hoop_hole_plan']=json.loads(json.dumps(hp))
        self.hoop=HoopPart('PART_HOOP',hp['part_geometry']['PART_HOOP'])
        self.base.parts[self.hoop.name]=self.hoop
        for m in summary['instances']:
            self.base.assembly.instances[m['instance_name']]=NS(partName=self.hoop.name,dependent=True,pose=deepcopy(m['placement']))
        self.source=script_source(self.base.plan,self.base.path)
        self.ns={'__name__':'hoop_test'};exec(self.source,self.ns)
    def run_all(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.ns['execute_step06_with_hoop'](self.base.plan,self.base.mdb,str(self.base.path),'test')
    def unchanged(self):
        self.base.unchanged()
    def after_hoop_regenerate(self,callback):
        def regenerate():
            if len(self.hoop.cut_calls)==2:callback()
        self.base.assembly.regenerate=regenerate
    def test_missing_feature_metadata_is_warning_with_geometry_pass(self):
        def missing():
            for name in list(self.hoop.features):
                if name.startswith('STEP06_HOLE_HOOP_'):del self.hoop.features[name]
        self.after_hoop_regenerate(missing)
        h=self.run_all()['hoop_validation']
        self.assertEqual(h['status'],'SUCCESS')
        for key in ('cut_geometry_status','volume_validation','assembly_inheritance_status'):self.assertEqual(h[key],'PASS')
        self.assertEqual(h['feature_repository_status'],'NOT_CONFIRMED_AFTER_REGENERATE')
        self.assertIn('HOOP cut feature repository entry not found after regenerate; geometry validation passed.',h['warnings'])
    def test_suppression_metadata_not_authoritative(self):
        def suppress():
            for name,f in self.hoop.features.items():
                if name.startswith('STEP06_HOLE_HOOP_'):f.isSuppressed=lambda:True
        self.after_hoop_regenerate(suppress)
        h=self.run_all()['hoop_validation']
        self.assertEqual(h['status'],'SUCCESS');self.assertEqual(h['feature_repository_status'],'NOT_CONFIRMED_AFTER_REGENERATE')
        self.assertTrue(all(e['feature_status']=='FOUND' for e in h['feature_evidence']))
    def test_suppression_api_exception_is_warning(self):
        def unavailable():
            def fail():raise RuntimeError('metadata API unavailable')
            for f in self.hoop.features.values():f.isSuppressed=fail
        self.after_hoop_regenerate(unavailable)
        self.assertEqual(self.run_all()['hoop_validation']['status'],'SUCCESS')
    def test_regenerate_volume_change_fails(self):
        self.after_hoop_regenerate(lambda:setattr(self.hoop,'volume',self.hoop.volume+1.e-6))
        with self.assertRaisesRegex(ValueError,'volume changed'):self.run_all()
        self.assertEqual(json.loads(self.base.path.read_text())['hoop_validation']['volume_validation'],'FAIL')
    def test_missing_wall_with_correct_total_volume_fails(self):
        original=self.hoop.face
        def missing(**kw):
            if 0<kw['coordinates'][1]<.005:raise ValueError('missing wall')
            return original(**kw)
        self.after_hoop_regenerate(lambda:setattr(self.hoop.faces,'findAt',missing))
        with self.assertRaisesRegex(ValueError,'missing wall'):self.run_all()
        h=json.loads(self.base.path.read_text())['hoop_validation']
        self.assertEqual(h['cut_geometry_status'],'FAIL');self.assertEqual(h['volume_validation'],'PASS')
    def test_blind_wall_area_fails_even_when_volume_matches(self):
        original=self.hoop.face
        def short(**kw):
            face=original(**kw)
            if face.index>=10:face.getSize=lambda **kw:math.pi*.016*.004
            return face
        self.after_hoop_regenerate(lambda:setattr(self.hoop.faces,'findAt',short))
        with self.assertRaisesRegex(ValueError,'through-thickness'):self.run_all()
    def test_cells_disappear_after_regenerate_fails(self):
        self.after_hoop_regenerate(lambda:setattr(self.hoop,'cells',[]))
        with self.assertRaisesRegex(ValueError,'no solid cells'):self.run_all()
    def test_instance_reference_lost_after_regenerate_fails(self):
        self.after_hoop_regenerate(lambda:self.base.assembly.instances.pop('HOOP_01_A'))
        with self.assertRaisesRegex(ValueError,'PART_REFERENCE'):self.run_all()
        h=json.loads(self.base.path.read_text())['hoop_validation']
        self.assertEqual(h['cut_geometry_status'],'PASS');self.assertEqual(h['assembly_inheritance_status'],'FAIL')
    def test_full_chain_shared_part_two_cuts_and_preserved_other_holes(self):
        poses={n:deepcopy(i.pose) for n,i in self.base.assembly.instances.items()}
        r=self.run_all();h=r['hoop_validation']
        self.assertEqual(r['status'],'SUCCESS');self.assertEqual(r['created_holes'],9)
        self.assertEqual(h['status'],'SUCCESS');self.assertEqual(h['created_holes'],2)
        self.assertEqual(h['execution_policy'],'MODIFY_SHARED_PART_ONCE')
        self.assertEqual(len(h['instance_inheritance']),4)
        self.assertEqual(len(self.base.support.cut_calls),2)
        self.assertEqual(len(self.base.local.removal_calls),1)
        self.assertEqual(len(self.base.beam.removal_calls),4)
        self.assertEqual(self.hoop.delete_mesh_calls,1)
        self.assertTrue(h['mesh_removed']);self.assertTrue(h['remesh_required'])
        self.assertEqual(h['mesh_nodes_before'],2)
        self.assertEqual({v['feature_name'] for v in h['holes']},{'STEP06_HOLE_HOOP_LEFT_01','STEP06_HOLE_HOOP_RIGHT_01'})
        for item,x in zip(h['holes'],[-.135,.135]):
            self.assertAlmostEqual(item['local_center'][0],x)
            self.assertEqual(item['local_center'][1:],[.0025,.02])
            self.assertAlmostEqual(item['removed_volume'],math.pi*.016**2/4*.005,places=14)
        self.assertAlmostEqual(h['removed_volume'],2*math.pi*.016**2/4*.005,places=14)
        self.assertEqual(poses,{n:i.pose for n,i in self.base.assembly.instances.items()})
        self.assertFalse(self.base.model.sketches)
    def test_second_hole_invalid_blocks_entire_model_before_mesh_or_cuts(self):
        self.base.plan['hoop_hole_plan']['driving_holes'][1]['local_center_m'][0]=.08
        with self.assertRaisesRegex(ValueError,'profile crosses'):self.run_all()
        self.unchanged()
    def test_edge_axis_shape_and_midplane_fail_before_mutation(self):
        original=deepcopy(self.base.plan['hoop_hole_plan']['driving_holes'][0])
        for change in ({'local_center_m':[-.15,.0025,.02]}, {'local_center_m':[-.135,.0025,.008]},
                       {'local_center_m':[-.135,.003,.02]}, {'local_axis':[0,0,1]},
                       {'hole_type':'INVALID'},{'width_m':0.}):
            self.base.plan['hoop_hole_plan']['driving_holes'][0]=dict(original,**change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_all()
            self.unchanged()
    def test_missing_independent_and_extra_references(self):
        instances=self.base.assembly.instances
        name='HOOP_01_A';instance=instances[name]
        for kind in ('independent','missing','extra'):
            if kind=='independent':instance.dependent=False
            elif kind=='missing':del instances[name]
            else:instances['EXTRA']=NS(partName=self.hoop.name,dependent=True)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_all()
            self.unchanged();instance.dependent=True;instances[name]=instance;instances.pop('EXTRA',None)
    def test_actual_thickness_mismatch(self):
        self.hoop.g=dict(self.hoop.g,thickness_m=.006)
        with self.assertRaisesRegex(ValueError,'No native face'):self.run_all()
        self.unchanged()
    def test_old_negative_y_geometry_rejected(self):
        self.hoop.vertices[0].pointOn=((-0.155,-.005,0.),)
        with self.assertRaisesRegex(ValueError,'negative-Y'):self.run_all()
        self.unchanged()
    def test_shell_or_wrong_extents_rejected(self):
        self.hoop.cells=[]
        with self.assertRaisesRegex(ValueError,'solid'):self.run_all()
        self.unchanged()
        self.hoop.cells=[1];self.hoop.vertices[0].pointOn=((-1.,0.,0.),)
        with self.assertRaisesRegex(ValueError,'extents'):self.run_all()
        self.unchanged()
    def test_partial_existing_features_fail_before_base(self):
        self.hoop.feature('STEP06_HOLE_HOOP_LEFT')
        with self.assertRaisesRegex(ValueError,'Existing HOOP features'):self.run_all()
        self.assertFalse(self.base.support.features);self.assertEqual(self.hoop.delete_mesh_calls,0)
    def test_mesh_failure_prevents_hoop_cut_and_preserves_base_report(self):
        with patch.object(self.hoop,'deleteMesh',return_value=None),self.assertRaisesRegex(ValueError,'mesh remains'):self.run_all()
        self.assertEqual(len(self.hoop.cut_calls),0)
        r=json.loads(self.base.path.read_text());self.assertEqual(r['support']['status'],'SUCCESS')
        self.assertEqual(r['hoop_validation']['status'],'FAILED');self.assertTrue(r['model_modified'])
    def test_bad_volume_reports_partial_model_and_does_not_retry(self):
        self.hoop.removal_scale=.5
        with self.assertRaisesRegex(ValueError,'volume mismatch'):self.run_all()
        r=json.loads(self.base.path.read_text());self.assertEqual(r['status'],'FAILED')
        self.assertEqual(r['hoop_validation']['created_holes'],1)
        self.assertEqual(r['created_holes'],8);self.assertEqual(len(self.hoop.cut_calls),1)
    def test_base_preflight_failure_does_not_touch_hoop(self):
        self.base.plan['instances'][0]['placement']['translation'][0]+=1.
        with self.assertRaisesRegex(ValueError,'SUMMARY_TRANSFORM'):self.run_all()
        r=json.loads(self.base.path.read_text());self.assertEqual(r['hoop_validation']['status'],'NOT_EXECUTED_BASE_FAILED')
        self.assertFalse(self.hoop.features);self.assertEqual(self.hoop.delete_mesh_calls,0)
    def test_no_mesh_and_duplicate_input(self):
        self.hoop.nodes=[];self.hoop.elements=[]
        r=self.run_all();self.assertFalse(r['hoop_validation']['mesh_removed'])
        self.assertEqual(self.hoop.delete_mesh_calls,0)
    def test_duplicate_hole_rejected(self):
        hp=self.base.plan['hoop_hole_plan'];hp['driving_holes'].append(deepcopy(hp['driving_holes'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate'):self.run_all()
        self.unchanged()
    def test_all_unique_parts_preflight_before_any_mutation(self):
        hp=self.base.plan['hoop_hole_plan'];other='PART_HOOP_2'
        hp['part_geometry'][other]=deepcopy(hp['part_geometry']['PART_HOOP'])
        p=HoopPart(other,hp['part_geometry'][other]);self.base.parts[other]=p
        self.base.assembly.instances['OTHER_HOOP']=NS(partName=other,dependent=True,pose={})
        for original in list(hp['driving_holes']):
            h=deepcopy(original);h['part_name']=other
            h['shared_part_info'].update(part_name=other,referencing_instances=['OTHER_HOOP'],
                expected_affected_instances=['OTHER_HOOP'],shared_part=False,execution_policy='MODIFY_PART_ONCE')
            hp['driving_holes'].append(h)
        hp['driving_holes'][-1]['local_center_m'][2]=.002
        with self.assertRaisesRegex(ValueError,'profile crosses'):self.run_all()
        self.unchanged()
    def test_slot_both_axes_plus_round_third_hole(self):
        holes=self.base.plan['hoop_hole_plan']['driving_holes']
        for h,axis in zip(holes,([1.,0.,0.],[0.,0.,1.])):
            h.update(hole_type='SLOT',width_m=.016,total_length_m=.030,local_major_axis=axis)
            h.pop('diameter_m',None)
        third=deepcopy(holes[0]);third.update(hole_id='HOOP_LEFT_02',hole_type='ROUND',width_m=.012,total_length_m=.012,local_major_axis=None)
        third['local_center_m'][2]=.060;holes.append(third)
        r=self.run_all()['hoop_validation']
        self.assertEqual(r['status'],'SUCCESS');self.assertEqual(r['created_holes'],3)
        self.assertEqual(len(self.hoop.cut_calls),3);self.assertEqual(self.hoop.delete_mesh_calls,1)
        self.assertEqual(r['cut_geometry_status'],'PASS')
        self.assertEqual(r['assembly_inheritance_status'],'PASS')
        self.assertEqual(len(self.base.support.cut_calls),2);self.assertEqual(len(self.base.beam.removal_calls),4)
        self.assertEqual([len(c['sketch'].calls) for c in self.hoop.cut_calls],[4,1,4])

    def test_overlap_runtime_preflight_before_any_mutation(self):
        holes=self.base.plan['hoop_hole_plan']['driving_holes']
        copy=deepcopy(holes[0]);copy['hole_id']='HOOP_LEFT_02';holes.append(copy)
        with self.assertRaisesRegex(ValueError,'HOOP_HOLE_OVERLAP'):self.run_all()
        self.unchanged();self.assertFalse(self.hoop.cut_calls)

    def test_generated_script_python2_and_lint(self):
        from lib2to3.refactor import RefactoringTool
        RefactoringTool([]).refactor_string(self.source+'\n','hoop_runtime')
        assert_runtime_compatible(self.source)
        self.assertIn('execute_step06_with_hoop(PLAN',self.source)
