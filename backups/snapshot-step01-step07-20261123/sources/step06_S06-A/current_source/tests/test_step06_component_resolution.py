import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cadtocae.hole_component_resolution import resolve_hole_component,mapping_diagnostics
from cadtocae.hole_plan import build_step06_a_plan
from cadtocae.hole_projects import can_generate,project_details
from cadtocae.step06_release import generate_release_batch
from cadtocae.hoop_hole_plan import unique_hoop_parts,build_hoop_hole_plan
from test_step06_derived import fixture_a
from test_step06_project_tables import add_hoop


class ComponentResolutionTests(unittest.TestCase):
    def test_five_projects_use_summary_names_not_project_name(self):
        for name in ('SP_SC_ANG18','SP_SC_ANG33','SP_DC_ANG28','DP_ANG14','DP_ANG35'):
            with self.subTest(project=name):
                summary,components,rows=fixture_a()
                summary['project_id']=name+'_UNRELATED_ID'
                summary['model_name']=summary['project_id']
                rows=[replace(r,project_id=summary['project_id']) for r in rows]
                for m in summary['instances']:
                    m['part_name']='ACTUAL_'+m['component_code']
                before=copy.deepcopy(components)
                plan=build_step06_a_plan(summary,rows,components)
                self.assertEqual({h['source_part'] for h in plan['driving_holes']},{'ACTUAL_PURLIN_SUPPORT'})
                self.assertEqual({h['target_part'] for h in plan['derived_holes']},{'ACTUAL_PURLIN_LOCAL','ACTUAL_INCLINED_BEAM'})
                self.assertTrue(plan['part_executions'][0]['shared_part'])
                self.assertEqual(components,before)
                self.assertTrue(all(d['components_match']=='PASS' for d in mapping_diagnostics(summary,components)))

    def test_exact_part_priority_and_collision_no_fallback(self):
        s,c,_=fixture_a();m=s['instances'][0]
        exact=next(x for x in c if x['part_name']==m['part_name'])
        other=dict(exact,part_name='OTHER')
        _,e=resolve_hole_component(m,c+[other]);self.assertEqual(e['method'],'EXACT_PART')
        broken=copy.deepcopy(c);broken[0]['component_code']='PURLIN_LOCAL'
        with self.assertRaisesRegex(ValueError,'canonical role conflict'):resolve_hole_component(m,broken+[other])

    def test_missing_duplicate_geometry_and_section_length_conflicts(self):
        s,c,_=fixture_a();m=copy.deepcopy(s['instances'][0]);m['part_name']='SUMMARY_ONLY'
        source=next(x for x in c if x['component_code']=='PURLIN_SUPPORT')
        for records in ([],c+[dict(source,part_name='AMBIGUOUS')]):
            with self.assertRaisesRegex(ValueError,'unique component'):resolve_hole_component(m,records)
        for change in (dict(section_kind='PIPE'),dict(length_m=.123),dict(section_params_m={})):
            records=[dict(x,**change) if x['component_code']=='PURLIN_SUPPORT' else x for x in c]
            with self.assertRaises(ValueError):resolve_hole_component(m,records)

    def test_diagnostics_include_all_four_instances_and_actual_parts(self):
        s,c,_=fixture_a();c=[x for x in c if x['component_code']!='PURLIN_SUPPORT']
        d=mapping_diagnostics(s,c)
        support=next(x for x in d if x['role']=='PURLIN_SUPPORT')
        self.assertEqual(support['components_match'],'FAIL');self.assertEqual(len(support['instances_found']),4)
        text=project_details(dict(project_id='DP',source_folder='test',part_mapping=d))
        for label in ('Role: PURLIN_SUPPORT','Instances found:','Actual Part names:','Components match: FAIL'):
            self.assertIn(label,text)

    def test_hoop_summary_binding_and_excel_part_mismatch_rejected(self):
        s,c,_=fixture_a();add_hoop(s,c)
        for m in s['instances']:
            if m.get('canonical_role')=='HOOP':m['part_name']='SUMMARY_HOOP'
        catalog=unique_hoop_parts(s,c)
        self.assertEqual(set(catalog),{'SUMMARY_HOOP'})
        row=dict(part_name='PART_HOOP',hole_id='HOOP_LEFT_01',end_reference='LEFT',hole_type='ROUND',enabled=False)
        with self.assertRaisesRegex(ValueError,'Unknown/duplicate'):build_hoop_hole_plan(catalog,[row])

    def test_dp_generates_only_hole_setup_without_connector(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);script=folder/'DP_hole.py'
            script.write_text("REPORT_PATH='unused'\nif __name__ == '__main__':\n    pass\n")
            row=dict(source_folder=tmp,project_id='DP',plan={'project_id':'DP'},input_identity={},warnings=[],errors=[],
                     input_status='READY',capability='HOLE_READY',connector_capability='CONNECTOR_NOT_YET_SUPPORTED')
            scan=dict(source_folder=tmp,include_subfolders=False,projects=[row])
            self.assertTrue(can_generate(row))
            with patch('cadtocae.hole_projects.scan_projects',return_value=scan),patch('cadtocae.step06_release.write_hole_setup',return_value={'script':script}),patch('cadtocae.step06_release.integrated_plan') as connector:
                result=generate_release_batch(scan)
            connector.assert_not_called()
            self.assertEqual(result['generation_counts']['succeeded'],1)
            self.assertEqual(set(result['projects'][0]['generated_files']),{'script'})
            self.assertIn('CONNECTOR_NOT_YET_SUPPORTED',result['projects'][0]['result'])
