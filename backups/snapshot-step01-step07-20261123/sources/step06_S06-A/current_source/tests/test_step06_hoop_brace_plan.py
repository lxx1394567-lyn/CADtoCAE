import copy,json,unittest
from pathlib import Path
from cadtocae.hoop_brace_plan import build_hoop_brace_plan
from cadtocae.hole_transforms import step04_local_point_to_global as point


def fixture(angle='18'):
    path=next((Path(__file__).parent/'fixtures').glob('SP_SC_ANG'+angle+'*_hoop.json'))
    return json.loads(path.read_text(encoding='utf-8'))


def build(f):return build_hoop_brace_plan(f['summary'],f['holes'],f['components'])


class HoopBracePlanTests(unittest.TestCase):
    def test_three_real_projects_actual_profiles_thickness_and_shared_group(self):
        for angle,thickness,kind in (('18',.005,'ROUND'),('28',.006,'SLOT'),('33',.003,'ROUND')):
            p=build(fixture(angle))
            self.assertEqual((p['front_hoop_group'],p['rear_hoop_group']),('HOOP_01','HOOP_01'))
            self.assertEqual([c['hoop_instance'] for c in p['connections']],['HOOP_01_A']*2)
            self.assertEqual(len({c['selected_hole_id'] for c in p['connections']}),2)
            for c in p['connections']:
                self.assertAlmostEqual(c['rp_distance_m'],thickness)
                self.assertEqual(c['hole_type'],kind)
                self.assertEqual(c['brace_station_m'],[0,.05])
            if angle=='33':self.assertEqual(p['connections'][1]['selected_hole_id'],'HOOP_RIGHT_02')

    def test_no_project_angle_or_hole_name_inference(self):
        f=fixture('33');old=build(f)
        f['summary']['project_id']=f['holes']['project_id']='ARBITRARY_PROJECT'
        for i,h in enumerate(f['holes']['hoop_hole_plan']['driving_holes']):h['hole_id']='ARBITRARY_'+str(i)
        new=build(f)
        for a,b in zip(old['connections'],new['connections']):
            self.assertEqual(a['hoop_rp_global'],b['hoop_rp_global'])
            self.assertEqual(a['brace_rp_global'],b['brace_rp_global'])

    def test_duplicate_nearest_hole_fails(self):
        f=fixture();h=copy.deepcopy(f['holes']['hoop_hole_plan']['driving_holes'][0]);h['hole_id']='DUPLICATE'
        f['holes']['hoop_hole_plan']['driving_holes'].append(h)
        with self.assertRaisesRegex(ValueError,'SP_SC_HOOP_BRACE_HOLE_AMBIGUOUS'):build(f)

    def test_global_rotation_does_not_require_global_y(self):
        f=fixture();old=build(f);rotation=dict(axis_point=[1,2,3],axis_direction=[1,0,0],angle_deg=37)
        for m in f['summary']['instances']:m['placement']['rotation_steps'].append(rotation)
        new=build(f)
        for a,b in zip(old['connections'],new['connections']):
            expected=point(a['hoop_rp_global'],dict(translation=[0,0,0],rotation_steps=[rotation]))
            for x,y in zip(expected,b['hoop_rp_global']):self.assertAlmostEqual(x,y)
            self.assertAlmostEqual(b['rp_distance_m'],a['rp_distance_m'])

    def test_metadata_scope_and_half_rule(self):
        f=fixture();f['summary']['structure_type']='DP'
        with self.assertRaisesRegex(ValueError,'SP_SC_HOOP_BRACE_SCOPE'):build(f)
        f=fixture()
        with self.assertRaisesRegex(ValueError,'A/A'):
            build_hoop_brace_plan(f['summary'],f['holes'],f['components'],{'FRONT':'B','REAR':'A'})
