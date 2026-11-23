import copy
import json
import math
import unittest
from pathlib import Path
from cadtocae.dp_hoop_brace_plan import build_dp_hoop_brace_plan, resolve_groups, choose_brace_rp
from cadtocae.hoop_brace_setup import hoop_brace_source
from cadtocae.hole_transforms import step04_local_point_to_global as point


def fixture():
    return json.loads((Path(__file__).parent/'fixtures/step06_dp_ang14_hoop_brace.json').read_text(encoding='utf-8'))


def build(f):return build_dp_hoop_brace_plan(f['summary'],f['holes'],f['components'])


class DPHoopTests(unittest.TestCase):
    def test_ang35_actual_topology_with_synthetic_input_sizes(self):
        f=json.loads((Path(__file__).parent/'fixtures/step06_dp_ang35_hoop_synthetic_inputs.json').read_text(encoding='utf-8'))
        p=build(f)
        self.assertEqual(len(p['connections']),2)
        self.assertEqual([c['selected_hole_id'] for c in p['connections']],['HOOP_LEFT_01','HOOP_LEFT_01'])
        for c in p['connections']:self.assertAlmostEqual(c['rp_distance_m'],.005)

    def test_actual_mapping_three_holes_and_three_mm_spacing(self):
        p=build(fixture())
        self.assertEqual((p['front_hoop_group'],p['rear_hoop_group']),('HOOP_01','HOOP_02'))
        self.assertEqual(p['brace_hoop_half'],'A')
        for c,y in zip(p['connections'],(.0015,-.0015)):
            self.assertEqual(c['selected_hole_id'],'HOOP_RIGHT_01')
            self.assertEqual(len(c['hole_selection_evidence']['candidates']),3)
            self.assertEqual((c['width_m'],c['total_length_m']),(.014,.025))
            self.assertAlmostEqual(c['rp_distance_m'],.003)
            self.assertAlmostEqual(c['hoop_rp_global'][1],y)
            self.assertAlmostEqual(c['brace_rp_global'][1],-y)

    def test_group_names_and_hole_names_have_no_numeric_or_side_meaning(self):
        f=fixture()
        for i,g in enumerate(f['summary']['hoop_groups']):
            old=g['group_id'];new=('REAR_NUMBER_99','FRONT_NUMBER_03')[i];g['group_id']=new
            for m in f['summary']['instances']:
                if m.get('connection_group')==old:m['connection_group']=new
        for h in f['holes']['hoop_hole_plan']['driving_holes']:h['hole_id']='ARBITRARY_'+h['hole_id']
        p=build(f)
        self.assertEqual(p['front_hoop_group'],'REAR_NUMBER_99')
        self.assertEqual(p['connections'][0]['selected_hole_id'],'ARBITRARY_HOOP_RIGHT_01')

    def test_axis_mapping_fallback_and_ambiguity(self):
        f=fixture()
        for g in f['summary']['hoop_groups']:
            for k in ('column_instance','column_role','brace_role'):g.pop(k,None)
        p=build(f);self.assertEqual(p['group_mapping_evidence']['FRONT']['method'],'UNIQUE_COLUMN_AXIS_MATCH')
        f['summary']['hoop_groups'].append(copy.deepcopy(f['summary']['hoop_groups'][0]))
        with self.assertRaisesRegex(ValueError,'DP_HOOP_GROUP_MAPPING_AMBIGUOUS'):build(f)

    def test_hole_tie_and_semantic_priority(self):
        f=fixture();holes=f['holes']['hoop_hole_plan']['driving_holes']
        duplicate=copy.deepcopy(holes[1]);duplicate['hole_id']='OTHER';holes.append(duplicate)
        with self.assertRaisesRegex(ValueError,'DP_HOOP_BRACE_HOLE_AMBIGUOUS'):build(f)
        holes[1]['connection_target']='BRACE_FRONT';duplicate['connection_target']='BRACE_REAR'
        p=build(f);self.assertEqual([c['selected_hole_id'] for c in p['connections']],['HOOP_RIGHT_01','OTHER'])

    def test_rotated_model_no_global_y_rule(self):
        f=fixture();base=build(f)
        rotation=dict(axis_point=[1.,2.,3.],axis_direction=[1.,2.,1.],angle_deg=43.)
        transform=dict(translation=[0.,0.,0.],rotation_steps=[rotation])
        for m in f['summary']['instances']:m['placement']['rotation_steps'].append(rotation)
        # Explicit semantic association is invariant under rigid rotation.
        p=build(f)
        for a,b in zip(base['connections'],p['connections']):
            self.assertEqual(a['selected_hole_id'],b['selected_hole_id'])
            for key in ('hoop_rp_global','brace_rp_global'):
                self.assertLess(math.dist(point(a[key],transform),b[key]),1.e-9)

    def test_side_equidistance_and_round_profile(self):
        with self.assertRaisesRegex(ValueError,'DP_BRACE_RP_SIDE_AMBIGUOUS'):
            choose_brace_rp((0,.025,.025),(1,0,0),.003,dict(translation=[0,0,0],rotation_steps=[]),.05)
        f=fixture()
        for h in f['holes']['hoop_hole_plan']['driving_holes']:h.update(hole_type='ROUND',total_length_m=h['width_m'])
        self.assertTrue(all(c['hole_type']=='ROUND' for c in build(f)['connections']))

    def test_runtime_contract_and_no_geometry_mutation(self):
        p=build(fixture());source=hoop_brace_source(p,'unused')
        for forbidden in ('__members__','CutExtrude(','PartitionFaceBy','ConnectorForce('):self.assertNotIn(forbidden,source)
        ns={'__name__':'test'};exec(source,ns)
        for c in p['connections']:
            frame=ns['b1_frame'](dict(rp_support=c['hoop_rp_global'],rp_purlin=c['brace_rp_global'],bolt_axis=c['bolt_axis'],slot_major_axis=c['brace_axis']))
            self.assertLess(frame['coaxial_error_m'],1.e-6)
            self.assertIn('STEP06_SURF_BRACE_',ns['dp_hb_names'](c['side'])['brace_surface'])
