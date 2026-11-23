import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


class ReplayTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('replay_generator', root/'scripts/step05_generate_brace_extend_face_replay_validation.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as tmp:
            output = generator.generate(tmp)
            self.assertEqual(output.name, 'SP_SC_ANG28_1042110101170S-T0204_step05_brace_extend_face_replay_validation.py')
            self.source = output.read_text(encoding='utf-8')

    def test_minimal_script_contract(self):
        calls = {n.func.attr for n in ast.walk(ast.parse(self.source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertTrue({'makeIndependent', 'deleteMesh', 'PartitionFaceByExtendFace'} <= calls)
        self.assertFalse(calls & {'Tie', 'Surface', 'DatumPlaneByThreePoints', 'PartitionFaceByDatumPlane',
                                 'RemoveFace', 'RemoveFaces', 'CutExtrude', 'Coupling'})
        for forbidden in ('viewport', '_s5_pose', 'sum(', 'point_global', 'point_local', 'getSize', 'getNormal'):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('Material removed = False', self.source)

    def execute(self, change):
        events = []
        class Faces(list):
            def getSequenceFromMask(self, mask):
                events.append(('mask', mask))
                return tuple(self[i] for i in ((1, 2, 3) if mask == ('[#e ]',) else (2,)))
        brace = NS(faces=Faces([object() for _ in range(5)]), edges=[object() for _ in range(8)])
        beam = NS(faces=[object() for _ in range(20)])
        def independent(instances):
            self.assertEqual(instances, (brace,))
            events.append('independent')
        def delete(regions):
            self.assertEqual(regions, tuple(brace.faces[1:4]))
            events.append('deleteMesh')
        def partition(extendFace, faces):
            self.assertIs(extendFace, beam.faces[18])
            self.assertEqual(faces, (brace.faces[2],))
            events.append('extendFace')
            if change:
                brace.faces.append(object())
                brace.edges.append(object())
        assembly = NS(instances={'BRACE_FRONT_01': brace, 'INCLINED_BEAM_01': beam},
                      makeIndependent=independent, deleteMesh=delete, PartitionFaceByExtendFace=partition,
                      regenerate=lambda: events.append('regenerate'))
        mdb = NS(models={'SP_SC_ANG28_1042110101170S-T0204': NS(rootAssembly=assembly)})
        with patch.dict(sys.modules, {'abaqus': NS(mdb=mdb), 'assembly': NS(), 'mesh': NS()}):
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(self.source, 'replay.py', 'exec'), {})
        return events

    def test_exact_macro_order_and_selections(self):
        self.assertEqual(self.execute(True), ['independent', ('mask', ('[#e ]',)), 'deleteMesh',
                                             ('mask', ('[#4 ]',)), 'extendFace', 'regenerate'])

    def test_no_topology_change_fails(self):
        with self.assertRaisesRegex(ValueError, 'did not modify BRACE_FRONT geometry'):
            self.execute(False)
