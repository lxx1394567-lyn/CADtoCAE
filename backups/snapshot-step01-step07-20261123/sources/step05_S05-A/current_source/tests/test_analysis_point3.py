import contextlib
import io
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from cadtocae.beam_brace_tie_runtime import point3, vector3, is_numeric_triple
from cadtocae.runtime_compatibility import assert_runtime_compatible


class PointTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'src/cadtocae/column_hoop_tie_runtime.py'
        self.runtime=dict(point3=point3,math=math)
        exec(path.read_text(encoding='utf-8'),self.runtime)

    def test_flat_point_and_float_result(self):
        self.assertEqual(point3((1,2,3)),(1.,2.,3.))
        for value in point3([1,2,3]): self.assertIs(type(value),float)

    def test_singleton_wrappers(self):
        for value in (((1,2,3),), [[1,2,3]], ((((1,2,3),),),)):
            self.assertEqual(point3(value),(1.,2.,3.))

    def test_point_on_objects(self):
        for value in ((1,2,3),((1,2,3),),((1,2,3),(0,0,1))):
            self.assertEqual(point3(NS(pointOn=value)),(1.,2.,3.))

    def test_custom_indexable_sequence(self):
        class Sequence:
            def __len__(self): return 3
            def __getitem__(self,index): return [1,2,3][index]
        self.assertEqual(point3(NS(pointOn=Sequence())),(1.,2.,3.))

    def test_shell_pointon_normal_payload(self):
        self.assertEqual(point3(NS(pointOn=((1,2,3,0,1,0),))),(1.,2.,3.))
        with self.assertRaises(ValueError): point3((1,2,3,0,1,0))

    def test_normal_sequence_normalized_before_projection(self):
        from cadtocae.beam_brace_tie_runtime import normal
        self.assertEqual(normal(NS(getNormal=lambda:((0,2,0),))),(0.,1.,0.))

    def test_invalid_and_ambiguous_points_fail(self):
        for value in ((),(1,2),(1,2,3,4),((1,2),(4,5,6)),(1,[],3),None,
                      (float('nan'),0,0),(0,float('inf'),0)):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'Invalid Abaqus'):
                point3(value)

    def test_coordinate_direction_pair_and_exact_real_sample(self):
        self.assertEqual(point3(((1,2,3),(0,0,1))),(1.,2.,3.))
        raw=((0.081059,0.010609,1.233333),(0.991543,0.129775,0.0))
        self.assertEqual(point3(raw),raw[0])
        self.assertEqual(point3(NS(pointOn=raw)),raw[0])

    def test_array_like_first_triple(self):
        class Array:
            def __len__(self): return 2
            def __getitem__(self,index): return [(1,2,3),(0,0,1)][index]
        self.assertEqual(point3(Array()),(1.,2.,3.))

    def test_does_not_search_later_entries_for_valid_point(self):
        for raw in (((float('nan'),2,3),(0,0,1)),((1,float('inf'),3),(0,0,1)),
                    ('bad',(1,2,3)),((1,2),(3,4,5))):
            with self.assertRaises(ValueError): point3(raw)

    def test_numeric_triple_contract(self):
        self.assertTrue(is_numeric_triple((1,2,3)))
        for value in ('123',None,(1,2),((1,2,3),),('bad',2,3),(1,float('nan'),3),(1,2,float('inf'))):
            self.assertFalse(is_numeric_triple(value))

    def test_vector_does_not_infer_pointon_direction(self):
        self.assertEqual(vector3(((0,0,1),)),(0.,0.,1.))
        for value in (((1,2,3),(0,0,1)),NS(pointOn=((1,2,3),(0,0,1)))):
            with self.assertRaises(ValueError): vector3(value)

    def face(self,centroid,area):
        # Deliberately different sample point: centroid weighting must not change.
        return NS(index=7,pointOn=((99,99,99),),getCentroid=lambda:centroid,
                  getSize=lambda printResults:area)

    def test_area_weighted_nested_centroid_not_sample_point(self):
        faces=[self.face(((1,2,3),(0,0,1)),2),self.face((5,6,7),6)]
        result=self.runtime['cht_center'](faces)
        self.assertEqual(result,(4.,5.,6.))
        self.assertIs(type(result),tuple)
        for value in result: self.assertIs(type(value),float)

    def test_empty_and_zero_area_fail_fast(self):
        for faces in ([],[self.face((1,2,3),0)],[self.face((1,2,3),1.e-13)]):
            with self.assertRaisesRegex(ValueError,'Empty HOOP'):
                self.runtime['cht_center'](faces)

    def test_invalid_area_fails(self):
        for area in (-1,float('nan'),float('inf')):
            with self.assertRaisesRegex(ValueError,'Invalid HOOP face area'):
                self.runtime['cht_center']([self.face((1,2,3),area)])

    def test_failed_centroid_prints_raw_structure(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(ValueError):
            self.runtime['cht_center']([self.face(((1,2),),1)])
        self.assertIn('getCentroid raw repr = ((1, 2),)',output.getvalue())

    def test_normalizer_runtime_syntax_and_no_generator(self):
        import inspect
        from lib2to3.refactor import RefactoringTool
        source=inspect.getsource(point3)
        assert_runtime_compatible(source)
        RefactoringTool([]).refactor_string(source,'point3')
