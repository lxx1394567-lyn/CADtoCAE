import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from cadtocae.connector_b1_plan import fingerprint
from cadtocae.connector_groups import build_group_plan
from cadtocae.support_beam_connector import build_support_beam_geometry
from cadtocae.connector_integration import integrated_plan, integrated_source
from test_step06_spsc_geometry import spsc


def actual():
    data = json.loads((Path(__file__).parent/'fixtures/step06_dp_ang14_completed_holes.json').read_text(encoding='utf-8'))
    return data['holes'], data['report']


class DPConnectorTests(unittest.TestCase):
    def test_actual_ang14_all_eight_from_successful_hole_report(self):
        h, r = actual()
        with tempfile.TemporaryDirectory() as tmp:
            ns = {'__name__': 'test'}
            exec(integrated_source(integrated_plan(h, Path(tmp)), 'unused'), ns)
        members = {m['instance_name']: m for m in h['instances']}
        for builder in (build_group_plan, build_support_beam_geometry):
            connections = builder(h, r, 'DP')['connections']
            self.assertEqual([c['connection_group'] for c in connections], ['P01','P02','P03','P04'])
            self.assertEqual(len({tuple(c['rp_purlin']) for c in connections}), 4)
            for c in connections:
                self.assertEqual(c['source_part'], members[c['source_instance']]['part_name'])
                self.assertEqual(c['target_part'], members[c['target_instance']]['part_name'])
                self.assertEqual((c['width_m'],c['total_length_m']), (.012,.030))
                frame = ns['b1_frame'](c)
                self.assertLess(frame['coaxial_error_m'], 1.e-6)
        self.assertEqual(len({c['target_instance'] for c in build_support_beam_geometry(h,r,'DP')['connections']}), 1)

    def test_dp_round_slot_and_spsc_same_plans_except_project(self):
        for size in ((.009,.009),(.010,.032)):
            h,r=spsc('NO_STRUCTURE_PREFIX',size,size)
            old=[fn(h,r,'SP_SC') for fn in (build_group_plan,build_support_beam_geometry)]
            h['structure_type']='DP';r['plan_fingerprint']=fingerprint(h)
            new=[fn(h,r) for fn in (build_group_plan,build_support_beam_geometry)]
            for a,b in zip(old,new):
                for x,y in zip(a['connections'],b['connections']):
                    x.pop('step06_a_fingerprint',None);y.pop('step06_a_fingerprint',None)
                    self.assertEqual(x,y)

    def test_summary_type_authoritative_and_unknown_type_rejected(self):
        h,r=actual()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/(h['project_id']+'_assembly_summary.json')).write_text(json.dumps(dict(project_id=h['project_id'],structure_type='DP')))
            h['structure_type']='SP_SC'
            self.assertEqual(integrated_plan(h,folder)['structure_type'],'DP')
        h,r=actual()
        for fn in (build_group_plan,build_support_beam_geometry):
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_STRUCTURE_TYPE'):fn(h,r,'UNKNOWN')

    def test_step05_generic_snapshot_detects_suppression_and_changes(self):
        h,r=actual()
        ns={'__name__':'test'}
        with tempfile.TemporaryDirectory() as tmp:
            exec(integrated_source(integrated_plan(h,Path(tmp)),'unused'),ns)
        class Obj:
            id=1
            suppressed=False
            __members__=['sketch']
            @property
            def sketch(self):raise RuntimeError('Feature does not have path sketch')
            def __str__(self):return 'stable object'
        obj=Obj();model=NS(constraints={'STEP05_DP_CUSTOM':obj},rootAssembly=NS(features={'STEP05_DP_RP':obj}))
        before=ns['integrated_step05_state'](model)
        obj.suppressed=True
        self.assertNotEqual(before,ns['integrated_step05_state'](model))
        obj.suppressed=False
        self.assertEqual(before,ns['integrated_step05_state'](model))
        obj.id=2
        self.assertNotEqual(before,ns['integrated_step05_state'](model))
        obj.id=1
        model.rootAssembly.features.clear()
        self.assertNotEqual(before,ns['integrated_step05_state'](model))

    def test_actual_report_corruption_blocks_before_geometry_execution(self):
        for key,value in (('target_part','WRONG_PART'),('width_m',.015),('intersection_global',[0,0,0])):
            h,r=actual();r['inclined_beam'][2][key]=value
            with self.assertRaises(ValueError):build_support_beam_geometry(h,r,'DP')
