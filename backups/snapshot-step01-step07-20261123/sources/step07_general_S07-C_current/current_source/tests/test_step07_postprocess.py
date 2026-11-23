import json, tempfile, unittest, ast
from pathlib import Path
from cadtocae.step07_postprocess import generate_postprocess
from cadtocae.step07_postprocess_runtime import pp_new_dir, pp_peak

class PostprocessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.summary=self.root/'summary.json';self.odb=self.root/'result.odb';self.odb.write_bytes(b'test')
        self.data={'project_id':'SP_DC_TEST','instances':[{'instance_name':'SUPPORT_X','canonical_role':'PURLIN_SUPPORT'},{'instance_name':'HALF_A','canonical_role':'HOOP','connection_group':'G'},{'instance_name':'HALF_B','canonical_role':'HOOP','connection_group':'G'}]}
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.summary.write_text(json.dumps(self.data),encoding='utf-8')
    def generate(self,**kw):return generate_postprocess(self.summary,self.odb,self.root,**kw)
    def test_groups_and_no_mdb_operations(self):
        r=self.generate();self.assertEqual(r['plan']['groups']['hoops'],{'G':['HALF_A','HALF_B']})
        text=Path(r['script']).read_text(encoding='utf-8');ast.parse(text)
        for forbidden in ('openMdb(','.saveAs(','.submit(','.save('):self.assertNotIn(forbidden,text)
    def test_missing_group_fails(self):
        self.data['instances'][1]['connection_group']=None;self.save()
        with self.assertRaisesRegex(ValueError,'HOOP_GROUP_MISSING'):self.generate()
    def test_missing_odb_fails(self):
        self.odb.unlink()
        with self.assertRaisesRegex(ValueError,'ODB_NOT_FOUND'):self.generate()
    def test_invalid_job_path(self):
        with self.assertRaisesRegex(ValueError,'INVALID_JOB_ID'):self.generate(job_id='../bad')
    def test_result_directories_do_not_overwrite(self):
        one=pp_new_dir(str(self.root),'run');two=pp_new_dir(str(self.root),'run');self.assertNotEqual(one,two)
    def test_changed_script_archived(self):
        r=self.generate();p=Path(r['script']);p.write_text('# user changes',encoding='utf-8');self.generate()
        self.assertEqual(len(list((self.root/'Step07_Archive').glob('*.py'))),1)
    def test_case_is_not_inferred_from_name(self):
        self.assertEqual(self.generate()['plan']['case_label'],'USER_SELECTED_ODB_CASE_NOT_INFERRED')
    def test_luan_count_guard(self):
        self.data['project_id']='SP_DC_ANG19_LUANLUANLUAN-T0203';self.save()
        with self.assertRaisesRegex(ValueError,'LUAN_EXPECTED'):self.generate()
    def test_runtime_reference_has_no_external_import(self):
        p=Path(self.generate()['script']);self.assertNotIn('from cadtocae',p.read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
