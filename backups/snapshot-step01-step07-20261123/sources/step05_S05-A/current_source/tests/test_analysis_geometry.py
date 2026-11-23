import unittest
from cadtocae.analysis_geometry import (patch_limits, shell_outer_plane, fit_pose, transform,
                                      inverse_point, verify_pose_contract, placement_candidates, plane_intersection)


class AnalysisGeometryTests(unittest.TestCase):
    def test_c_plus_minus_80_mm(self):
        low, high = patch_limits(1.25, .080, 3., 1.e-6)
        self.assertAlmostEqual(low, 1.17)
        self.assertAlmostEqual(high, 1.33)

    def test_patch_bounds(self):
        for center in (.02, 2.99, float("nan")):
            with self.assertRaises(ValueError):
                patch_limits(center, .08, 3., 1.e-6)

    def test_physical_side_offset_and_normal_flip(self):
        for normal, side in (((0., 1., 0.), "SIDE2"), ((0., -1., 0.), "SIDE1")):
            result = shell_outer_plane((0., 0., 0.), normal, (0., -1., 0.), .004, "MIDDLE_SURFACE", 0)
            self.assertEqual(result["physical_side"], side)
            self.assertAlmostEqual(result["point"][1], -.002)
        result = shell_outer_plane((0., 0., 0.), (0., 1., 0.), (0., 1., 0.), .004, "TOP_SURFACE", 0)
        self.assertEqual(result["point"], (0., 0., 0.))

    def test_ambiguous_physical_side_and_offset_fail(self):
        with self.assertRaises(ValueError):
            shell_outer_plane((0,0,0), (0,1,0), (1,0,0), .004, "SINGLE_VALUE", 0)
        with self.assertRaises(ValueError):
            shell_outer_plane((0,0,0), (0,1,0), (0,-1,0), .004, "OFFSET_FIELD", 0)

    def test_runtime_fit_resolves_translation_before_roll(self):
        placement = {"translation": [2., 3., 4.], "rotation_steps": [
            {"axis_point": [0.,0.,0.], "axis_direction": [0.,1.,0.], "angle_deg": 45.},
            {"axis_point": [1.,2.,3.], "axis_direction": [0.,0.,1.], "angle_deg": 90.}]}
        points = [(0.,0.,0.), (.2,0.,0.), (0.,.4,0.), (0.,0.,2.)]
        expected = placement_candidates(placement)[1]
        world = [transform(expected, p) for p in points]
        actual = fit_pose(points, world, 1.e-7)
        self.assertEqual(verify_pose_contract(actual, placement, points, 1.e-7), [1])
        for p, q in zip(points, world):
            for a, b in zip(inverse_point(actual, q), p):
                self.assertAlmostEqual(a, b)

    def test_unsupported_transform_rejected(self):
        points = [(0.,0.,0.), (1.,0.,0.), (0.,1.,0.), (0.,0.,1.)]
        pose = fit_pose(points, points, 1.e-7)
        with self.assertRaisesRegex(ValueError, "unsupported transform"):
            verify_pose_contract(pose, {"translation": [1,0,0], "rotation_steps": []}, points, 1.e-7)
        with self.assertRaises(ValueError):
            fit_pose(points, [(0,0,0),(2,0,0),(0,1,0),(0,0,1)], 1.e-7)

    def test_oblique_plane_intersection(self):
        square = [(0,0,0),(1,0,0),(1,0,1),(0,0,1)]
        segment = plane_intersection(square, (.5,0,0), (1,0,1), 1.e-6)
        self.assertEqual(set(segment), {(.5,0.,0.), (0.,0.,.5)})
        self.assertEqual(plane_intersection(square, (0,0,2), (0,0,1), 1.e-6), [])
