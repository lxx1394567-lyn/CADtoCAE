import unittest
from cadtocae.hoop_brace_plan import build_hoop_brace_plan

class HoopBracePlanTests(unittest.TestCase):
    def fixture(self):
        def member(name,part,translation,steps=None):
            return dict(instance_name=name,part_name=part,placement=dict(translation=translation,rotation_steps=steps or []))
        summary=dict(project_id='SP_SC_ANG18_TEST',instances=[
            member('BRACE_FRONT_01','front',[-.1,0,1.1]),member('BRACE_REAR_01','rear',[.1,0,1.1]),
            member('HOOP_01_A','hoop',[0,0,1.06]),member('HOOP_01_B','hoop',[0,0,1.06],[dict(axis_point=[0,0,0],axis_direction=[0,0,1],angle_deg=180)])])
        holes=[dict(part_name='hoop',hole_id=label,hole_type='ROUND',diameter_m=.016,local_center_m=[x,.0025,.02],local_axis=[0,1,0]) for label,x in [('HOOP_LEFT',-.135),('HOOP_RIGHT',.135)]]
        return summary,dict(hoop_hole_plan=dict(part_geometry={'hoop':{'thickness_m':.005}},driving_holes=holes))
    def test_benchmark_uses_explicit_a_a_without_distance_inference(self):
        s,p=self.fixture()
        plan=build_hoop_brace_plan(s,p)
        self.assertEqual([c['hoop_instance'] for c in plan['connections']],['HOOP_01_A','HOOP_01_A'])
    def test_explicit_choice_and_five_mm_y_offset(self):
        s,p=self.fixture();plan=build_hoop_brace_plan(s,p,{'FRONT':'A','REAR':'A'})
        for c in plan['connections']:
            self.assertAlmostEqual(c['rp_distance'],.005)
            self.assertEqual(c['hoop_rp_global'][0],c['brace_rp_global'][0])
            self.assertEqual(c['hoop_rp_global'][2],c['brace_rp_global'][2])
            self.assertEqual(c['brace_station_m'],[0,.05])
        self.assertEqual(plan['connections'][0]['hoop_hole_id'],'HOOP_LEFT')
        self.assertEqual(plan['connections'][1]['hoop_hole_id'],'HOOP_RIGHT')
        self.assertLess(plan['connections'][0]['delta_xyz'][1],0)
        self.assertLess(plan['connections'][1]['delta_xyz'][1],0)
    def test_non_y_bolt_axis_rejected(self):
        s,p=self.fixture();p['hoop_hole_plan']['driving_holes'][0]['local_axis']=[1,0,0]
        with self.assertRaisesRegex(ValueError,'HOOP_BOLT_AXIS_NOT_GLOBAL_Y'):build_hoop_brace_plan(s,p)
    def test_wrong_benchmark_thickness_rejected(self):
        s,p=self.fixture();p['hoop_hole_plan']['part_geometry']['hoop']['thickness_m']=.006
        with self.assertRaisesRegex(ValueError,'5 mm'):build_hoop_brace_plan(s,p)
