import copy,math,unittest
from cadtocae.connector_b1_plan import fingerprint
from cadtocae.connector_groups import build_group_plan
from cadtocae.support_beam_connector import build_support_beam_geometry
from cadtocae.connector_geometry import connector_profile,matched_hole_geometry
from cadtocae.connector_setup import connector_script_source
from test_step06_connector_groups import four


def spsc(project='SP_SC_ANG33_TEST',purlin=(.008,.008),beam=(.008,.008)):
    holes,report=four();holes['project_id']=project;report['project_id']=project
    for s in holes['driving_holes']:s.update(width_m=purlin[0],total_length_m=purlin[1])
    for t in report['purlin_local']:t.update(width_m=purlin[0],total_length_m=purlin[1])
    holes['instances'].append(dict(instance_name='INCLINED_BEAM_01',canonical_role='INCLINED_BEAM',part_name='beam',
        component_geometry=dict(model_policy='SHELL',section_params_m={'h_m':.075}),
        placement=dict(translation=[0,0,0],rotation_steps=[dict(axis_point=[0,0,0],axis_direction=[1,0,0],angle_deg=90)])))
    report['inclined_beam']=[]
    for n in range(1,5):
        group='P%02d'%n;s=copy.deepcopy(holes['driving_holes'][n-1]);s.update(hole_id='PS_TO_BEAM',driving_hole_id='beam'+group,leg='SHORT_LEG',width_m=beam[0],total_length_m=beam[1])
        holes['driving_holes'].append(s)
        holes['derived_holes'].append(dict(source_driving_hole_id=s['driving_hole_id'],target_instance='INCLINED_BEAM_01',target_part='beam'))
        report['inclined_beam'].append(dict(connection_group=group,source_instance=s['source_instance'],target_instance='INCLINED_BEAM_01',target_part='beam',
            target_surface='INCLINED_BEAM_TOP_FLANGE',feature_name='STEP06_HOLE_BEAM_'+group+'_FROM_SUPPORT',normal_axis=1,plane_coordinate=.075,
            local_center=[n,.075,0],source_global_center=[n,0,.0025],intersection_global=[n,0,.075],global_hole_axis=[0,0,1],global_major_axis=[1,0,0],
            local_axis=[0,1,0],local_major_axis=[1,0,0],hole_type='SLOT',width_m=beam[0],total_length_m=beam[1]))
    report['plan_fingerprint']=fingerprint(holes)
    return holes,report


class GeneralSPScTests(unittest.TestCase):
    def test_three_projects_and_geometry_parameters(self):
        for project,a,b in [('SP_SC_ANG18_TEST',(.012,.040),(.012,.025)),('SP_SC_ANG28_TEST',(.010,.030),(.010,.020)),('SP_SC_ANG33_TEST',(.008,.008),(.008,.008)),('METADATA_PROJECT',(.009,.009),(.009,.009))]:
            with self.subTest(project=project):
                h,r=spsc(project,a,b)
                for fn,dims in ((build_group_plan,a),(build_support_beam_geometry,b)):
                    plan=fn(h,r);self.assertEqual(len(plan['connections']),4)
                    self.assertEqual([(c['width_m'],c['total_length_m']) for c in plan['connections']],[dims]*4)
    def test_type_metadata_required_no_project_name_fallback(self):
        h,r=spsc();h.pop('structure_type');r['plan_fingerprint']=fingerprint(h)
        for fn in (build_group_plan,build_support_beam_geometry):
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_STRUCTURE_TYPE'):fn(h,r)
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_STRUCTURE_TYPE'):fn(h,r,'UNKNOWN')
            self.assertEqual(len(fn(h,r,'SP_SC')['connections']),4)
    def test_target_size_axis_and_coaxial_mismatch(self):
        for key,value,error in [('width_m',.007,'HOLE_GEOMETRY_MISMATCH'),('global_hole_axis',[1,0,0],'HOLE_GEOMETRY_MISMATCH'),('intersection_global',[1.01,0,.075],'Step06-A data mismatch')]:
            h,r=spsc();r['inclined_beam'][0][key]=value
            with self.assertRaisesRegex(ValueError,error):build_support_beam_geometry(h,r)
    def test_round_probes_twelve_unique_points(self):
        h,r=spsc();ns={'__name__':'test'};exec(connector_script_source(build_group_plan(h,r),'unused'),ns)
        probes=ns['b1_probes']((0,0,0),(1,0,0),(0,0,1),.008,.008)
        self.assertEqual(len(probes),12);self.assertEqual(len(set(p[0] for p in probes)),12)
        for p,n in probes:self.assertAlmostEqual(math.sqrt(sum(x*x for x in p)),.004)
    def test_invalid_profiles_rejected_and_equivalent_round_allowed(self):
        for width,length in ((0,.008),(.008,.007),(float('nan'),.008),(.008,float('inf'))):
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_HOLE_PROFILE'):connector_profile(dict(width_m=width,total_length_m=length))
        self.assertTrue(matched_hole_geometry(dict(hole_type='ROUND',width_m=.008,total_length_m=.008),dict(hole_type='SLOT',width_m=.008,total_length_m=.008))[2])
    def test_mechanics_still_kinematic_and_same_preset(self):
        h,r=spsc();s=connector_script_source(build_group_plan(h,r),'unused')
        self.assertIn('couplingType=KINEMATIC',s);self.assertIn('u1=ON,u2=ON,u3=ON,ur1=OFF,ur2=OFF,ur3=OFF',s)
        self.assertIn('components=(1,2,3),table=((5.0e8,2.0e8,2.0e8),)',s)
