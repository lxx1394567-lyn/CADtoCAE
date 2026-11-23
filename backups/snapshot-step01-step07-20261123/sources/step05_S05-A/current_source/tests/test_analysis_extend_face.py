import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from cadtocae.brace_extend_face_validation import select_lower_flange, brace_targets, run
from analysis_fake_cae import Part, Repository


def beam_geometry():
    beam = Part('beam', .05, .09, .015, 1., (.256, .416))
    sets = {}
    for label, station in [('MINUS', .256), ('PLUS', .416)]:
        edges = [e for e in beam.edges if all(abs(beam.vertices[i].pointOn[0][2]-station) < 1.e-8 for i in e.getVertices())]
        sets['STEP05_BEAM_C_'+label+'_80'] = NS(edges=edges)
    # Rotate local length into world X, local height into world Z.
    for vertex in beam.vertices:
        x, y, z = vertex.pointOn[0]
        vertex.pointOn = ((z, x, y),)
    for face in beam.faces:
        face.pointOn = (tuple(sum(beam.vertices[i].pointOn[0][j] for i in face.getVertices())/4 for j in range(3)),)
    beam.sets = sets
    return beam


class ExtendFaceTests(unittest.TestCase):
    def test_lower_flange_excludes_web_upper_lips(self):
        beam = beam_geometry()
        face = select_lower_flange(beam, .05)
        points = [beam.vertices[i].pointOn[0] for i in face.getVertices()]
        self.assertTrue(all(p[2] == 0. for p in points))
        self.assertAlmostEqual(min(p[0] for p in points), .256)
        self.assertAlmostEqual(max(p[0] for p in points), .416)
        with self.assertRaises(ValueError):
            select_lower_flange(beam, .03)

    def test_missing_or_ambiguous_selector_fails(self):
        beam = beam_geometry()
        face = select_lower_flange(beam, .05)
        beam.faces.append(face)
        with self.assertRaises(ValueError):
            select_lower_flange(beam, .05)
        beam.sets.clear()
        with self.assertRaises(ValueError):
            select_lower_flange(beam, .05)

    def execute(self, change):
        beam = beam_geometry()
        brace = Part('brace', .03, .07, .015, 1.)
        brace.dependent = 'ON'
        original = brace.faces[:]
        self.assertEqual(brace_targets(brace), original)
        assembly = NS(instances={'beam': beam, 'brace': brace}, features=Repository(), regenerate=lambda: None)
        converted = []
        assembly.makeIndependent = lambda instances: converted.extend(instances)
        def partition(faces, extendFace):
            self.assertEqual(faces, original)
            self.assertIs(extendFace, select_lower_flange(beam, .05))
            if change:
                # Kernel test double only: independently clip the brace geometry.
                brace.PartitionFaceByDatumPlane(datumPlane=NS(point=(0, 0, .7), normal=(0, 0, 1)), faces=faces)
            feature = NS(name='Partition-1')
            assembly.features[feature.name] = feature
            return feature
        assembly.PartitionFaceByExtendFace = partition
        mdb = NS(models={'test': NS(rootAssembly=assembly)})
        with contextlib.redirect_stdout(io.StringIO()) as output:
            run(mdb, dict(model='test', beam_instance='beam', brace_instance='brace', beam_width=.05), 'ON')
        self.assertEqual(converted, [brace])
        return output.getvalue()

    def test_assembly_target_and_topology(self):
        self.assertIn('partition created = True', self.execute(True))

    def test_unchanged_topology_fails(self):
        with self.assertRaisesRegex(ValueError, 'Extend-face partition did not modify BRACE_FRONT geometry'):
            self.execute(False)

    def test_generated_script_contract(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('extend_generator', root/'scripts/step05_generate_brace_extend_face_validation.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        project = 'SP_SC_ANG28_1042110101170S-T0204'
        plan = {'project': {'project_id': project, 'model_name': project}, 'instances': [
            dict(component_code='INCLINED_BEAM', instance_name='INCLINED_BEAM_01', component_geometry={'section_params_m': {'b_m': .05}}),
            dict(component_code='BRACE_FRONT', instance_name='BRACE_FRONT_01')]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'plan.json'
            path.write_text(json.dumps(plan))
            before = path.read_bytes()
            source = generator.generate(path).read_text(encoding='utf-8')
            self.assertEqual(before, path.read_bytes())
        calls = {n.func.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn('PartitionFaceByExtendFace', calls)
        self.assertFalse(calls & {'DatumPlaneByThreePoints', 'PartitionFaceByDatumPlane', 'Tie', 'Surface', 'Coupling', 'CutExtrude', 'RemoveFace', 'RemoveFaces'})
        for forbidden in ('_s5_pose', 'point_local', 'point_global', 'analysis_runtime', 'thickness'):
            self.assertNotIn(forbidden, source)
        self.assertIn('Material removed = False', source)
