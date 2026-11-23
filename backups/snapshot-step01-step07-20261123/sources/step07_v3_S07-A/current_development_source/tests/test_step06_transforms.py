from copy import deepcopy
import math
import json
from pathlib import Path
import unittest

from cadtocae.hole_transforms import (
    step04_local_point_to_global as forward_point,
    step04_global_point_to_local as inverse_point,
    step04_local_vector_to_global as forward_vector,
    step04_global_vector_to_local as inverse_vector,
    step04_validate_anchors,
    step04_placement_phases,
    _step04_rotate,
)
from cadtocae.hole_plan import build_step06_a_plan, _step04_summary_anchors, _component
from test_step06_derived import fixture_a


class SummaryTransformTests(unittest.TestCase):
    def close3(self,a,b):
        self.assertLess(math.dist(a,b),1.e-9)

    def test_first_global_axis_keeps_all_following_rotations_post(self):
        steps = [dict(axis_point=center, axis_direction=[0.,0.,1.], angle_deg=90.)
                 for center in ([0.,1.e-13,0.], [1.,0.,0.], [0.,0.,0.])]
        p = dict(translation=[2.,0.,0.], rotation_steps=steps)
        translation, pre, post = step04_placement_phases(p)
        self.assertEqual(pre, steps[:1])
        self.assertEqual(post, steps[1:])
        self.close3(forward_point([0.,0.,0.],p),[-1.,1.,0.])
        self.close3(inverse_point(forward_point([.1,.2,.3],p),p),[.1,.2,.3])

    def test_real_ang18_all_families_anchors_and_roundtrips(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/step06_ang18_transform.json').read_text(encoding='utf-8'))
        self.assertEqual(len(fixture['instances']),11)
        for member in fixture['instances']:
            with self.subTest(instance=member['instance_name']):
                component = _component(member,fixture['components'])
                anchors = _step04_summary_anchors(fixture,member,component,fixture['components'])
                p = member['placement']
                checks = step04_validate_anchors(p,anchors)
                self.assertTrue(checks)
                for check in checks:
                    self.assertLessEqual(check['error_m'],1.e-6)
                    self.assertLessEqual(check['roundtrip_error_m'],1.e-6)
                unused, pre, post = step04_placement_phases(p)
                role = member['canonical_role']
                if role in ('INCLINED_BEAM','BRACE_FRONT','BRACE_REAR'):
                    self.assertEqual((len(pre),len(post)),(1,1))
                    self.assertEqual(len(anchors),4 if role=='INCLINED_BEAM' else 2)
                else:
                    self.assertFalse(post)
                for point in ([0.,0.,0.],[.021,.037,.127],[.04,-.03,component['length_m']]):
                    self.close3(inverse_point(forward_point(point,p),p),point)
                for vector in ([1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,2.,3.]):
                    self.close3(inverse_vector(forward_vector(vector,p),p),
                                [v/math.sqrt(sum(x*x for x in vector)) for v in vector])
                if role == 'INCLINED_BEAM':
                    old = anchors[0]['local_point']
                    for step in p['rotation_steps']:
                        old = _step04_rotate(old,step)
                    old = [old[i]+p['translation'][i] for i in range(3)]
                    self.assertAlmostEqual(math.dist(old,anchors[0]['expected_global']),4.163273322598014)

    def test_nonorigin_axis_point_numeric_result(self):
        p=dict(translation=[4.,5.,6.],rotation_steps=[dict(axis_point=[1.,2.,3.],axis_direction=[0.,0.,5.],angle_deg=90.)])
        self.close3(forward_point([2.,2.,3.],p),(-4.,7.,9.))
        self.close3(inverse_point([-4.,7.,9.],p),(2.,2.,3.))
        self.close3(forward_vector([2.,0.,0.],p),(0.,1.,0.))
        self.close3(inverse_vector([0.,7.,0.],p),(1.,0.,0.))

    def test_all_roles_and_p01_p04_roundtrips(self):
        summary,components,rows=fixture_a()
        plan=build_step06_a_plan(summary,rows,components)
        extra=[dict(axis_point=[.015,0.,3.1],axis_direction=[.9510565163,0.,.3090169944],angle_deg=90.),
               dict(axis_point=[2.,-3.,1.],axis_direction=[1.,2.,3.],angle_deg=-31.)]
        self.assertEqual(len(plan['instances']),9)
        for m in plan['instances']:
            placement=deepcopy(m['placement']);placement['rotation_steps'].extend(extra)
            for n in range(1,5):
                point=(.013*n,.0375,.12*n);vector=(.2*n,-.5,.7)
                normalized=tuple(x/math.sqrt(sum(v*v for v in vector)) for x in vector)
                with self.subTest(instance=m['instance_name'],group='P%02d'%n):
                    self.close3(inverse_point(forward_point(point,placement),placement),point)
                    self.close3(inverse_vector(forward_vector(vector,placement),placement),normalized)

    def test_vectors_ignore_axis_points_and_translation(self):
        p=dict(translation=[100.,-90.,70.],rotation_steps=[dict(axis_point=[1.,2.,3.],axis_direction=[1.,2.,1.],angle_deg=57.)])
        q=deepcopy(p);q['translation']=[-4.,5.,6.];q['rotation_steps'][0]['axis_point']=[-50.,70.,90.]
        for transform in (forward_vector,inverse_vector):self.close3(transform([1.,2.,3.],p),transform([1.,2.,3.],q))
        self.assertGreater(math.dist(forward_point([1.,2.,3.],p),forward_point([1.,2.,3.],q)),1.)

    def test_empty_rotation_sequence(self):
        p=dict(translation=[1.,2.,3.],rotation_steps=[])
        self.close3(forward_point([3.,2.,1.],p),(4.,4.,4.))
        self.close3(inverse_point([4.,4.,4.],p),(3.,2.,1.))
        self.close3(forward_vector([0.,0.,9.],p),(0.,0.,1.))

    def test_bad_rotation_input_rejected(self):
        for step in (dict(axis_point=[0.,0.,0.],axis_direction=[0.,0.,0.],angle_deg=90.),
                     dict(axis_point=[0.,0.,0.],axis_direction=[0.,1.,0.],angle_deg=float('nan')),
                     dict(axis_direction=[0.,1.,0.],angle_deg=90.)):
            with self.subTest(step=step),self.assertRaises((ValueError,KeyError)):
                forward_point([0.,0.,0.],dict(translation=[0.,0.,0.],rotation_steps=[step]))

    def test_missing_or_inconsistent_anchor_cannot_pass_roundtrip_alone(self):
        p=dict(translation=[1.,2.,3.],rotation_steps=[])
        with self.assertRaisesRegex(ValueError,'SUMMARY_ANCHOR_MISSING'):step04_validate_anchors(p,[])
        results=[]
        with self.assertRaisesRegex(ValueError,'SUMMARY_TRANSFORM_INCONSISTENT'):
            step04_validate_anchors(p,[dict(local_point=[0.,0.,0.],expected_global=[1.,2.,3.01])],results=results)
        self.assertAlmostEqual(results[0]['error_m'],.01)
        self.assertLess(results[0]['roundtrip_error_m'],1e-12)

    def test_legacy_ang18_beam_anchor_matches_step04_order(self):
        # Step04 applies the global-axis roll after translation.
        p=dict(translation=[-1.8956725412369635,-.0375,2.4791848583007305],rotation_steps=[
            dict(axis_point=[0.,0.,0.],axis_direction=[0.,1.,0.],angle_deg=72.),
            dict(axis_point=[.015,0.,3.1],axis_direction=[.9510565162951535,0.,.3090169943749474],angle_deg=90.)])
        anchor=dict(name='G_global',local_point=[0.,.0375,0.],expected_global=[-1.8956725412369635,0.,2.479184858300731])
        results=[]
        step04_validate_anchors(p,[anchor],results=results)
        self.assertLess(results[0]['error_m'],1.e-12)
        self.close3(inverse_point(forward_point(anchor['local_point'],p),p),anchor['local_point'])
