from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cadtocae.hole_inputs import normalize_hole_rows
from cadtocae.hole_plan import build_hole_plan, load_hole_plan
from test_step06_hole_inputs import input_rows
import test_step06_hole_inputs as input_fixture


def fixture():
    members, components = [], []
    for role, length, kind, policy in (("PURLIN_SUPPORT", .08, "ANGLE", "SOLID"),
                                        ("PURLIN_LOCAL", .2, "C_CHANNEL", "SHELL"),
                                        ("INCLINED_BEAM", 3., "C_CHANNEL", "SHELL")):
        params = dict(leg_a_m=.1, leg_b_m=.063, t_m=.006, inner_root_radius_m=.007) if kind == "ANGLE" else dict(h_m=.1,b_m=.05,t_m=.002,lip_m=.015)
        components.append(dict(component_code=role, part_name="PART_"+role, length_m=length,
                               section_kind=kind, model_policy=policy, section_params_m=params))
        members.append(dict(component_code=role, canonical_role=role, part_name="PART_"+role,
                            instance_name=role+"_01", connection_group="P01" if role != "INCLINED_BEAM" else None,
                            geometry_info=dict(length=length), placement=dict(translation=[1.,2.,3.],rotation_steps=[])))
    return dict(project_id="TEST_STEP06",model_name="TEST_STEP06",instances=members), components


class PlanTests(unittest.TestCase):
    def setUp(self): self.summary,self.components=fixture(); self.rows=input_rows()
    def plan(self): return build_hole_plan(self.summary,normalize_hole_rows(self.rows),self.components)

    def test_two_driving_and_two_derived(self):
        plan=self.plan()
        self.assertEqual(len(plan.driving_holes),2);self.assertEqual(len(plan.derived_holes),2)
        self.assertEqual({h.target_role for h in plan.derived_holes},{"PURLIN_LOCAL","INCLINED_BEAM"})
        self.assertTrue(all(h.target_local_center_m is None for h in plan.derived_holes))
        self.assertTrue(all(h.validation_status=="TARGET_SURFACE_PENDING_RUNTIME" for h in plan.derived_holes))
        json.dumps(plan.to_dict(),allow_nan=False)

    def test_part_local_outer_root_and_mid_thickness(self):
        holes={h.hole_id:h for h in self.plan().driving_holes}
        self.assertEqual(holes['PS_TO_PURLIN'].local_center_m,(.05,.003,.04))
        self.assertEqual(holes['PS_TO_BEAM'].local_center_m,(.003,.035,.04))
        self.assertEqual(holes['PS_TO_PURLIN'].local_axis,(0.,1.,0.))
        self.assertEqual(holes['PS_TO_BEAM'].local_axis,(1.,0.,0.))

    def test_end_reference_is_local_length(self):
        self.rows[0].update(end_reference="END",distance_from_end_mm=25.)
        hole=next(h for h in self.plan().driving_holes if h.hole_id=="PS_TO_PURLIN")
        self.assertAlmostEqual(hole.local_center_m[2],.055)

    def test_b_can_be_long_leg(self):
        self.components[0]['section_params_m'].update(leg_a_m=.063,leg_b_m=.1)
        h=next(h for h in self.plan().driving_holes if h.hole_id=="PS_TO_PURLIN")
        self.assertEqual(h.local_center_m,(.003,.05,.04))

    def test_fillet_does_not_shift_zero(self):
        before=self.plan().driving_holes
        self.components[0]['section_params_m']['inner_root_radius_m']=.01
        self.assertEqual([h.local_center_m for h in before],[h.local_center_m for h in self.plan().driving_holes])

    def test_boundary_preflight_never_clamps(self):
        for key,value in (("distance_from_angle_corner_mm",110), ("distance_from_angle_corner_mm",19),
                          ("distance_from_angle_corner_mm",94), ("distance_from_end_mm",90),
                          ("distance_from_end_mm",6), ("hole_diameter_mm",100)):
            self.rows=input_rows();self.rows[0][key]=value
            before=deepcopy(self.rows)
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.plan()
            self.assertEqual(self.rows,before)

    def test_same_group_not_name_suffix_resolution(self):
        self.summary['instances'][1]['instance_name']='CUSTOM_LOCAL'
        other=deepcopy(self.summary['instances'][1]);other.update(instance_name='PURLIN_LOCAL_01',connection_group='P02')
        self.summary['instances'].append(other)
        target=next(h for h in self.plan().derived_holes if h.target_role=='PURLIN_LOCAL')
        self.assertEqual(target.target_instance,'CUSTOM_LOCAL')

    def test_missing_or_ambiguous_target(self):
        member=self.summary['instances'].pop(1)
        with self.assertRaisesRegex(ValueError,'unique'):self.plan()
        self.summary['instances'].extend([member,dict(member,instance_name='OTHER')])
        with self.assertRaisesRegex(ValueError,'unique'):self.plan()

    def test_shared_part_detection_for_all_three_roles(self):
        for member in list(self.summary['instances']):
            self.summary['instances'].append(dict(deepcopy(member),instance_name=member['instance_name']+'_OTHER',
                                                  canonical_role='OTHER',connection_group='P02'))
        plan=self.plan()
        for hole in (*plan.driving_holes,*plan.derived_holes):
            self.assertTrue(hole.shared_part_info.shared_part)
            self.assertEqual(hole.shared_part_info.requires_instance_isolation, hole in plan.derived_holes)
            self.assertEqual(len(hole.shared_part_info.instance_names),2)

    def test_no_shared_part(self):
        for h in (*self.plan().driving_holes,*self.plan().derived_holes):self.assertFalse(h.shared_part_info.shared_part)

    def shared_supports(self, explicit=False):
        for n in range(2,5):
            for member in list(self.summary['instances'][:2]):
                copied=deepcopy(member)
                copied.update(instance_name=member['component_code']+'_%02d'%n,connection_group='P%02d'%n)
                copied['placement']['translation']=[n,2*n,3*n]
                self.summary['instances'].append(copied)
            if explicit:self.rows.extend(dict(r,connection_group='P%02d'%n) for r in input_rows())

    def test_shared_standard_inherits_p01_for_four_instances(self):
        self.shared_supports()
        p=self.plan();e=p.part_executions[0]
        self.assertEqual(e['execution_policy'],'MODIFY_SHARED_PART_ONCE')
        self.assertTrue(e['hole_pattern_identical']);self.assertFalse(e['requires_instance_isolation'])
        self.assertEqual(e['expected_affected_instances'],['PURLIN_SUPPORT_%02d'%i for i in range(1,5)])
        self.assertEqual([x['pattern_source'] for x in e['instance_patterns']],['EXPLICIT_GROUP']+['P01_STANDARD_INHERITED']*3)
        self.assertTrue(all(not h.shared_part_info.requires_instance_isolation for h in p.driving_holes))

    def test_explicit_four_identical_patterns_only_one_execution(self):
        self.shared_supports(explicit=True)
        p=self.plan();self.assertEqual(len(p.driving_holes),8);self.assertEqual(len(p.part_executions),1)
        self.assertEqual(p.part_executions[0]['execution_policy'],'MODIFY_SHARED_PART_ONCE')

    def test_different_or_disabled_p02_pattern_requires_isolation(self):
        for change in ({'distance_from_end_mm':30},{'enabled':False}):
            self.summary,self.components=fixture();self.rows=input_rows();self.shared_supports(explicit=True)
            self.rows[2].update(change)
            e=self.plan().part_executions[0]
            self.assertEqual(e['execution_policy'],'PART_ISOLATION_REQUIRED')
            self.assertTrue(e['requires_instance_isolation']);self.assertFalse(e['hole_pattern_identical'])

    def test_shared_geometry_mismatch_cannot_be_authorized(self):
        self.shared_supports()
        self.summary['instances'][3]['geometry_info']['section_kind']='OTHER'
        with self.assertRaisesRegex(ValueError,'section/model policy conflict'):self.plan()

    def test_ids_stable_under_input_order(self):
        before=self.plan().to_dict();self.rows.reverse()
        after=self.plan().to_dict()
        for value in (before,after):
            for h in value['driving_holes']:h.pop('source_row')
        self.assertEqual(before,after)
        self.assertIn('STEP06_DRIVING_P01_PS_TO_PURLIN',[h.driving_hole_id for h in self.plan().driving_holes])

    def test_source_global_transformed_target_not_copied(self):
        h=next(h for h in self.plan().derived_holes if h.target_role=='PURLIN_LOCAL')
        self.assertEqual(h.global_source_center_m,(1.05,2.003,3.04))
        self.assertEqual(h.global_axis,(0.,1.,0.))
        self.assertIsNone(h.target_local_center_m)

    def test_rotation_applied_to_axis_without_translation(self):
        self.summary['instances'][0]['placement']=dict(translation=[0.,0.,0.],rotation_steps=[dict(axis_point=[0.,0.,0.],axis_direction=[0.,0.,1.],angle_deg=90.)])
        h=next(h for h in self.plan().derived_holes if h.target_role=='PURLIN_LOCAL')
        self.assertAlmostEqual(h.global_source_center_m[0],-.003)
        self.assertAlmostEqual(h.global_axis[0],-1.)

    def test_ambiguous_legacy_pose_remains_pending(self):
        self.summary['instances'][0]['placement']['rotation_steps']=[dict(axis_point=[0.,0.,0.],axis_direction=[0.,0.,1.],angle_deg=90.)]
        for h in self.plan().derived_holes:
            self.assertEqual(h.source_pose_status,'POSE_PENDING_RUNTIME')
            self.assertIsNone(h.global_source_center_m);self.assertIsNone(h.global_axis)

    def test_scope_and_project(self):
        for update in ({'project_id':'OTHER'}, {'connection_group':'P02'}):
            self.rows=[dict(r,**update) for r in input_rows()]
            with self.assertRaises(ValueError):self.plan()

    def test_summary_geometry_mismatch(self):
        self.summary['instances'][0]['geometry_info']['length']=.09
        with self.assertRaisesRegex(ValueError,'length mismatch'):self.plan()

    def test_summary_duplicate_instance_rejected(self):
        self.summary['instances'].append(deepcopy(self.summary['instances'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate instance'):self.plan()

    def test_missing_placement_rejected(self):
        self.summary['instances'][0].pop('placement')
        with self.assertRaisesRegex(ValueError,'placement'):self.plan()

    def test_invalid_angle_geometry_rejected(self):
        for updates in ({'leg_b_m':.1},{'t_m':.07},{'inner_root_radius_m':float('nan')}):
            self.summary,self.components=fixture()
            self.components[0]['section_params_m'].update(updates)
            with self.subTest(updates=updates),self.assertRaises(ValueError):self.plan()

    def test_planner_preserves_input_objects(self):
        original=deepcopy((self.summary,self.rows,self.components))
        self.plan()
        self.assertEqual((self.summary,self.rows,self.components),original)

    def test_disabled_hole_no_derived_or_execution_intent(self):
        self.rows[1]['enabled']=False
        p=self.plan();self.assertEqual(len(p.derived_holes),1);self.assertEqual(len(p.disabled_hole_ids),1)

    def test_missing_second_leg(self):
        self.rows[1]['leg']='LONG_LEG'
        with self.assertRaisesRegex(ValueError,'SHORT_LEG'):self.plan()

    def test_file_interface_never_requires_generated_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);summary=root/'summary.json';summary.write_text(json.dumps(self.summary))
            xlsx=input_fixture.InputTests().filled_workbook(tmp)
            def export(source, target, selection):
                self.assertEqual(selection,'complete')
                target.write_text(json.dumps({'components':self.components}));return target
            with patch('cadtocae.hole_plan.export_abaqus_json',side_effect=export):
                result=load_hole_plan(root/'components.xlsx',summary,xlsx)
            self.assertEqual(len(result.derived_holes),2)
