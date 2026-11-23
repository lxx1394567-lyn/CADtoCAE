import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from cadtocae.connector_setup import connector_script_source
from cadtocae.connector_b1_plan import build_b1_plan, fingerprint


def plan():
    return dict(project_id='SP_SC_ANG18_TEST',connection_group='P01',connection_family='PURLIN_BOLT',
        source_instance='PURLIN_SUPPORT_01',target_instance='PURLIN_LOCAL_01',
        source_part='support',target_part='purlin',rp_support=[0.,0.,.0025],rp_purlin=[0.,0.,.0075],
        bolt_axis=[0.,0.,1.],slot_major_axis=[1.,0.,0.],width_m=.012,total_length_m=.04,
        thickness_m=.005,connector_type='CARTESIAN',behavior_status='PRESET_FOR_WORKFLOW_VALIDATION')


def runtime():
    ns={'__name__':'test_runtime'}
    exec(connector_script_source(plan(),'unused.json'),ns)
    return ns


def completed_holes():
    p=plan()
    source=dict(connection_group='P01',hole_id='PS_TO_PURLIN',driving_hole_id='driving',
        source_instance=p['source_instance'],source_part=p['source_part'],hole_type='SLOT',
        width_m=.012,total_length_m=.04,local_center_m=p['rp_support'],
        local_axis=p['bolt_axis'],local_major_axis=p['slot_major_axis'],source_geometry={'t_m':.005})
    derived=dict(source_driving_hole_id='driving',derived_hole_id='derived',target_role='PURLIN_LOCAL',
        target_instance=p['target_instance'],target_part=p['target_part'])
    members=[dict(instance_name=p[s+'_instance'],part_name=p[s+'_part'],
                  placement={'translation':[0,0,0],'rotation_steps':[]}) for s in ('source','target')]
    holes=dict(project_id=p['project_id'],structure_type='SP_SC',driving_holes=[source],derived_holes=[derived],instances=members)
    target=dict(connection_group='P01',source_instance=p['source_instance'],target_instance=p['target_instance'],
        target_part=p['target_part'],hole_type='SLOT',width_m=.012,total_length_m=.04,
        source_global_center=p['rp_support'],intersection_global=p['rp_purlin'],local_center=p['rp_purlin'],
        global_hole_axis=p['bolt_axis'],global_major_axis=p['slot_major_axis'])
    return holes,dict(status='SUCCESS',project_id=p['project_id'],plan_fingerprint=fingerprint(holes),purlin_local=[target])


class ConnectorB1Tests(unittest.TestCase):
    def test_frame_right_handed(self):
        ns=runtime(); f=ns['b1_frame'](plan())
        self.assertEqual(f['connector_local_1'],(0.,0.,1.))
        self.assertEqual(f['connector_local_2'],(1.,0.,0.))
        self.assertEqual(f['connector_local_3'],(0.,1.,0.))

    def test_axis_sign_follows_rps(self):
        p=plan();p['bolt_axis']=[0.,0.,-1.]
        self.assertEqual(runtime()['b1_frame'](p)['connector_local_1'],(0.,0.,1.))

    def test_bad_frames_rejected(self):
        for key,value in [('rp_purlin',[.001,0.,.0075]),('rp_purlin',[0.,0.,.0025]),
                          ('slot_major_axis',[0.,0.,1.]),('bolt_axis',[0.,float('nan'),1.])]:
            with self.subTest(key=key,value=value):
                p=plan();p[key]=value
                with self.assertRaises(ValueError):runtime()['b1_frame'](p)

    def test_capsule_extents(self):
        points=runtime()['b1_probes']((0,0,0),(1,0,0),(0,0,1),.012,.04)
        self.assertAlmostEqual(max(p[0][0] for p in points),.020)
        self.assertAlmostEqual(min(p[0][0] for p in points),-.020)
        self.assertAlmostEqual(max(p[0][1] for p in points),.006)

    def test_geometry_resolution_ignores_repository_order(self):
        ns=runtime();p=plan(); perimeter=2*(.04-.012)+math.pi*.012
        class Edges:
            def __getitem__(self,key):
                return () if key.start==key.stop else (key.start,)
            def findAt(self,point,printWarning):
                x,y,z=point[0]
                # Four semantic segments; arbitrary live indices.
                k=11 if x>.014 else 33 if x<-.014 else 82 if y>0 else 7
                size=math.pi*.006 if k in (11,33) else .028
                return NS(index=k,getSize=lambda printResults: size)
        instance=NS(cells=[],edges=Edges())
        objects,proof=ns['b1_resolve'](instance,p['rp_purlin'],p,False)
        self.assertEqual(len(objects),4)
        self.assertAlmostEqual(proof['measured'],perimeter)

    def test_wrong_perimeter_rejected(self):
        class Edges:
            def findAt(self,*args,**kw):return NS(index=100,getSize=lambda **kw:1.)
        with self.assertRaisesRegex(ValueError,'perimeter'):
            runtime()['b1_resolve'](NS(cells=[],edges=Edges()),[0,0,0],plan(),False)

    def test_duplicate_preflight_no_geometry_access(self):
        p=plan(); ns=runtime()
        for name in ns['B1_NAMES'].values():
            a=NS(instances={p['source_instance']:None,p['target_instance']:None},
                 features={name:object()},sets={},surfaces={})
            m=NS(rootAssembly=a,constraints={},sections={})
            with self.assertRaisesRegex(ValueError,'Existing B1 object'):
                ns['b1_preflight'](p,NS(models={p['project_id']:m}))

    def test_no_hole_mutation_apis_in_generated_script(self):
        source=connector_script_source(plan(),'r.json')
        for forbidden in ('CutExtrude','PartitionFace','RemoveFaces','deleteMesh','Job('):
            self.assertNotIn(forbidden,source)

    def test_requires_matching_success_report(self):
        a={'project_id':'SP_SC_ANG18_TEST'}
        for r in ({'status':'FAILED'},{'status':'SUCCESS','project_id':a['project_id'],'plan_fingerprint':'stale'}):
            with self.assertRaisesRegex(ValueError,'SUCCESS'):
                build_b1_plan(a,r)

    def test_reuses_completed_centers_without_mutating_a(self):
        a,r=completed_holes();before=copy.deepcopy((a,r))
        b=build_b1_plan(a,r)
        self.assertEqual(b['rp_support'],r['purlin_local'][0]['source_global_center'])
        self.assertEqual(b['rp_purlin'],r['purlin_local'][0]['intersection_global'])
        self.assertEqual((a,r),before)

    def test_report_center_inconsistent_with_plan_rejected(self):
        a,r=completed_holes();r['purlin_local'][0]['intersection_global']=[1,2,3]
        with self.assertRaisesRegex(ValueError,'center'):build_b1_plan(a,r)

    def test_duplicate_derived_result_rejected(self):
        a,r=completed_holes();r['purlin_local']*=2
        with self.assertRaisesRegex(ValueError,'exactly one'):build_b1_plan(a,r)

    def test_generated_python2_syntax(self):
        from lib2to3.refactor import RefactoringTool
        RefactoringTool([]).refactor_string(connector_script_source(plan(),'report.json'),'b1.py')

    def test_unsupported_scope_fails_before_model_access(self):
        p=plan();p['connection_group']='P02'
        with self.assertRaisesRegex(ValueError,'scope'):
            runtime()['b1_preflight'](p,None)


if __name__=='__main__':unittest.main()
