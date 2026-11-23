import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from analysis_fake_cae import fake_model_and_summary
from cadtocae.analysis_geometry import dot, sub, norm


class BracePartitionTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('brace_generator', root/'scripts/step05_generate_brace_partition_validation.py')
        self.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.generator)
        self.source = (root/'src/cadtocae/brace_partition_validation_minimal.py').read_text(encoding='utf-8')

    def test_offline_plane_transform_and_generation(self):
        def member(translation):
            return {'part_name': 'BRACE_FRONT', 'placement': {'translation': translation, 'rotation_steps': [
                {'axis_point': [0., 0., 0.], 'axis_direction': [0., 1., 0.], 'angle_deg': 0.},
                {'axis_point': translation, 'axis_direction': [0., 0., 1.], 'angle_deg': 0.}]}}
        beam, brace = member([1., 2., 3.]), member([4., 5., 6.])
        beam['component_geometry'] = {'section_params_m': {'h_m': .09, 'b_m': .05, 't_m': .002}}
        # Rotate beam local Y toward global Z, while maintaining explicit known transform.
        beam['placement']['rotation_steps'][1]['axis_direction'] = [1., 0., 0.]
        beam['placement']['rotation_steps'][1]['angle_deg'] = 90.
        plan = {'project': {'project_id': 'SP_SC_ANG28_1042110101170S-T0204', 'model_name': 'TEST'},
                'instances': [beam, brace], 'real_case': {'C_beam_local_station_m': .336}}
        data = self.generator.calculate(plan)
        for actual, expected in zip(data['point_global'], [1.025, 1.664, 2.999]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(data['point_local'], [-2.975, -3.336, -3.001]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(norm(data['normal_local']), 1.)
        for point in data['datum_points']:
            self.assertAlmostEqual(dot(sub(point, data['point_local']), data['normal_local']), 0.)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'plan.json'
            path.write_text(json.dumps(plan))
            output, _ = self.generator.generate(path)
            source = output.read_text(encoding='utf-8')
        calls = {n.func.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn('PartitionFaceByDatumPlane', calls)
        self.assertIn('DatumPlaneByThreePoints', calls)
        self.assertFalse(calls & {'Tie', 'CutExtrude', 'RemoveFace', 'RemoveFaces', 'Trim', 'Surface'})
        self.assertNotIn('_s5_pose', source)
        self.assertIn('Material removed = False', source)

    def execute(self, no_intersection=False):
        mdb, _ = fake_model_and_summary()
        z = 2. if no_intersection else .7
        data = dict(model='SYNTHETIC_A2', brace='P_BRACE_FRONT', point_global=[0, 0, z], normal_global=[0, 0, 1],
                    point_local=[0, 0, z], normal_local=[0, 0, 1], datum_points=[[0, 0, z], [.1, 0, z], [0, .1, z]])
        runtime = {'__name__': 'test'}
        exec(self.source, runtime)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            runtime['run'](mdb, data)
        return output.getvalue()

    def test_actual_partition_topology_and_area(self):
        output = self.execute()
        self.assertIn('partition created = True', output)
        self.assertIn('Material removed = False', output)

    def test_unchanged_topology_fails(self):
        with self.assertRaisesRegex(ValueError, 'BRACE_FRONT partition did not intersect shell geometry'):
            self.execute(no_intersection=True)
