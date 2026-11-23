import ast
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from cadtocae.analysis_setup import generate_analysis_setup
from test_analysis_plan import benchmark_inputs
from analysis_fake_cae import fake_model_and_summary, DynamicStation, Part, Repository


class AnalysisRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.mdb, self.summary=fake_model_and_summary()
        (self.root/'summary.json').write_text(json.dumps(self.summary))
        (self.root/'input.json').write_text(json.dumps(benchmark_inputs()))
        self.paths=generate_analysis_setup(self.root/'summary.json',self.root/'input.json',self.root)
        self.source=self.paths['script'].read_text(encoding='utf-8')
        self.runtime={'__name__':'test_runtime'}
        exec(compile(self.source,'generated.py','exec'),self.runtime)

    def run_script(self):
        return self.runtime['execute_analysis'](self.runtime['PLAN'],self.mdb,str(self.paths['runtime_report']),self.runtime['PLAN_FINGERPRINT'])

    def test_repository_access_and_reuse_without_membership(self):
        class StrictRepository(Repository):
            def changeKey(self, fromName, toName):
                # Simulate the native repository method, not caller lookup.
                if dict.__contains__(self, toName):
                    raise ValueError('Duplicate feature')
                value = dict.pop(self, fromName)
                value.name = toName
                dict.__setitem__(self, toName, value)

            def __contains__(self, key):
                raise AssertionError('Repository membership is forbidden')

            def __getitem__(self, key):
                if not any(key is actual for actual in self.keys()):
                    raise AssertionError('Expected original Repository key')
                return super().__getitem__(key)

        model = self.mdb.models['SYNTHETIC_A2']
        for part in model.parts.values():
            for name in ('sets', 'surfaces', 'features'):
                setattr(part, name, StrictRepository(getattr(part, name)))
        model.parts = StrictRepository(model.parts)
        model.sections = StrictRepository(model.sections)
        model.rootAssembly.instances = StrictRepository(model.rootAssembly.instances)
        self.mdb.models = StrictRepository(self.mdb.models)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            first = self.run_script()
            repeated = self.run_script()
        self.assertEqual(first['status'], 'SUCCESS')
        self.assertEqual(repeated['status'], 'SUCCESS')
        self.assertIn('STEP05 repository preflight passed', output.getvalue())
        self.assertIn('Resolved Parts:', output.getvalue())
        self.assertIn('Resolved Instances:', output.getvalue())

    def test_generated_script_has_no_forbidden_calls(self):
        calls={node.func.attr for node in ast.walk(ast.parse(self.source))
               if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        self.assertFalse(calls & {'Tie','Coupling','ReferencePoint','CutExtrude','RemoveFaces','RemoveFace',
                                 'generateMesh','ConnectorSection','WirePolyLine','Instance','deleteCells'})
        self.assertIn('PartitionFaceByDatumPlane',calls)
        self.assertFalse(self.paths['runtime_report'].exists())

    def test_success_area_mesh_station_and_reuse(self):
        result=self.run_script()
        self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual(result['partition_locations'],[.92,1.08])
        self.assertIn('SET_BEAM_SEC_C',result['existing_objects_reused'])
        self.assertEqual(result['beam_region']['geometric_region_type'],'FACE')
        self.assertEqual(result['brace_region']['geometric_region_type'],'EDGE')
        self.assertFalse(result['material_removed'])
        self.assertFalse(result['tie_created'])
        self.assertTrue(result['mesh_removed'])
        for key,value in result['shell_area_before'].items():
            self.assertAlmostEqual(result['shell_area_after'][key],value)
        model=self.mdb.models['SYNTHETIC_A2']
        counts={name:len(part.features) for name,part in model.parts.items()}
        repeated=self.run_script()
        self.assertEqual(repeated['status'],'SUCCESS')
        self.assertFalse(repeated['mesh_removed'])
        self.assertTrue(repeated['remesh_required'])
        self.assertEqual(counts,{name:len(part.features) for name,part in model.parts.items()})

    def test_wrong_c_fails_before_mutation_and_reports(self):
        part=self.mdb.models['SYNTHETIC_A2'].parts['P_INCLINED_BEAM']
        part.sets['SET_BEAM_SEC_C']=DynamicStation(part,.5)
        with self.assertRaisesRegex(ValueError,'SET_BEAM_SEC_C'):
            self.run_script()
        self.assertEqual(part.mutations,[])
        report=json.loads(self.paths['runtime_report'].read_text())
        self.assertEqual(report['status'],'FAILED')
        self.assertIn('traceback',report)

    def test_unsupported_pose_fails_before_mesh_change(self):
        model=self.mdb.models['SYNTHETIC_A2']
        model.rootAssembly.instances['BRACE_FRONT_01'].translation=(8,8,8)
        with self.assertRaisesRegex(ValueError,'unsupported transform'):
            self.run_script()
        self.assertTrue(all(not p.mutations for p in model.parts.values()))

    def test_physical_side_failure_is_preflight(self):
        model=self.mdb.models['SYNTHETIC_A2']
        model.parts['P_INCLINED_BEAM'].sectionAssignments[0].offsetType='OFFSET_FIELD'
        with self.assertRaisesRegex(ValueError,'offset'):
            self.run_script()
        self.assertTrue(all(not p.mutations for p in model.parts.values()))

    def test_no_intersection_fails_before_mutation(self):
        model=self.mdb.models['SYNTHETIC_A2']
        instance=model.rootAssembly.instances['BRACE_FRONT_01']
        instance.translation=(instance.translation[0],instance.translation[1],instance.translation[2]-2.)
        self.runtime['PLAN']['instances'][1]['placement']['translation']=instance.translation
        with self.assertRaisesRegex(ValueError,'does not intersect'):
            self.run_script()
        self.assertTrue(all(not p.mutations for p in model.parts.values()))

    def test_changed_plan_conflict(self):
        self.run_script()
        self.runtime['PLAN_FINGERPRINT']='different'
        with self.assertRaisesRegex(ValueError,'conflict policy FAIL'):
            self.run_script()

    def test_unrelated_mesh_is_untouched(self):
        model=self.mdb.models['SYNTHETIC_A2']
        other=Part('UNRELATED',.1,.2,.025,2.)
        model.parts[other.name]=other
        self.run_script()
        self.assertEqual(other.mutations,[])
        self.assertEqual(len(other.elements),1)

    def test_out_of_patch_intersection_is_preflight_error(self):
        model=self.mdb.models['SYNTHETIC_A2']
        instance=model.rootAssembly.instances['BRACE_FRONT_01']
        instance.translation=(instance.translation[0]+.2,instance.translation[1],instance.translation[2])
        self.runtime['PLAN']['instances'][1]['placement']['translation']=instance.translation
        with self.assertRaisesRegex(ValueError,'outside finite beam patch'):
            self.run_script()
        self.assertTrue(all(not p.mutations for p in model.parts.values()))

    def test_bad_existing_surface_side_fails_without_duplicates(self):
        self.run_script()
        part=self.mdb.models['SYNTHETIC_A2'].parts['P_INCLINED_BEAM']
        part.surfaces['STEP05_SURF_BEAM_BRACE_FRONT'].sides=('WRONG',)
        before=len(part.features)
        with self.assertRaisesRegex(ValueError,'surface side'):
            self.run_script()
        self.assertEqual(before,len(part.features))
