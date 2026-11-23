"""Geometric invariants for both Step02 entry points and unchanged Step04 pairs."""
import ast
import importlib.util
import math
from pathlib import Path
import unittest

from cadtocae.main_frame_assembly import (
    ABAQUS_SCRIPT_TEMPLATE, _create_hoop_pair, _dp_hoop_orientation,
)

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def functions_from(source):
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    scope = {'math': math, 'CLOCKWISE': 'CLOCKWISE', 'COUNTERCLOCKWISE': 'COUNTERCLOCKWISE'}
    exec(compile(tree, '<generated-script-functions>', 'exec'), scope)
    return scope


def component(left=0.057, right=0.117, rf=0.003):
    return {'component_code': 'HOOP', 'part_name': 'P_HOOP', 'section_kind': 'HOOP_BAND',
            'section_params_m': {'diameter_m': 0.06, 'width_m': 0.04, 't_m': 0.003,
                                 'left_extension_m': left, 'right_extension_m': right,
                                 'transition_fillet_m': rf}}


def sample(segment, count=24):
    a, b = segment['start'], segment['end']
    if segment['kind'] == 'LINE':
        return [a, b]
    c = segment['center']
    radius = math.dist(a, c)
    first = math.atan2(a[1]-c[1], a[0]-c[0])
    last = math.atan2(b[1]-c[1], b[0]-c[0])
    sweep = (last-first) % (2*math.pi)
    if segment['direction'] == 'CLOCKWISE':
        sweep -= 2*math.pi
    return [(c[0]+radius*math.cos(first+sweep*i/count),
             c[1]+radius*math.sin(first+sweep*i/count)) for i in range(count+1)]


def tangent(segment, endpoint):
    if segment['kind'] == 'LINE':
        dx, dy = (segment['end'][i]-segment['start'][i] for i in (0, 1))
    else:
        x, y = (segment[endpoint][i]-segment['center'][i] for i in (0, 1))
        dx, dy = (y, -x) if segment['direction'] == 'CLOCKWISE' else (-y, x)
    norm = math.hypot(dx, dy)
    return dx/norm, dy/norm


class HoopProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = load_script('abaqus_build_parts')
        cls.runner = functions_from(load_script('make_cae_runner').CAE_TEMPLATE)
        cls.assembly = functions_from(ABAQUS_SCRIPT_TEMPLATE)

    def assertPoint(self, a, b):
        self.assertLess(math.dist(a, b), 1e-11)

    def test_both_entry_points_match_and_use_only_explicit_lines_and_arcs(self):
        class Sketch:
            def __init__(self):
                self.edges = []

            def Line(self, point1, point2):
                self.edges.append((point1, point2))

            def ArcByCenterEnds(self, center, point1, point2, direction):
                self.edges.append((center, point1, point2, direction))

        for rf in (0.0, 0.001, 0.003, 0.006):
            with self.subTest(rf=rf):
                item = component(rf=rf)
                self.assertEqual(self.legacy._hoop_band_profile_geometry(item),
                                 self.runner['_hoop_band_profile_geometry'](item))
                a, b = Sketch(), Sketch()
                self.legacy._draw_hoop_band_profile(self.runner, a, item)
                self.runner['_draw_hoop_band_profile'](b, item)
                self.assertEqual(a.edges, b.edges)
                self.assertEqual(len(a.edges), 10 if rf == 0 else 12)

    def test_radius_thickness_tangency_lengths_and_no_self_intersection(self):
        for left, right in ((0.057, 0.057), (0.057, 0.117), (0.117, 0.057)):
            for rf in (0.0, 0.001, 0.003, 0.006):
                with self.subTest(left=left, right=right, rf=rf):
                    p = self.legacy._hoop_band_profile_geometry(component(left, right, rf))
                    inner, outer = p['inner'], p['outer']
                    self.assertPoint(inner[0]['start'], (-0.033-left, 0.0))
                    self.assertPoint(inner[-1]['end'], (0.033+right, 0.0))
                    for chain, radius, y, bend in ((inner, 0.03, 0.0, rf+0.003),
                                                   (outer, 0.033, 0.003, rf)):
                        for first, second in zip(chain, chain[1:]):
                            self.assertPoint(first['end'], second['start'])
                            if rf != 0 or chain is inner:
                                self.assertPoint(tangent(first, 'end'), tangent(second, 'start'))
                        self.assertEqual(chain[0]['start'][1], y)
                        self.assertEqual(chain[-1]['end'][1], y)
                        for arc in (s for s in chain if s['kind'] == 'ARC'):
                            expected = radius if arc['center'] == (0, 0) else bend
                            for point in sample(arc):
                                self.assertAlmostEqual(math.dist(point, arc['center']), expected)
                        points = [point for s in chain for point in sample(s)]
                        self.assertTrue(all(b[0] >= a[0]-1e-12 for a, b in zip(points, points[1:])))
                        self.assertTrue(all(point[1] >= -1e-12 for point in points))
                    # Pair corresponding circular normals, not same-X vertical distances.
                    if rf > 0:
                        for a, b in zip(inner, outer):
                            if a['kind'] == 'ARC':
                                self.assertPoint(a['center'], b['center'])
                                for pa, pb in zip(sample(a), sample(b)):
                                    self.assertAlmostEqual(math.dist(pa, pb), 0.003)
                    # Closed boundary must have no crossings, including between chains.
                    polygon = [pt for s in inner for pt in sample(s)[:-1]] + [inner[-1]['end']]
                    polygon += list(reversed([pt for s in outer for pt in sample(s)[:-1]] + [outer[-1]['end']]))
                    edges = list(zip(polygon, polygon[1:] + polygon[:1]))
                    def cross(a, b, c):
                        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                    for i, (a, b) in enumerate(edges):
                        for j in range(i+2, len(edges)):
                            if i == 0 and j == len(edges)-1:
                                continue
                            c, d = edges[j]
                            self.assertFalse(cross(a,b,c)*cross(a,b,d) < -1e-24 and
                                             cross(c,d,a)*cross(c,d,b) < -1e-24)

    def test_invalid_dimensions_fail_before_sketch_creation(self):
        for key, value in (('diameter_m', 0), ('width_m', -1), ('t_m', float('nan')),
                           ('left_extension_m', float('inf')), ('right_extension_m', 0),
                           ('transition_fillet_m', -0.001), ('transition_fillet_m', 10)):
            with self.subTest(key=key, value=value):
                item = component()
                item['section_params_m'][key] = value
                for dimensions in (self.legacy._hoop_band_dimensions, self.runner['_hoop_band_dimensions']):
                    with self.assertRaises(ValueError):
                        dimensions(item)

    def test_existing_step04_pairs_mate_inner_faces_and_keep_long_side(self):
        transform = self.assembly['_transform_member']
        center = [1.4, 0.0, 0.53]
        for structure, left, right in (('SP_SC', .057, .057), ('SP_DC', .057, .057),
                                       ('DP', .057, .117), ('DP', .117, .057)):
            with self.subTest(structure=structure, left=left, right=right):
                item = component(left, right)
                kwargs = {}
                if structure == 'DP':
                    orientation, axis, _ = _dp_hoop_orientation(item, [1.4,0,0], [-1.4,0,0])
                    kwargs = {'initial_orientation': orientation, 'pair_axis_direction': axis}
                pair, _ = _create_hoop_pair(item, center, 1, 'geometry regression', **kwargs)
                for x in (-.05, .05):
                    other_x = x if structure == 'DP' else -x
                    a = transform((x, 0, .02), pair[0])
                    b = transform((other_x, 0, .02), pair[1])
                    self.assertPoint(a, b)
                    outer_a = transform((x, .003, .02), pair[0])
                    outer_b = transform((other_x, .003, .02), pair[1])
                    self.assertAlmostEqual(math.dist(outer_a, outer_b), .006)
                for member in pair:
                    for angle in (30, 90, 150):
                        theta = math.radians(angle)
                        point = transform((.03*math.cos(theta), .03*math.sin(theta), .02), member)
                        self.assertAlmostEqual(math.hypot(point[0]-center[0], point[1]-center[1]), .03)
                if structure == 'DP':
                    x = .10 if right > left else -.10
                    for member in pair:
                        self.assertLess(transform((x, 0, .02), member)[0], center[0])


if __name__ == '__main__':
    unittest.main()
