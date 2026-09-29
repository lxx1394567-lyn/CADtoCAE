"""Legacy HOOP codes share one matcher across scan and generation."""
import copy
import json
from pathlib import Path
import shutil
import unittest
from openpyxl import load_workbook
import test_analysis_sp_dc as dc
from cadtocae.analysis_capability import is_hoop_family,match_hoop_component,GeometryReviewError
from cadtocae.analysis_discovery import scan_projects
from cadtocae.analysis_batch import generate_batch
from cadtocae.sp_dc_setup import build_sp_dc_plan,generate

class MatcherTests(unittest.TestCase):
    def test_family_variants(self):
        for code in ('HOOP','HOOP_1','HOOP_2','HOOP_ASSEMBLY_1','HOOP_ASSEMBLY_2'):
            self.assertTrue(is_hoop_family(code))
        for code in ('XHOOP','HOOP_BAD','HOOP_ASSEMBLY','PIPE',None):self.assertFalse(is_hoop_family(code))
    def test_part_identity_preserves_raw_codes(self):
        m=dict(part_name='P_HOOP_A',component_code='HOOP',canonical_role='HOOP')
        c=dict(part_name='P_HOOP_A',component_code='HOOP_1',section_kind='HOOP_BAND')
        before=copy.deepcopy((m,c));self.assertIs(match_hoop_component(m,[c]),c);self.assertEqual((m,c),before)
    def test_ambiguous_part_rejected_even_one_code_matches(self):
        m=dict(part_name='P',component_code='HOOP');a=dict(part_name='P',component_code='HOOP',section_kind='HOOP_BAND')
        with self.assertRaisesRegex(ValueError,'unique exact part_name'):match_hoop_component(m,[a,dict(a,component_code='HOOP_1')])
    def test_wrong_geometry_or_family_rejected(self):
        m=dict(part_name='P',component_code='HOOP')
        for code,kind in (('HOOP_1','PIPE'),('COLUMN_DOWN','HOOP_BAND')):
            with self.assertRaises(ValueError):match_hoop_component(m,[dict(part_name='P',component_code=code,section_kind=kind)])

class LegacyGroupTests(unittest.TestCase):
    def setUp(self):
        self.f=dc.DCTests();self.addCleanup(self.f.doCleanups);self.f.setUp()
        s=self.f.base.summary
        group1=[m for m in s['instances'] if m.get('connection_group')=='HOOP_01']
        for h in group1:
            third=copy.deepcopy(h);third.update(connection_group='HOOP_03',instance_name=h['instance_name'].replace('01','03'))
            third['placement']['translation'][2]=1.46;s['instances'].append(third)
        # A and B use different Parts, each reused by all three groups.
        for h in s['instances']:
            if h.get('canonical_role')=='HOOP':
                h['component_code']='HOOP';h['part_name']='P_HOOP' if h['instance_name'].endswith('_A') else 'P_HOOP2'
        self.f.base.write_summary()
        wb=load_workbook(self.f.base.components)
        for row in wb.active:
            if row[2].value=='抱箍组合1':row[2].value='抱箍1'
            if row[2].value=='抱箍组合2':row[2].value='抱箍2'
        wb.save(self.f.base.components);wb.close()
    def partial(self):
        for m in self.f.base.summary['instances']:
            if m.get('connection_group')=='HOOP_03':m['placement']['translation'][2]=1.56
        self.f.base.write_summary()
    def test_three_legacy_groups_full_and_generate_ten(self):
        before=self.f.base.summary_path.read_bytes()
        row=self.f.scan()['projects'][0]
        self.assertEqual(row['input_status'],'READY',row['errors'])
        self.assertEqual(row['expected_tie_count'],10)
        plan=build_sp_dc_plan(self.f.files)
        self.assertEqual(plan['expected_constraints']['tie_count'],10)
        mappings=[h['component_mapping'] for g in plan['column_hoop_groups'] for h in g['halves']]
        self.assertEqual({m['raw_component_code'] for m in mappings},{'HOOP'})
        self.assertEqual({m['component_record_code'] for m in mappings},{'HOOP_1','HOOP_2'})
        result=generate_batch(self.f.scan())
        self.assertEqual(result['generation_counts'],dict(succeeded=1,failed=0))
        self.assertEqual(self.f.base.summary_path.read_bytes(),before)
    def test_partial_overlap_review_blocks_direct_generation(self):
        self.partial();row=self.f.scan()['projects'][0]
        self.assertEqual(row['input_status'],'NEEDS_REVIEW')
        self.assertEqual(row['missing_requirements']['hoop_groups'],[])
        self.assertEqual(row['complete_hoop_group_count'],3)
        self.assertEqual(row['expected_nominal_tie_count'],10)
        self.assertIsNone(row['executable_tie_count'])
        self.assertIn('HOOP_03 axial band exceeds',row['first_blocking_reason'])
        self.assertAlmostEqual(row['geometry_review'][0]['overlap_length'],.04)
        out=self.f.root/'not_created'
        with self.assertRaises(GeometryReviewError):generate(self.f.files,output_dir=out)
        self.assertFalse(out.exists())
    def test_mixed_batch_skips_review_and_keeps_existing_files(self):
        self.partial();pid=self.f.base.summary['project_id'];ready='SP_DC_READY_FIXTURE'
        for p in list(self.f.root.iterdir()):
            if p.is_file() and p.name.startswith(pid):shutil.copy2(p,self.f.root/p.name.replace(pid,ready))
        path=self.f.root/(ready+'_assembly_summary.json');s=json.loads(path.read_text())
        s.update(project_id=ready,model_name=ready)
        for m in s['instances']:
            if m.get('connection_group')=='HOOP_03':m['placement']['translation'][2]=1.46
        path.write_text(json.dumps(s))
        protected=self.f.root/(pid+'_analysis_setup.py');protected.write_text('OLD UNTOUCHED')
        events=[];result=generate_batch(scan_projects(self.f.root),progress=events.append)
        self.assertEqual(result['generation_counts'],dict(succeeded=1,failed=0))
        self.assertEqual(protected.read_text(),'OLD UNTOUCHED')
        skipped=[e for e in events if e['event']=='skipped'];self.assertEqual(len(skipped),1)
        self.assertIn('geometry review required',skipped[0]['row']['skip_reason'])
        self.assertEqual(result['skipped_projects'][0]['project_id'],pid)

if __name__=='__main__':unittest.main()
