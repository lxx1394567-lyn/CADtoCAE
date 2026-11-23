import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cadtocae.batch_runner.publication import publish, registry, store, recover, publication_lock
from cadtocae.batch_runner.executor import digest
from cadtocae.batch_runner.migration import plan_migration, apply_migration

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.n=0
    def publish(self, stage=9, content=b'FIRST VALIDATED TEST DOUBLE', key='key', prefix='PROJECT'):
        self.n+=1
        candidate=store(self.root,key)/('candidate%d.cae'%self.n)
        candidate.parent.mkdir(parents=True,exist_ok=True);candidate.write_bytes(content)
        suffix='_final' if stage==9 else '_step%02d'%stage
        result=dict(status='PASSED',stage=stage,sha256=digest(candidate),path=str(self.root/'CAE_Results'/(prefix+suffix+'.cae')))
        return publish(self.root,key,result,candidate)
    def test_repeat_exact_one_final_and_internal_json(self):
        a=self.publish();b=self.publish(content=b'NEW VALIDATED TEST DOUBLE')
        self.assertEqual(a['path'],b['path'])
        self.assertEqual([p.name for p in (self.root/'CAE_Results').iterdir()],['PROJECT_final.cae'])
        self.assertEqual(Path(a['path']).read_bytes(),b'NEW VALIDATED TEST DOUBLE')
        self.assertTrue(list(store(self.root,'key').rglob('publication.json')))
    def test_rejected_candidate_never_replaces(self):
        old=self.publish();candidate=self.root/'bad.cae';candidate.write_bytes(b'CORRUPT')
        with self.assertRaises(ValueError):publish(self.root,'key',dict(old,status='FAILED'),candidate)
        self.assertEqual(digest(old['path']),old['sha256'])
    def test_windows_sharing_violation_retains_old_and_recovers(self):
        old=self.publish()
        original=os.replace
        def fail_candidate(src,dst):
            if str(src).endswith('.cae'):raise PermissionError('Windows sharing violation')
            return original(src,dst)
        with patch('cadtocae.batch_runner.publication.os.replace',side_effect=fail_candidate):
            with self.assertRaises(RuntimeError):self.publish(content=b'NEW')
        self.assertEqual(digest(old['path']),old['sha256'])
        self.publish(content=b'NEW')
        self.assertEqual(Path(old['path']).read_bytes(),b'NEW')
    def test_crash_after_replace_before_index_recovered(self):
        self.publish()
        with patch('cadtocae.batch_runner.publication.finish',side_effect=OSError('interrupted metadata')):
            latest=self.publish(content=b'NEW')
        self.assertEqual(registry(self.root,'key')['final']['sha256'],latest['sha256'])
        with publication_lock(self.root):recover(self.root,'key')
        self.assertFalse((store(self.root,'key')/'pending.json').exists())
    def test_partial_preserves_final_then_full_retires_partial(self):
        old=self.publish();p=self.publish(stage=3,content=b'PARTIAL')
        self.assertEqual(digest(old['path']),old['sha256'])
        self.assertEqual(len(list((self.root/'CAE_Results').glob('*.cae'))),2)
        self.publish(content=b'FINAL2')
        self.assertFalse(Path(p['path']).exists())
        self.assertEqual(len(list((self.root/'CAE_Results').glob('*.cae'))),1)
        self.assertTrue(list(store(self.root,'key').rglob('PROJECT_step03.cae')))
    def test_partial_stage_replaces_previous_partial_only(self):
        old=self.publish(stage=2);self.publish(stage=3)
        self.assertFalse(Path(old['path']).exists())
        self.assertEqual(len(list((self.root/'CAE_Results').glob('*.cae'))),1)
    def test_nine_complete_projects_nine_fixed_files(self):
        for _ in range(2):
            for n in range(9):self.publish(key='key%d'%n,prefix='P%d'%n)
        self.assertEqual(len(list((self.root/'CAE_Results').iterdir())),9)
    def test_input_model_never_replaced(self):
        user=self.root/'PROJECT_final.cae';user.write_bytes(b'USER')
        self.publish();self.assertEqual(user.read_bytes(),b'USER')
    def test_actual_windows_lock(self):
        if os.name!='nt':self.skipTest('Windows only')
        import ctypes
        from ctypes import wintypes
        old=self.publish()
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.CreateFileW(old['path'],0x80000000,1,None,3,0,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(RuntimeError):self.publish(content=b'NEXT')
            self.assertEqual(digest(old['path']),old['sha256'])
        finally:kernel.CloseHandle(handle)
        self.publish(content=b'NEXT')
    def test_migration_requires_explicit_confirmation(self):
        p,plan=plan_migration(self.root)
        with self.assertRaises(ValueError):apply_migration(p,None)
    def test_migration_uses_run_record_not_mtime(self):
        folder=self.root/'CAE_Results';folder.mkdir()
        for n,date in [(1,'2026-01-01T00:00:00+00:00'),(2,'2026-02-01T00:00:00+00:00')]:
            cae=folder/('P_final_%d.cae'%n);cae.write_bytes(str(n).encode())
            record=dict(key='key',prefix='P',ended=date,stages=[{'status':'SUCCESS'}]*9,delivery=dict(path=str(cae),sha256=digest(cae),stage=9,status='PASSED',verification={'status':'PASSED'}))
            run=self.root/'.batchrunner'/str(n);run.mkdir(parents=True)
            (run/'record.json').write_text(json.dumps(record))
        os.utime(folder/'P_final_1.cae',(2000000000,2000000000))
        _,plan=plan_migration(self.root)
        self.assertTrue(plan['selected']['key']['path'].endswith('_2.cae'))

if __name__=='__main__':unittest.main()
