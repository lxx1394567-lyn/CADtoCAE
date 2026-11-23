import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_batch_runner as helpers
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.scanner import SUFFIXES
from cadtocae.batch_runner.publication import publish, store, registry
from cadtocae.batch_runner.executor import digest
from cadtocae.batch_runner.state import write_json

class ChangeTests(unittest.TestCase):
    setUp=helpers.BatchTests.setUp
    tearDown=helpers.BatchTests.tearDown
    project=helpers.BatchTests.project
    def run_project(self, executor=None):
        exe=executor or helpers.FakeExecutor()
        runner=BatchRunner(self.root,self.output,exe)
        _,rows=runner.run('smart')
        return exe,rows
    def test_each_changed_stage_and_missing_step5(self):
        self.project(steps=(1,2,3,4));self.run_project()
        for number in (1,2,3,4):
            with self.subTest(stage=number):
                path=self.root/('A'+SUFFIXES[number-1][0]);path.write_text(path.read_text()+'\n# changed%d\n'%number)
                exe,rows=self.run_project()
                self.assertEqual([c[1] for c in exe.calls],list(range(number,5)))
                self.assertEqual(rows[0]['stages'][number-1]['action'],'RERUN')
                self.assertEqual(rows[0]['stages'][4]['status'],'MISSING')
                self.assertEqual(rows[0]['execution_result'],'PARTIAL_SUCCESS')
                if number>1:self.assertIn('step%d'%(number-1),exe.calls[0][2])
        exe,rows=self.run_project();self.assertFalse(exe.calls)
        self.assertEqual([s.get('action') for s in rows[0]['stages'][:4]],['REUSED']*4)
    def test_same_size_and_timestamp_and_cached_scan(self):
        self.project(steps=(1,2,3,4));self.run_project()
        exe=helpers.FakeExecutor();runner=BatchRunner(self.root,self.output,exe)
        runner.inspect()
        path=self.root/('A'+SUFFIXES[1][0]);stat=path.stat()
        path.write_bytes(path.read_bytes().replace(b'simulation',b'alteration'))
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size,stat.st_size)
        self.assertEqual([s.plan_action for s in runner.inspect()[0].stages[:4]],['REUSED','RERUN','RERUN','RERUN'])
        runner.run('smart');self.assertEqual([c[1] for c in exe.calls],[2,3,4])
    def test_actual_json_excel_contract_input_changes(self):
        self.project(steps=(1,2,3,4))
        manifest=self.root/'A_batchrunner.json';d=json.loads(manifest.read_text())
        for number,name in [(2,'A_input.json'),(3,'A_input.xlsx')]:
            (self.root/name).write_bytes(b'static-v1')
            d['stages'][str(number)]['inputs']=[{'path':name}]
        manifest.write_text(json.dumps(d));self.run_project()
        for number,name in [(2,'A_input.json'),(3,'A_input.xlsx')]:
            (self.root/name).write_bytes(b'static-v2')
            exe,_=self.run_project();self.assertEqual([c[1] for c in exe.calls],list(range(number,5)))
    def test_generation_and_report_changes_not_runtime_inputs(self):
        self.project(steps=(1,2,3,4));self.run_project()
        for name in ('A_components.xlsx','A_assembly_summary.json','A_analysis_setup_report.json'):
            (self.root/name).write_text('not consumed by this fixture')
        exe,_=self.run_project();self.assertFalse(exe.calls)
    def test_missing_predecessor_and_old_execution_copy(self):
        self.project(steps=(1,2,3,4));_,rows=self.run_project()
        old=Path(rows[0]['stages'][1]['checkpoint']);old.with_name('stage.py').write_text('# old cached script')
        old.unlink();exe,_=self.run_project();self.assertEqual([c[1] for c in exe.calls],[2,3,4])
    def test_nine_project_independent_changes(self):
        for n in range(9):self.project('P%d'%n,steps=(1,2,3,4))
        self.run_project()
        path=self.root/('P4'+SUFFIXES[2][0]);path.write_text('# changed')
        exe,_=self.run_project();self.assertEqual([(x[0],x[1]) for x in exe.calls],[('P4',3),('P4',4)])
    def test_failed_rerun_no_delivery_or_downstream(self):
        self.project(steps=(1,2,3,4));self.run_project()
        path=self.root/('A'+SUFFIXES[1][0]);path.write_text('# changed')
        exe,rows=self.run_project(helpers.FakeExecutor(fail=2))
        self.assertEqual([x[1] for x in exe.calls],[2])
        self.assertEqual(rows[0]['result'],'FAILED')
        self.assertIsNone(rows[0]['delivery']['path'])
    def test_changed_external_managed_file_pending_recovered(self):
        key='test';target=self.root/'CAE_Results/A_step04.cae';target.parent.mkdir()
        target.write_bytes(b'externally changed')
        base=store(self.root,key);archive=base/'archive/old';archive.mkdir(parents=True)
        prior=dict(path=str(target),sha256='old',stage=4,status='PASSED')
        write_json(base/'current.json',dict(partial=prior))
        write_json(base/'pending.json',dict(delivery=dict(prior,sha256='pending'),old_sha256='old',archive=str(archive)))
        candidate=base/'new.cae';candidate.write_bytes(b'new validated model')
        result=dict(prior,sha256=digest(candidate))
        publish(self.root,key,result,candidate)
        self.assertEqual(target.read_bytes(),b'new validated model')
        self.assertTrue(any(p.read_bytes()==b'externally changed' for p in base.rglob('A_step04.cae')))
        self.assertEqual(registry(self.root,key)['partial']['sha256'],result['sha256'])

if __name__=='__main__':unittest.main()
