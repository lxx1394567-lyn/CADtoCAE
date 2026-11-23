import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from cadtocae.batch_runner.delivery import deliver, checked_model_path, open_model
from cadtocae.batch_runner.executor import AbaqusExecutor, digest

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = AbaqusExecutor(['test-launcher'])
        self.project = SimpleNamespace(prefix='PROJECT_001', key='key-001', stages=[SimpleNamespace(number=1, contract={'parts':['P'], 'kind':'custom'})])
        self.source = self.root/'checkpoint.cae'
        self.source.write_bytes(b'TEST DOUBLE ONLY: NOT A REAL CAE')
        self.record = {'stages':[dict(status='SUCCESS', checkpoint=str(self.source), checkpoint_hash=digest(self.source), artifacts={})]}
        self.mock = patch('cadtocae.batch_runner.delivery.verify_file', return_value={'status':'PASSED', 'test_double':True})
        self.verify = self.mock.start()
        self.addCleanup(self.mock.stop)
        self.addCleanup(self.temp.cleanup)
    def run_delivery(self):
        return deliver(self.root, self.project, self.record, self.executor, self.root/'logs')
    def test_copy_and_no_rebuild(self):
        r=self.run_delivery()
        self.assertEqual(r['save_status'],'SAVED')
        self.assertEqual(Path(r['path']).name,'PROJECT_001_step01.cae')
        self.assertEqual(Path(r['path']).read_bytes(),self.source.read_bytes())
        self.verify.assert_called_once()
    def test_existing_user_file_never_overwritten(self):
        folder=self.root/'CAE_Results';folder.mkdir()
        old=folder/'PROJECT_001_step01.cae';old.write_bytes(b'USER ORIGINAL')
        r=self.run_delivery()
        self.assertEqual(r['status'], 'FAILED')
        self.assertEqual(old.read_bytes(),b'USER ORIGINAL')
    def test_repeat_reuses_bytes_but_revalidates(self):
        a=self.run_delivery();b=self.run_delivery()
        self.assertEqual(a['path'],b['path'])
        self.assertTrue(b['published'])
        self.assertEqual(self.verify.call_count,2)
    def test_changed_source_replaces_fixed_name(self):
        a=self.run_delivery()
        self.source.write_bytes(b'ANOTHER TEST FIXTURE')
        self.record['stages'][0]['checkpoint_hash']=digest(self.source)
        b=self.run_delivery();c=self.run_delivery()
        self.assertEqual(a['path'],b['path'])
        self.assertEqual(b['path'],c['path'])
        self.assertTrue(Path(a['path']).exists())
    def test_changed_checkpoint_rejected(self):
        self.source.write_bytes(b'changed')
        r=self.run_delivery()
        self.assertEqual(r['status'],'FAILED')
        self.verify.assert_not_called()
    def test_failure_does_not_certify_delivery(self):
        self.verify.return_value={'status':'FAILED','error':'not a database'}
        r=self.run_delivery()
        self.assertEqual(r['status'],'FAILED')
        self.assertEqual(r['save_status'],'SAVED')
        with self.assertRaises(ValueError): checked_model_path(r)
    def test_simulator_never_delivers_success(self):
        self.executor.kind='simulation'
        r=self.run_delivery()
        self.assertEqual(r['status'],'NOT_VERIFIED')
        self.assertFalse((self.root/'CAE_Results').exists())
    def test_no_continuous_prefix_no_delivery(self):
        self.record['stages'].insert(0,{'status':'MISSING'})
        r=self.run_delivery()
        self.assertIsNone(r['path'])
        self.verify.assert_not_called()
    def test_file_changed_or_deleted_blocks_gui_open(self):
        r=self.run_delivery();Path(r['path']).write_bytes(b'corrupt')
        with self.assertRaises(ValueError): checked_model_path(r)
        Path(r['path']).unlink()
        with self.assertRaises(ValueError): checked_model_path(r)
    def test_gui_uses_configured_gui_not_nogui(self):
        r=self.run_delivery()
        with patch('cadtocae.batch_runner.delivery.subprocess.Popen') as popen, patch('cadtocae.batch_runner.delivery.shutil.which', return_value='test-launcher'):
            open_model(self.executor,r)
            cmd=popen.call_args.args[0]
            self.assertIn('cae',cmd)
            self.assertTrue(any(x.startswith('database=') for x in cmd))
            self.assertFalse(any('noGUI' in x for x in cmd))
    def test_nine_project_outputs_are_independent(self):
        paths=[]
        for n in range(9):
            self.project.prefix='PROJECT_%03d'%n;self.project.key='key-%d'%n
            paths.append(self.run_delivery()['path'])
        self.assertEqual(len(set(paths)),9)
        self.assertTrue(all(Path(p).exists() for p in paths))
    def test_unknown_contract_is_not_verified(self):
        self.project.stages[0].contract['parts']=[]
        r=self.run_delivery()
        self.assertEqual(r['status'],'NOT_VERIFIED')
        self.verify.assert_not_called()

if __name__=='__main__': unittest.main()
