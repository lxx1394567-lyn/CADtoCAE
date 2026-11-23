import unittest,tempfile,json
from pathlib import Path
from cadtocae.step07_projects import scan_inplace
from cadtocae.step07_output import write_generated,lock_path
class UnifiedTests(unittest.TestCase):
 def fixture(self,p):
  project='SP_DC_TEST';(p/(project+'_assembly_summary.json')).write_text(json.dumps(dict(project_id=project,model_name=project)))
  (p/(project+'_step06_hole_report.json')).write_text(json.dumps(dict(project_id=project,status='SUCCESS')));return project
 def test_nonstandard_cae_needs_explicit_choice_even_if_only_one(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);project=self.fixture(p);(p/'luan.cae').touch();r=scan_inplace(p)[0];self.assertIsNone(r['cae']);self.assertTrue(r['ready'])
   (p/(project+'_step07_cae.json')).write_text(json.dumps(dict(project_id=project,target_model=project,cae_path=str(p/'luan.cae'))));self.assertEqual(scan_inplace(p)[0]['cae'],str(p/'luan.cae'))
 def test_multiple_cae_needs_choice_and_exact_name_first(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);project=self.fixture(p);(p/'luan.cae').touch();(p/(project+'.cae')).touch();r=scan_inplace(p)[0];self.assertIsNone(r['cae']);self.assertEqual(Path(r['candidates'][0]).stem,project)
 def test_controlled_update_archive_and_noop(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);f=p/'test.py';write_generated({f:'old'},p,'P',False)
   self.assertEqual(write_generated({f:'old'},p,'P',False)['status'],'ALREADY_IDENTICAL')
   with self.assertRaisesRegex(ValueError,'CONFIRMATION'):write_generated({f:'new'},p,'P',False)
   r=write_generated({f:'new'},p,'P',True);self.assertEqual(Path(r['backups'][0]).read_text(),'old');self.assertEqual(f.read_text(),'new')
 def test_running_project_blocks_update(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);lock=lock_path(p,'P');lock.parent.mkdir();lock.write_text('running')
   with self.assertRaisesRegex(ValueError,'RUNNING'):write_generated({p/'a.py':'code'},p,'P',True)
   self.assertFalse((p/'a.py').exists());self.assertTrue(lock.exists())
if __name__=='__main__':unittest.main()
