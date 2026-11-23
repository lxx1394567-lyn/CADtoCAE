"""Runtime contract tests with an independent fake geometry kernel; not CAE validation."""
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
from cadtocae.hole_plan import build_hole_plan
from cadtocae.hole_setup import script_source
from cadtocae.runtime_compatibility import assert_runtime_compatible
from test_step06_hole_inputs import input_rows
from test_step06_hole_plan import fixture


class Features(dict):
    def changeKey(self,fromName,toName):
        feature=self.pop(fromName);feature.name=toName;self[toName]=feature


class Sketch:
    def __init__(self,**kwargs):self.kwargs=kwargs;self.calls=[]
    def Line(self,**kwargs):self.calls.append(('line',kwargs))
    def ArcByCenterEnds(self,**kwargs):self.calls.append(('arc',kwargs))
    def CircleByCenterPerimeter(self,**kwargs):self.calls.append(('circle',kwargs))
    def area(self):
        circles=[v for k,v in self.calls if k=='circle']
        if circles:return math.pi*math.dist(circles[0]['center'],circles[0]['point1'])**2
        lines=[v for k,v in self.calls if k=='line'];arcs=[v for k,v in self.calls if k=='arc']
        radius=math.dist(arcs[0]['center'],arcs[0]['point1'])
        return math.pi*radius**2+math.dist(lines[0]['point1'],lines[0]['point2'])*2*radius


class Part:
    def __init__(self,name,geometry):
        self.name=name;self.geometry=geometry;self.features=Features();self.datums={}
        self.cells=[1];self.nodes=[];self.elements=[];self.cut_calls=[];self.delete_mesh_calls=0
        a,b,t,length=[geometry[k] for k in ('leg_a_m','leg_b_m','t_m','length_m')]
        radius=geometry.get('inner_root_radius_m',0.)
        self.volume=(t*(a+b-t)+(1-math.pi/4)*radius**2)*length
        points=[(0,0,0),(a,0,0),(a,0,length),(0,0,length),(0,b,0),(0,b,length)]
        self.vertices=[NS(pointOn=(p,)) for p in points]
        self.faces=NS(findAt=self.face)
    def face(self,*,coordinates,printWarning=False):
        assert len(coordinates)==3 and all(isinstance(v,(int,float)) for v in coordinates)
        coordinate=coordinates;index=1 if coordinate[1]==0 else 0
        normal=(0,-1,0) if index==1 else (-1,0,0)
        ids=[i for i,v in enumerate(self.vertices) if v.pointOn[0][index]==0]
        return NS(getNormal=lambda **kw:normal,getVertices=lambda:ids,index=index)
    def deleteMesh(self):
        self.delete_mesh_calls += 1; self.nodes=[]; self.elements=[]
    def getVolume(self,**kw):return self.volume
    def feature(self,prefix):
        key=prefix+str(len(self.features)+1);f=NS(name=key,id=len(self.features)+1)
        self.features[key]=f;return f
    def DatumAxisByPrincipalAxis(self,**kw):
        f=self.feature('Axis');self.datums[f.id]=f;return f
    def MakeSketchTransform(self,**kw):
        matrix=(1,0,0,0,0,1,0,-1,0) if kw['sketchPlane'].index==1 else (0,1,0,0,0,-1,-1,0,0)
        return NS(matrix=lambda:matrix+kw['origin'])
    def CutExtrude(self,**kw):
        self.cut_calls.append(kw)
        self.volume-=kw['sketch'].area()*self.geometry['t_m']
        return self.feature('Cut')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.report=Path(self.tmp.name)/'report.json'
        summary,components=fixture();rows=input_rows()
        rows[0].update(hole_type='SLOT',slot_total_length_mm=30,slot_major_axis='LEG_DIRECTION')
        rows[1].update(hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='PART_LENGTH')
        self.plan=build_hole_plan(summary,normalize_hole_rows(rows),components).to_dict()
        self.plan=json.loads(json.dumps(self.plan))
        self.source=script_source(self.plan,self.report)
        self.runtime={'__name__':'runtime_contract_test'};exec(self.source,self.runtime)
        self.part=Part('PART_PURLIN_SUPPORT',self.plan['driving_holes'][0]['source_geometry'])
        inst=NS(partName=self.part.name,dependent=True)
        self.assembly=NS(instances={'PURLIN_SUPPORT_01':inst},features={},regenerate=lambda:None)
        self.model=NS(parts={self.part.name:self.part},rootAssembly=self.assembly,sketches={})
        self.sketches=[]
        def sketch(**kw):
            value=Sketch(**kw);self.model.sketches[kw['name']]=value;self.sketches.append(value);return value
        self.model.ConstrainedSketch=sketch
        self.mdb=NS(models={'TEST_STEP06':self.model})
        constants=ModuleType('abaqusConstants')
        for k,v in dict(ON=True,OFF=False,SIDE1='SIDE1',RIGHT='RIGHT',ZAXIS='Z',COUNTERCLOCKWISE='CCW').items():setattr(constants,k,v)
        self.enterContext(patch.dict('sys.modules',{'abaqusConstants':constants}))
    def run_runtime(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.runtime['execute_hole_setup'](self.plan,self.mdb,str(self.report),'fingerprint')

    def test_slot_closed_geometry_and_stable_names(self):
        result=self.run_runtime()
        self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual({h['name'] for h in result['created_hole_details']},{'STEP06_HOLE_PS_TO_BEAM','STEP06_HOLE_PS_TO_PURLIN'})
        for sketch in self.sketches:
            self.assertEqual([k for k,v in sketch.calls],['line','arc','line','arc'])
            path=[(v.get('point1'),v.get('point2')) for k,v in sketch.calls]
            for i in range(4):self.assertEqual(path[i][1],path[(i+1)%4][0])
        self.assertEqual(len(self.part.cut_calls),2)
        self.assertFalse(result['derived_holes_executed'])
        self.assertEqual(self.model.sketches,{})

    def test_slot_envelope_and_direction_in_part_coordinates(self):
        self.run_runtime()
        for sketch,hole in zip(self.sketches,self.plan['driving_holes']):
            u,v=sketch.kwargs['transform'][:3],sketch.kwargs['transform'][3:6]
            major=hole['local_major_axis'];centers=[]
            for kind,call in sketch.calls:
                if kind=='arc':
                    q=call['center'];point=[q[0]*u[i]+q[1]*v[i] for i in range(3)]
                    centers.append(sum(point[i]*major[i] for i in range(3)))
            actual=max(centers)-min(centers)+hole['width_m']
            self.assertAlmostEqual(actual,hole['total_length_m'])

    def test_shared_part_stops_before_any_mutation(self):
        self.assembly.instances['PURLIN_SUPPORT_02']=NS(partName=self.part.name,dependent=True)
        with self.assertRaisesRegex(ValueError,'PART_REFERENCE_REVIEW_REQUIRED'):self.run_runtime()
        self.assertEqual(self.part.features,{})
        self.assertEqual(self.sketches,[]);self.assertEqual(self.part.cut_calls,[])
        report=json.loads(self.report.read_text())
        self.assertFalse(report['model_modified']);self.assertEqual(report['status'],'FAILED')
        self.assertEqual(len(report['affected_instances']),2)

    def test_actual_instance_sharing_overrides_plan_metadata(self):
        self.assembly.allInstances=dict(self.assembly.instances)
        self.assembly.allInstances['EXTRA']=NS(partName=self.part.name,dependent=True)
        with self.assertRaisesRegex(ValueError,'PART_REFERENCE_REVIEW_REQUIRED'):self.run_runtime()
        self.assertFalse(self.part.features)

    def configure_shared(self, explicit=False, conflict=False):
        summary,components=fixture();rows=input_rows()
        rows[0].update(hole_type='SLOT',slot_total_length_mm=30,slot_major_axis='LEG_DIRECTION')
        rows[1].update(hole_type='SLOT',slot_total_length_mm=25,slot_major_axis='PART_LENGTH')
        base=deepcopy(rows)
        for n in range(2,5):
            for member in list(summary['instances'][:2]):
                copied=deepcopy(member);copied.update(instance_name=member['component_code']+'_%02d'%n,connection_group='P%02d'%n)
                copied['placement']['translation']=[n,2*n,3*n];summary['instances'].append(copied)
            if explicit:rows.extend(dict(r,connection_group='P%02d'%n) for r in base)
        if conflict:rows[2]['distance_from_end_mm']=30
        self.plan=json.loads(json.dumps(build_hole_plan(summary,normalize_hole_rows(rows),components).to_dict()))
        for n in range(1,5):self.assembly.instances['PURLIN_SUPPORT_%02d'%n]=NS(partName=self.part.name,dependent=True,translation=[n,2*n,3*n])

    def test_shared_four_instances_cut_once_and_placements_unchanged(self):
        self.configure_shared(explicit=True)
        other=Part('OTHER_PART',self.part.geometry);other.nodes=[9];other.elements=[9]
        self.model.parts[other.name]=other
        before=deepcopy({k:vars(v) for k,v in self.assembly.instances.items()})
        self.part.nodes=[1,2];self.part.elements=[1]
        result=self.run_runtime()
        self.assertEqual(result['created_holes'],2);self.assertEqual(len(self.part.cut_calls),2)
        self.assertTrue(result['shared_part']);self.assertTrue(result['hole_pattern_identical'])
        self.assertFalse(result['requires_instance_isolation'])
        self.assertEqual(result['execution_policy'],'MODIFY_SHARED_PART_ONCE')
        self.assertEqual(result['expected_affected_instances'],sorted(before))
        self.assertEqual(result['referencing_instances'],sorted(before))
        self.assertTrue(result['mesh_removed']);self.assertTrue(result['remesh_required'])
        self.assertEqual(result['mesh_nodes_before'],2);self.assertEqual(result['mesh_elements_before'],1)
        self.assertEqual(self.part.delete_mesh_calls,1)
        self.assertEqual(before,{k:vars(v) for k,v in self.assembly.instances.items()})
        self.assertEqual(other.nodes,[9]);self.assertEqual(other.elements,[9]);self.assertFalse(other.features)

    def test_shared_inherited_pattern_success_without_mesh(self):
        self.configure_shared()
        result=self.run_runtime();self.assertEqual(result['created_holes'],2)
        self.assertFalse(result['mesh_removed']);self.assertEqual(self.part.delete_mesh_calls,0)
        self.assertEqual(result['mesh_nodes_before'],0);self.assertEqual(result['mesh_elements_before'],0)

    def test_pattern_conflict_stops_before_mesh_removal(self):
        self.configure_shared(explicit=True,conflict=True);self.part.nodes=[1]
        with self.assertRaisesRegex(ValueError,'PART_ISOLATION_REQUIRED'):self.run_runtime()
        report=json.loads(self.report.read_text())
        self.assertTrue(report['requires_instance_isolation']);self.assertFalse(report['model_modified'])
        self.assertEqual(self.part.delete_mesh_calls,0);self.assertFalse(self.part.features)

    def test_geometry_error_keeps_existing_mesh(self):
        self.part.nodes=[1];self.part.volume*=2
        with self.assertRaisesRegex(ValueError,'volume'):self.run_runtime()
        self.assertEqual(self.part.nodes,[1]);self.assertEqual(self.part.delete_mesh_calls,0)

    def test_mesh_deletion_failure_never_attempts_cuts(self):
        self.part.nodes=[1]
        with patch.object(self.part,'deleteMesh',side_effect=RuntimeError('mesh removal failed')):
            with self.assertRaisesRegex(RuntimeError,'mesh removal failed'):self.run_runtime()
        report=json.loads(self.report.read_text());self.assertTrue(report['remesh_required'])
        self.assertFalse(report['mesh_removed']);self.assertEqual(self.part.cut_calls,[])

    def test_residual_mesh_blocks_cut(self):
        self.part.nodes=[1]
        with patch.object(self.part,'deleteMesh',return_value=None):
            with self.assertRaisesRegex(ValueError,'mesh remains'):self.run_runtime()
        self.assertFalse(self.part.features)

    def test_independent_reference_blocks_shared_mutation(self):
        self.configure_shared();self.assembly.instances['PURLIN_SUPPORT_04'].dependent=False
        with self.assertRaisesRegex(ValueError,'dependent'):self.run_runtime()
        self.assertFalse(self.part.features)

    def test_p02_not_executed(self):
        other=dict(self.plan['driving_holes'][0],connection_group='P02')
        self.plan['driving_holes'].append(other)
        report=self.run_runtime();self.assertEqual(report['created_holes'],2)
        self.assertEqual(report['skipped_groups'],['P02'])

    def test_round_and_equal_length_slot_degenerate_circle(self):
        for hole in self.plan['driving_holes']:
            hole['total_length_m']=hole['width_m']
        self.plan['driving_holes'][0]['hole_type']='ROUND'
        pattern = [{k:h[k] for k in self.plan['part_executions'][0]['standard_hole_pattern'][0]} for h in self.plan['driving_holes']]
        self.plan['part_executions'][0]['standard_hole_pattern'] = pattern
        for evidence in self.plan['part_executions'][0]['instance_patterns']: evidence['hole_pattern']=deepcopy(pattern)
        self.run_runtime()
        self.assertTrue(all([k for k,v in s.calls]==['circle'] for s in self.sketches))

    def test_duplicate_run_is_refused_without_more_cuts(self):
        self.run_runtime()
        with self.assertRaisesRegex(ValueError,'Existing STEP06'):self.run_runtime()
        self.assertEqual(len(self.part.cut_calls),2)

    def test_wrong_model_or_geometry_stops_before_cuts(self):
        self.part.volume*=2
        with self.assertRaisesRegex(ValueError,'volume'):self.run_runtime()
        self.assertFalse(self.part.features)

    def test_suppressed_features_fail_fast(self):
        self.assembly.features['Suppressed']=NS(isSuppressed=lambda:True)
        with self.assertRaisesRegex(ValueError,'Suppressed'):self.run_runtime()
        self.assertFalse(self.part.features)

    def test_cut_failure_report_has_partial_state_no_retry(self):
        with patch.object(self.part,'CutExtrude',side_effect=RuntimeError('kernel failure')):
            with self.assertRaisesRegex(RuntimeError,'kernel failure'):self.run_runtime()
        result=json.loads(self.report.read_text());self.assertTrue(result['model_modified'])
        self.assertEqual(result['status'],'FAILED');self.assertEqual(len(self.sketches),1)

    def test_python2_grammar_and_runtime_lint(self):
        from lib2to3.refactor import RefactoringTool
        RefactoringTool([]).refactor_string(self.source+'\n','step06')
        assert_runtime_compatible(self.source)
        for forbidden in ('load_workbook','openMdb','saveAs','execute_analysis','execute_beam_brace','model.Coupling','ReferencePoint('):
            self.assertNotIn(forbidden,self.source)
        self.assertNotIn('depth',self.source[self.source.index('feature = part.CutExtrude'):self.source.index('part.features.changeKey(fromName=abaqus_name(feature.name)')])
