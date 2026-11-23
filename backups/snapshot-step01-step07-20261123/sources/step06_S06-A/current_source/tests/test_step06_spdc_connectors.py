import copy
import json
from pathlib import Path
import tempfile
import unittest

from cadtocae.connector_b1_plan import fingerprint
from cadtocae.connector_groups import build_group_plan
from cadtocae.support_beam_connector import build_support_beam_geometry
from cadtocae.connector_integration import integrated_plan, integrated_source
from test_step06_spsc_geometry import spsc


def actual():
    data=json.loads((Path(__file__).parent/'fixtures/step06_spdc_ang17_completed_holes.json').read_text(encoding='utf-8'))
    return data['holes'],data['report']


class SPDCConnectorTests(unittest.TestCase):
    def test_actual_ang17_mapping_frames_and_counts(self):
        h,r=actual()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/(h['project_id']+'_assembly_summary.json')).write_text(json.dumps(dict(project_id=h['project_id'],structure_type='SP_DC')))
            p=integrated_plan(h,Path(tmp));ns={'__name__':'test'}
            exec(integrated_source(p,'unused'),ns)
        self.assertEqual(p['structure_type'],'SP_DC')
        self.assertEqual([p[k] for k in ('expected_rps','expected_couplings','expected_wires','expected_connectors')],[16,16,8,8])
        for fn,target in ((build_group_plan,'PURLIN_LOCAL'),(build_support_beam_geometry,'INCLINED_BEAM')):
            connections=fn(h,r,'SP_DC')['connections']
            self.assertEqual([c['connection_group'] for c in connections],['P01','P02','P03','P04'])
            self.assertEqual(len({tuple(c['rp_purlin']) for c in connections}),4)
            for i,c in enumerate(connections,1):
                self.assertEqual(c['source_instance'],'PURLIN_SUPPORT_%02d'%i)
                self.assertEqual(c['target_instance'],target+('_%02d'%i if target=='PURLIN_LOCAL' else '_01'))
                self.assertLessEqual(ns['b1_frame'](c)['coaxial_error_m'],1e-6)

    def test_incomplete_hoop_report_does_not_block_either_family(self):
        h,r=actual()
        expected=[fn(h,r,'SP_DC') for fn in (build_group_plan,build_support_beam_geometry)]
        for key in list(r):
            if 'hoop' in key.lower():r.pop(key)
        r['hoop_validation']={'status':'NOT_READY','created_holes':0}
        self.assertEqual(expected,[fn(h,r,'SP_DC') for fn in (build_group_plan,build_support_beam_geometry)])

    def test_success_fingerprint_and_beam_geometry_still_required(self):
        for mode in ('status','fingerprint','missing_beam'):
            h,r=actual()
            if mode=='status':r['status']='FAILED'
            elif mode=='fingerprint':r['plan_fingerprint']='invalid'
            else:r['inclined_beam'].pop()
            with self.assertRaises(ValueError):build_support_beam_geometry(h,r,'SP_DC')

    def test_all_structures_identical_round_slot_mechanics(self):
        for dims in ((.008,.008),(.012,.030)):
            h,r=spsc('NO_STRUCTURE_PREFIX',dims,dims)
            expected=[fn(h,r,'SP_DC') for fn in (build_group_plan,build_support_beam_geometry)]
            for structure in ('SP_DC','DP'):
                h['structure_type']=structure;r['plan_fingerprint']=fingerprint(h)
                found=[fn(h,r) for fn in (build_group_plan,build_support_beam_geometry)]
                for old,new in zip(copy.deepcopy(expected),found):
                    for a,b in zip(old['connections'],new['connections']):
                        a.pop('step06_a_fingerprint',None);b.pop('step06_a_fingerprint',None)
                        self.assertEqual(a,b)

    def test_generated_contract_and_runtime_lint(self):
        from cadtocae.runtime_compatibility import assert_runtime_compatible
        h,r=actual()
        with tempfile.TemporaryDirectory() as tmp:
            source=integrated_source(integrated_plan(h,Path(tmp)),'unused')
        assert_runtime_compatible(source)
        for token in ('couplingType=KINEMATIC','u1=ON,u2=ON,u3=ON,ur1=OFF,ur2=OFF,ur3=OFF',
                      'components=(1,2,3),table=((5.0e8,2.0e8,2.0e8),)', 'PRESERVE_EXISTING_NO_LOAD_CREATED'):
            self.assertIn(token,source)
        self.assertNotIn('CutExtrude(',source)
        self.assertNotIn('ConnectorForce(',source)
        self.assertNotIn('__members__',source)
