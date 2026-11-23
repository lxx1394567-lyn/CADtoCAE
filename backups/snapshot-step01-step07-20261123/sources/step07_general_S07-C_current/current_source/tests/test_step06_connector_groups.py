import copy
import unittest
from cadtocae.connector_b1_plan import fingerprint, build_b1_plan
from cadtocae.connector_groups import build_group_plan
from cadtocae.connector_setup import connector_script_source
from test_step06_connector_b1 import completed_holes


def four():
    a,r=completed_holes()
    old=copy.deepcopy(a);oldr=copy.deepcopy(r)
    a['instances']=[];a['driving_holes']=[];a['derived_holes']=[];r['purlin_local']=[]
    for n in range(1,5):
        group='P%02d'%n; suffix='%02d'%n
        s=copy.deepcopy(old['driving_holes'][0]);s.update(connection_group=group,source_instance='PURLIN_SUPPORT_'+suffix,driving_hole_id='driving'+group)
        d=copy.deepcopy(old['derived_holes'][0]);d.update(source_driving_hole_id=s['driving_hole_id'],target_instance='PURLIN_LOCAL_'+suffix,derived_hole_id='derived'+group)
        t=copy.deepcopy(oldr['purlin_local'][0]);t.update(connection_group=group,source_instance=s['source_instance'],target_instance=d['target_instance'])
        for k in ('source_global_center','intersection_global'):t[k]=[t[k][0]+n,t[k][1],t[k][2]]
        for m in copy.deepcopy(old['instances']):
            role='PURLIN_SUPPORT' if m['instance_name'].startswith('PURLIN_SUPPORT') else 'PURLIN_LOCAL'
            m.update(instance_name=role+'_'+suffix,connection_group=group,canonical_role=role)
            m['placement']['translation'][0]=n;a['instances'].append(m)
        a['driving_holes'].append(s);a['derived_holes'].append(d);r['purlin_local'].append(t)
    r['plan_fingerprint']=fingerprint(a)
    return a,r


class GroupsTests(unittest.TestCase):
    def test_four_shared_parts_independent_centers(self):
        a,r=four();p=build_group_plan(a,r)
        self.assertEqual(p['groups'],['P01','P02','P03','P04'])
        self.assertEqual(len(set(c['source_part'] for c in p['connections'])),1)
        self.assertEqual(len(set(tuple(c['rp_support']) for c in p['connections'])),4)
        self.assertEqual(p['connections'][0],build_b1_plan(a,r))

    def test_missing_duplicate_and_wrong_role_rejected(self):
        for mode in ('missing','duplicate','wrong'):
            a,r=four()
            if mode=='missing':a['instances'].pop()
            if mode=='duplicate':a['instances'].append(copy.deepcopy(a['instances'][-1]))
            if mode=='wrong':a['instances'][-1]['instance_name']='PURLIN_LOCAL_01'
            with self.assertRaises(ValueError):build_group_plan(a,r)

    def test_cross_group_report_rejected(self):
        a,r=four();r['purlin_local'][-1]['target_instance']='PURLIN_LOCAL_01'
        with self.assertRaises(ValueError):build_group_plan(a,r)

    def test_group_names_and_frames(self):
        a,r=four();p=build_group_plan(a,r);ns={'__name__':'test'}
        exec(connector_script_source(p,'unused.json'),ns)
        for c in p['connections']:
            names=ns['b1_names'](c['connection_group'])
            self.assertIn(c['connection_group'],names['wire'])
            self.assertEqual(names['connector_section'],'STEP06_CONNECTOR_SECTION_PURLIN_BOLT')
            self.assertLess(ns['b1_frame'](c)['coaxial_error_m'],1.e-6)


if __name__=='__main__':unittest.main()
