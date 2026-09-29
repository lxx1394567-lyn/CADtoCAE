import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class MinimalPartitionTests(unittest.TestCase):
    def test_generation_contract(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('minimal_generator', root/'scripts/step05_generate_partition_validation.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        project = 'SP_SC_ANG28_1042110101170S-T0204'
        plan = {'project': {'project_id': project, 'model_name': project}, 'real_case': {
            'beam_part': 'P_SP_SC_ANG28_INCLINED_BEAM', 'C_beam_local_station_m': .336,
            'patch_range_m': [.256, .416]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'plan.json'
            path.write_text(json.dumps(plan))
            before = path.read_bytes()
            output = generator.generate(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(output.name, project+'_step05_partition_validation.py')
            source = output.read_text(encoding='utf-8')
            tree = ast.parse(source)
            values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign)}
            self.assertEqual(values['MODEL'], project)
            self.assertEqual(values['BEAM'], plan['real_case']['beam_part'])
            self.assertEqual((values['C'], values['MINUS'], values['PLUS']), (.336, .256, .416))
            calls = {node.func.attr for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
            self.assertTrue({'DatumPlaneByPrincipalPlane', 'PartitionFaceByDatumPlane'} <= calls)
            self.assertFalse(calls & {'Tie', 'Coupling', 'Hole', 'ReferencePoint', 'RemoveFaces', 'CutExtrude', 'generateMesh'})
            self.assertNotIn('_s5_pose', source)
            self.assertNotIn('analysis_runtime', source)
            self.assertNotIn('.instances', source)
            self.assertIn('STEP05_BEAM_C_MINUS_80', source)
            self.assertIn('STEP05_BEAM_C_PLUS_80', source)
            plan['real_case']['C_beam_local_station_m'] = .302
            path.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                generator.generate(path)
