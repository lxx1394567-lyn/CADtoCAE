import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_abaqus_script():
    spec = importlib.util.spec_from_file_location("abaqus_build_parts", ROOT / "scripts" / "abaqus_build_parts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AbaqusGeometryTest(unittest.TestCase):
    def test_c_channel_profile_is_open_lipped_centerline(self):
        module = _load_abaqus_script()
        component = {
            "section_kind": "C_CHANNEL",
            "section_params_m": {"h_m": 0.075, "b_m": 0.04, "lip_m": 0.015, "t_m": 0.002},
        }
        self.assertEqual(
            module._profile_points(component),
            [(0.04, 0.015), (0.04, 0.0), (0.0, 0.0), (0.0, 0.075), (0.04, 0.075), (0.04, 0.06)],
        )

    def test_simple_c_and_clamp_v1_profiles_use_drawing_dimensions(self):
        module = _load_abaqus_script()
        simple = module._simple_c_profile_points({"h_m": 0.106, "b_m": 0.052, "t_m": 0.003})
        self.assertEqual(simple[0], (0.0, 0.0))
        self.assertEqual(simple[2], (0.052, 0.003))
        self.assertEqual(simple[4], (0.003, 0.103))
        self.assertNotIn("lip_m", {"h_m": 0.106, "b_m": 0.052, "t_m": 0.003})

        mid = module._clamp_profile_points("MID_CLAMP_PROFILE")
        edge = module._clamp_profile_points("EDGE_CLAMP_PROFILE")
        self.assertAlmostEqual(max(point[1] for point in mid), 0.023)
        self.assertAlmostEqual(min(point[0] for point in mid), -0.022)
        self.assertAlmostEqual(max(point[0] for point in mid), 0.022)
        self.assertIn((-0.010, 0.0), mid)
        self.assertIn((0.010, 0.0), mid)
        self.assertIn((-0.007, 0.004), mid)
        self.assertIn((0.007, 0.004), mid)
        self.assertNotIn((-0.011, 0.017), mid)
        self.assertAlmostEqual(-0.007 - -0.022, 0.015)
        self.assertAlmostEqual(0.022 - 0.007, 0.015)
        self.assertTrue(any(x < -0.010 for x, _ in mid), "MID_CLAMP needs a left outward flange")
        self.assertTrue(any(x > 0.010 for x, _ in mid), "MID_CLAMP needs a right outward flange")
        module._validate_mid_clamp_profile(mid)
        self.assertAlmostEqual(max(point[1] for point in edge), 0.034)
        self.assertAlmostEqual(max(point[0] for point in edge), 0.046)
        self.assertNotEqual(mid, edge)
        self.assertFalse(module._clamp_requires_slots("MID_CLAMP_PROFILE"))
        self.assertTrue(module._clamp_requires_slots("EDGE_CLAMP_PROFILE"))

    def test_mid_clamp_profile_rejects_previous_self_intersection(self):
        module = _load_abaqus_script()
        previous = [(-0.015, 0.023), (0.0, 0.023), (0.0, 0.0), (0.020, 0.0),
                    (0.020, 0.004), (-0.003, 0.004), (-0.003, 0.019), (-0.015, 0.019)]
        with self.assertRaisesRegex(ValueError, "MID_CLAMP profile is not a valid closed region"):
            module._validate_mid_clamp_profile(previous)

    def test_mid_clamp_validation_does_not_call_abaqus_sum_with_generator(self):
        module = _load_abaqus_script()
        module.sum = lambda value: self.fail("Abaqus sum must not receive the profile generator")
        module._validate_mid_clamp_profile(module._mid_clamp_profile_points())

    def test_clamp_sketch_plane_uses_planar_face_and_z_direction_edge(self):
        module = _load_abaqus_script()

        class Vertex:
            def __init__(self, point):
                self.pointOn = (point,)

        class Edge:
            def getVertices(self):
                return (index for index in (0, 1))

        class Face:
            pointOn = ((0.008, 0.034, 0.045),)

            def getNormal(self, point):
                return (0.0, 1.0, 0.0)

            def getEdges(self):
                return (index for index in (0,))

        class Part:
            faces = (Face(),)
            edges = (Edge(),)
            vertices = (Vertex((0.0, 0.034, 0.0)), Vertex((0.0, 0.034, 0.09)))

        face, edge = module._find_clamp_sketch_plane(Part(), 0.034)
        self.assertIs(face, Part.faces[0])
        self.assertIs(edge, Part.edges[0])

    def test_clamp_slots_have_two_centers_at_15_and_75_mm(self):
        module = _load_abaqus_script()
        component = {"section_params_m": {"hole_1_center_m": 0.015, "hole_2_center_m": 0.075}}
        self.assertEqual(module._slot_centers(component), (0.015, 0.075))

    def test_angle_inner_root_uses_fillet_radius_equal_to_thickness(self):
        module = _load_abaqus_script()

        class Sketch:
            def __init__(self):
                self.lines = []
                self.fillets = []

            def Line(self, point1, point2):
                line = (point1, point2)
                self.lines.append(line)
                return line

            def FilletByRadius(self, **kwargs):
                self.fillets.append(kwargs)

        sketch = Sketch()
        module._draw_angle_profile(
            sketch,
            {"leg_a_m": 0.1, "leg_b_m": 0.063, "t_m": 0.006, "inner_root_radius_m": 0.006},
        )
        self.assertEqual(len(sketch.fillets), 1)
        self.assertAlmostEqual(sketch.fillets[0]["radius"], 0.006)

    def test_hoop_band_dimensions_use_inner_diameter_and_asymmetric_extensions(self):
        module = _load_abaqus_script()
        component = {
            "section_kind": "HOOP_BAND",
            "section_params_m": {
                "diameter_m": 0.06,
                "width_m": 0.04,
                "t_m": 0.003,
                "left_extension_m": 0.057,
                "right_extension_m": 0.117,
            },
        }

        dims = module._hoop_band_dimensions(component)

        self.assertAlmostEqual(dims["inner_radius_m"], 0.03)
        self.assertAlmostEqual(dims["outer_radius_m"], 0.033)
        self.assertAlmostEqual(dims["width_m"], 0.04)
        self.assertAlmostEqual(dims["thickness_m"], 0.003)
        self.assertAlmostEqual(dims["left_extension_m"], 0.057)
        self.assertAlmostEqual(dims["right_extension_m"], 0.117)



if __name__ == "__main__":
    unittest.main()
