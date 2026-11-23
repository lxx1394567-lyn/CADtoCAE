"""Step06-A transforms and face-local removal contracts; no Abaqus kernel claims."""
from copy import deepcopy
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import patch

from cadtocae.hole_inputs import normalize_hole_rows
from cadtocae.hole_plan import build_step06_a_plan
from cadtocae.hole_setup import script_source
from cadtocae.analysis_geometry import placement_candidates, transform, matvec, rotate_point
from cadtocae.runtime_compatibility import assert_runtime_compatible
from test_step06_hole_plan import fixture
from test_step06_hole_inputs import input_rows
from test_step06_runtime import Part, Features, Sketch


def fixture_a():
    summary, components=fixture()
    members=[]
    rotation=[dict(axis_point=[0.,0.,0.],axis_direction=[0.,0.,1.],angle_deg=90.)]
    for n in range(1,5):
        for index in (0,1):
            m=deepcopy(summary['instances'][index]);m.update(instance_name=m['component_code']+'_%02d'%n,connection_group='P%02d'%n)
            m['placement']=dict(translation=[0.,0.,.2+(n-1)*.4],rotation_steps=[])
            if index==1:m['placement'].update(translation=[.1,0.,.2+(n-1)*.4],rotation_steps=rotation)
            members.append(m)
    beam=deepcopy(summary['instances'][2]);beam['placement']=dict(translation=[.103,.01,0.],rotation_steps=rotation)
    members.append(beam);summary['instances']=members
    for m in members:
        m['transform_anchors']=[dict(name='fixture assembly origin',local_point=[0.,0.,0.],expected_global=list(m['placement']['translation']))]
    rows=input_rows();rows[0].update(hole_type='SLOT',slot_total_length_mm=30,slot_major_axis='LEG_DIRECTION')
    rows[1].update(hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='PART_LENGTH')
    return summary,components,normalize_hole_rows(rows)


class Face:
    def __init__(self,part,indices,normal,area):
        self.part=part;self.ids=indices;self.normal=normal;self.area=area
        self.index=0 if normal[0] else 1
        points=[part.vertices[i].pointOn[0] for i in indices]
        self.pointOn=(tuple(sum(p[i] for p in points)/len(points) for i in range(3)),)
    def getNormal(self,**kw):return self.normal
    def getVertices(self):return tuple(self.ids)
    def getEdges(self):return (0,1,2,3)
    def getSize(self,**kw):return self.area
    def contains(self,q):
        points=[self.part.vertices[i].pointOn[0] for i in self.ids]
        return all(min(p[d] for p in points)-1e-8<=q[d]<=max(p[d] for p in points)+1e-8 for d in range(3))


class Faces(list):
    def findAt(self,*,coordinates,printWarning=False):
        matches=[f for f in self if f.contains(coordinates)]
        if not matches:raise ValueError('Face not found')
        return min(matches,key=lambda f:f.area)


class ShellPart(Part):
    def __init__(self,component):
        self.name=component['part_name'];self.features=Features();self.datums={};self.cells=[]
        self.nodes=[1,2];self.elements=[1];self.delete_mesh_calls=0;self.cut_calls=[]
        self.vertices=[];self.faces=Faces();self.partition_calls=[];self.removal_calls=[]
        p=component['section_params_m'];h,b,lip=p['h_m'],p['b_m'],p['lip_m'];length=component['length_m']
        profile=[(b,lip),(b,0),(0,0),(0,h),(b,h),(b,h-lip)]
        for z in (0.,length):
            for x,y in profile:self.vertices.append(NS(pointOn=((x,y,z),)))
        normals=[(1,0,0),(0,-1,0),(-1,0,0),(0,1,0),(1,0,0)]
        for i in range(5):
            size=math.dist(profile[i],profile[i+1])*length
            self.faces.append(Face(self,[i,i+1,i+7,i+6],normals[i],size))
    def PartitionFaceBySketch(self,*,faces,sketch,sketchUpEdge,sketchOrientation):
        self.partition_calls.append(faces)
        outer=faces[0];matrix=sketch.kwargs['transform'];origin=matrix[9:12]
        points=[]
        for kind,c in sketch.calls:
            for key in ('point1','point2'):
                if key in c:
                    uv=c[key];points.append(tuple(origin[i]+matrix[i]*uv[0]+matrix[i+3]*uv[1] for i in range(3)))
        ids=[]
        for p in points:
            ids.append(len(self.vertices));self.vertices.append(NS(pointOn=(p,)))
        inside=Face(self,ids,outer.normal,sketch.area());inside.pointOn=(origin,)
        outer.area-=inside.area;self.faces.append(inside)
        return self.feature('Partition')
    def RemoveFaces(self,*,faceList):
        self.removal_calls.append(faceList)
        for f in faceList:self.faces.remove(f)
        return self.feature('Remove')
    def CutExtrude(self,**kw):raise AssertionError('Shell must never be through-all cut')


class Instance:
    dependent=True
    def __init__(self,part,pose):self.part=part;self.partName=part.name;self.pose=pose
    @property
    def vertices(self):return [NS(pointOn=(transform(self.pose,v.pointOn[0]),)) for v in self.part.vertices]
    @property
    def faces(self):
        return [NS(getVertices=f.getVertices,getNormal=lambda f=f,**kw:matvec(self.pose['rotation'],f.getNormal())) for f in self.part.faces]


class Step06ATests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'report.json'
        self.summary,self.components,self.rows=fixture_a()
        self.plan=json.loads(json.dumps(build_step06_a_plan(self.summary,self.rows,self.components)))
        self.ns={'__name__':'stage_a_test'};self.source=script_source(self.plan,self.path);exec(self.source,self.ns)
        self.support=Part('PART_PURLIN_SUPPORT',self.plan['driving_holes'][0]['source_geometry'])
        self.support.faces=Faces([Face(self.support,[0,1,2,3],(0,-1,0),.008),Face(self.support,[0,4,5,3],(-1,0,0),.005)])
        self.support.nodes=[1];self.support.elements=[1]
        self.local=ShellPart(self.components[1]);self.beam=ShellPart(self.components[2])
        self.parts={p.name:p for p in (self.support,self.local,self.beam)}
        instances={}
        for m in self.plan['instances']:
            instances[m['instance_name']]=Instance(self.parts[m['part_name']],placement_candidates(m['placement'])[-1])
        self.assembly=NS(instances=instances,features={},regenerate=lambda:None)
        self.model=NS(parts=self.parts,rootAssembly=self.assembly,sketches={})
        def sketch(**kw):
            s=Sketch(**kw);self.model.sketches[kw['name']]=s;return s
        self.model.ConstrainedSketch=sketch;self.mdb=NS(models={'TEST_STEP06':self.model})
        constants=ModuleType('abaqusConstants')
        for k,v in dict(ON=True,OFF=False,SIDE1='SIDE1',RIGHT='RIGHT',ZAXIS='Z',COUNTERCLOCKWISE='CCW').items():setattr(constants,k,v)
        self.enterContext(patch.dict('sys.modules',{'abaqusConstants':constants}))
    def run_a(self):
        with contextlib.redirect_stdout(io.StringIO()):return self.ns['execute_step06_a'](self.plan,self.mdb,str(self.path),'test')
    def unchanged(self):
        for p in self.parts.values():
            self.assertEqual(p.delete_mesh_calls,0);self.assertFalse(p.features)
    def test_all_groups_plan_and_roundtrip(self):
        self.assertEqual(len(self.plan['driving_holes']),8);self.assertEqual(len(self.plan['derived_holes']),8)
        self.assertEqual(self.plan['inherited_standard_groups'],['P02','P03','P04'])
        self.assertEqual(self.plan['benchmark_scope'],'P01-P04')
    def test_full_chain_one_shared_and_four_beam_holes(self):
        before={k:deepcopy(v.pose) for k,v in self.assembly.instances.items()}
        report=self.run_a()
        self.assertEqual(report['status'],'SUCCESS');self.assertEqual(report['created_holes'],7)
        self.assertEqual(len(self.support.cut_calls),2)
        self.assertEqual(len(self.local.removal_calls),1);self.assertEqual(len(self.beam.removal_calls),4)
        self.assertEqual(len(report['purlin_local']),4);self.assertEqual(len(report['inclined_beam']),4)
        self.assertEqual({r['created_feature'] for r in report['purlin_local']},{'STEP06_HOLE_PURLIN_FROM_SUPPORT'})
        self.assertEqual(report['inclined_beam'][3]['created_feature'],'STEP06_HOLE_BEAM_P04_FROM_SUPPORT')
        for r in report['purlin_local']:
            self.assertTrue(r['hole_pattern_identical'])
            self.assertAlmostEqual(r['local_center'][1],.05)
            self.assertAlmostEqual(r['local_center'][0],0.)
        for r in report['inclined_beam']:
            self.assertAlmostEqual(r['local_center'][0],.025);self.assertAlmostEqual(r['local_center'][1],.1)
            self.assertAlmostEqual(r['local_major_axis'][2],1.)
        for p in self.parts.values():self.assertEqual(p.delete_mesh_calls,1)
        self.assertEqual(before,{k:v.pose for k,v in self.assembly.instances.items()})
        self.assertEqual(self.model.sketches,{})
    def test_preflight_last_group_outside_keeps_every_mesh(self):
        name='PURLIN_LOCAL_04'
        self.assembly.instances[name].pose['translation']=(.4,0.,1.4)
        for m in self.plan['instances']:
            if m['instance_name']==name:
                m['placement']['translation']=[.4,0.,1.4];m['transform_anchors'][0]['expected_global']=[.4,0.,1.4]
        with self.assertRaises(ValueError):self.run_a()
        self.unchanged()
    def test_different_shared_local_pattern_requires_isolation(self):
        name='PURLIN_LOCAL_04'
        self.assembly.instances[name].pose['translation']=(.105,0.,1.4)
        for m in self.plan['instances']:
            if m['instance_name']==name:
                m['placement']['translation']=[.105,0.,1.4];m['transform_anchors'][0]['expected_global']=[.105,0.,1.4]
        with self.assertRaisesRegex(ValueError,'PART_ISOLATION_REQUIRED'):self.run_a()
        self.unchanged()
    def test_summary_anchor_mismatch_stops_before_mutation(self):
        self.plan['instances'][-1]['placement']['translation'][0]+=.01
        with self.assertRaisesRegex(ValueError,'SUMMARY_TRANSFORM_INCONSISTENT'):self.run_a()
        self.unchanged()
    def test_combined_world_rotation_preserves_local_results(self):
        extra=dict(axis_point=[.4,-.2,.3],axis_direction=[1.,2.,3.],angle_deg=37.)
        for m in self.plan['instances']:
            m['transform_anchors'][0]['expected_global']=list(rotate_point(m['transform_anchors'][0]['expected_global'],extra))
            m['placement']['rotation_steps'].append(extra)
            self.assembly.instances[m['instance_name']].pose=placement_candidates(m['placement'])[-2]
        result=self.run_a()
        for r in result['purlin_local']:
            self.assertAlmostEqual(r['local_center'][1],.05)
            self.assertNotAlmostEqual(r['global_major_axis'][0],1.)
        for r in result['inclined_beam']:self.assertAlmostEqual(r['local_center'][0],.025)

    def test_slot_edge_overrun_stops_before_mutation(self):
        # Source pattern still fits support; target WEB is too narrow for the inherited slot.
        name='PURLIN_LOCAL_04'
        self.assembly.instances[name].pose['translation']=(.065,0.,1.4)
        for m in self.plan['instances']:
            if m['instance_name']==name:
                m['placement']['translation']=[.065,0.,1.4];m['transform_anchors'][0]['expected_global']=[.065,0.,1.4]
        with self.assertRaisesRegex(ValueError,'Slot exceeds'):self.run_a()
        self.unchanged()

    def test_unlisted_shared_target_reference_stops_before_mutation(self):
        self.assembly.instances['EXTRA']=self.assembly.instances['PURLIN_LOCAL_04']
        with self.assertRaisesRegex(ValueError,'PART_REFERENCE_REVIEW_REQUIRED'):self.run_a()
        self.unchanged()

    def test_wrong_shell_partition_area_never_removes_face(self):
        original=self.local.PartitionFaceBySketch
        def wrong(**kw):
            feature=original(**kw);self.local.faces[-1].area*=2.;return feature
        with patch.object(self.local,'PartitionFaceBySketch',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'slot interior'):self.run_a()
        self.assertEqual(self.local.removal_calls,[]);self.assertEqual(self.beam.removal_calls,[])

    def test_reused_support_evidence_survives_target_preflight_failure(self):
        sub=dict(self.plan,schema_version='step06-hole-setup-v0.1',benchmark_scope='P01')
        with contextlib.redirect_stdout(io.StringIO()):self.ns['execute_hole_setup'](sub,self.mdb,str(self.path),'old')
        with patch.dict(self.assembly.instances,EXTRA=self.assembly.instances['PURLIN_LOCAL_04']):
            with self.assertRaisesRegex(ValueError,'PART_REFERENCE_REVIEW_REQUIRED'):self.run_a()
        self.assertEqual(json.loads(self.path.read_text())['support_validation']['status'],'SUCCESS')
        self.assertEqual(self.run_a()['status'],'SUCCESS')
    def test_missing_top_flange_never_selects_lower(self):
        self.beam.faces[:]=[f for f in self.beam.faces if f.normal!=(0,1,0)]
        with self.assertRaises(ValueError):self.run_a()
        self.unchanged()
    def test_existing_verified_support_is_reused(self):
        sub=dict(self.plan,schema_version='step06-hole-setup-v0.1',benchmark_scope='P01')
        with contextlib.redirect_stdout(io.StringIO()):self.ns['execute_hole_setup'](sub,self.mdb,str(self.path),'old')
        report=self.run_a()
        self.assertEqual(report['support']['status'],'REUSED_VERIFIED');self.assertEqual(len(self.support.cut_calls),2)
        self.assertEqual(report['created_holes'],5)
    def test_existing_support_without_proof_is_rejected(self):
        self.support.feature('STEP06_HOLE_')
        with self.assertRaisesRegex(ValueError,'successful Step06 report'):self.run_a()
        self.assertEqual(self.local.delete_mesh_calls,0)
    def test_shell_removal_failure_reports_partial_state(self):
        with patch.object(self.local,'RemoveFaces',side_effect=RuntimeError('kernel error')):
            with self.assertRaisesRegex(RuntimeError,'kernel error'):self.run_a()
        report=json.loads(self.path.read_text());self.assertTrue(report['model_modified']);self.assertEqual(report['status'],'FAILED')
        self.assertEqual(len(self.beam.removal_calls),0)
    def test_live_instance_topology_is_never_used_for_pose(self):
        class NoTopology(Instance):
            @property
            def vertices(self):raise AssertionError('live vertex order must not be read')
            @property
            def faces(self):raise AssertionError('live face order must not be read')
        for name,instance in list(self.assembly.instances.items()):
            self.assembly.instances[name]=NoTopology(instance.part,instance.pose)
        self.assertEqual(self.run_a()['status'],'SUCCESS')
        self.assertNotIn('fit_pose',self.source)
        self.assertNotIn('verify_pose_contract',self.source)

    def test_python2_and_lint(self):
        from lib2to3.refactor import RefactoringTool
        RefactoringTool([]).refactor_string(self.source+'\n','step06_a')
        assert_runtime_compatible(self.source)
