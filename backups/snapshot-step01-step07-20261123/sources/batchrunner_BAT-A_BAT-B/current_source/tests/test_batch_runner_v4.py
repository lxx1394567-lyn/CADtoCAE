import json
import os
from pathlib import Path
import tempfile
import unittest
from test_batch_runner import FakeExecutor
from cadtocae.batch_runner.scanner import SUFFIXES, scan
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.step07_adapter import adapt_inplace


class NineStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executor = FakeExecutor()
        self.runner = BatchRunner(self.root, self.root/'.batchrunner', self.executor)

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, prefix='A', numbers=range(1,10)):
        stages = {}
        for n in numbers:
            (self.root/(prefix+SUFFIXES[n-1][0])).write_text('# current model script\n')
            stages[str(n)] = {'validation': {'parts': ['P_TEST']}}
        (self.root/(prefix+'_batchrunner.json')).write_text(json.dumps({'project':prefix,'stages':stages}))
        (self.root/(prefix+'_step06_connector_setup.py')).write_text('raise RuntimeError("MUST NOT RUN")')

    def run_project(self):
        return self.runner.run()[1][0]

    def test_nine_and_reuse(self):
        self.project()
        self.assertEqual(self.run_project()['execution_result'],'SUCCESS')
        self.assertEqual([x[1] for x in self.executor.calls],list(range(1,10)))
        self.executor.calls.clear()
        self.assertTrue(all(x['action']=='REUSED' for x in self.run_project()['stages']))
        self.assertFalse(self.executor.calls)

    def test_changes_at_every_stage_and_retained_timestamp(self):
        self.project();self.run_project()
        for n in range(1,10):
            self.executor.calls.clear()
            path=self.root/('A'+SUFFIXES[n-1][0]);st=path.stat()
            path.write_text(path.read_text().replace('current','changed'))
            os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns))
            self.run_project()
            self.assertEqual([x[1] for x in self.executor.calls],list(range(n,10)))

    def test_partial_and_gap(self):
        self.project(numbers=range(1,5))
        r=self.run_project()
        self.assertEqual(r['execution_result'],'PARTIAL_SUCCESS')
        self.assertEqual([s['status'] for s in r['stages'][4:]],['MISSING']*5)
        self.project(numbers=(1,2,3,4,5,7,8,9))
        r=self.run_project()
        self.assertEqual(r['stages'][5]['status'],'MISSING')
        self.assertEqual([s['status'] for s in r['stages'][6:]],['BLOCKED']*3)

    def test_missing_checkpoint_and_failure(self):
        self.project();r=self.run_project()
        Path(r['stages'][3]['checkpoint']).unlink();self.executor.calls.clear()
        self.executor.fail=6;r=self.run_project()
        self.assertEqual([x[1] for x in self.executor.calls],[4,5,6])
        self.assertEqual([s['status'] for s in r['stages'][6:]],['BLOCKED']*3)
        self.assertFalse(r['delivery'].get('published'))

    def test_nine_projects_independent(self):
        for i in range(9):self.project('P%d'%i)
        self.runner.run();self.executor.calls.clear()
        f=self.root/('P3'+SUFFIXES[7][0]);f.write_text('# updated mesh')
        self.runner.run()
        self.assertEqual([(p,n) for p,n,_ in self.executor.calls],[('P3',8),('P3',9)])

    def test_legacy_workflow_and_internal_copies(self):
        self.project();r=self.run_project()
        key=r['key'];path=self.root/'.batchrunner/history'/(key+'.json')
        d=json.loads(path.read_text());d['stages']['5']['fingerprint']='legacy-connector';path.write_text(json.dumps(d))
        history=self.root/'过程文件';history.mkdir()
        (history/('A'+SUFFIXES[4][0])).write_text('# old')
        self.assertEqual(len(scan(self.root)),1)
        self.executor.calls.clear();self.run_project()
        self.assertEqual([x[1] for x in self.executor.calls],list(range(5,10)))

    def test_adapter_preserves_runtime_and_captures_result(self):
        source='import json, os\ndef u7_run(c): return c\nINPLACE_PLAN=json.loads("{}")\nif __name__ == "__main__":\n    u7_run(INPLACE_PLAN)\n'
        result=adapt_inplace(source)
        compile(result,'stage.py','exec')
        self.assertIn('def u7_run(c): return c',result)
        self.assertIn('_batch_step07_result = u7_run(INPLACE_PLAN)',result)
        self.assertIn('upstream_hole_report.json',result)

    def test_load_json_identity_hash_and_missing(self):
        from cadtocae.batch_runner.scanner import Project, Stage
        from cadtocae.batch_runner.step07_adapter import inspect_plan
        from cadtocae.batch_runner.executor import digest
        p=Project('A',str(self.root));path=self.root/'A_J13_step07_loads.json'
        plan=dict(schema='step07-inplace-1',execution_mode='CURRENT_MDB_IN_PLACE',stage=5,
                  project_id='A',model_name='A',assembly_summary=dict(project_id='A',model_name='A',instances=[]),
                  load_config_path=str(path),load_config_sha256='missing')
        def stage():return Stage(9,str(self.root/'A_step07_05_load_setup.py'))
        _,missing=inspect_plan(p,stage(),plan);self.assertTrue(missing)
        path.write_text('{"project_id":"B"}')
        with self.assertRaisesRegex(ValueError,'identity mismatch'):inspect_plan(p,stage(),plan)
        path.write_text('{"project_id":"A"}')
        with self.assertRaisesRegex(ValueError,'regenerate'):inspect_plan(p,stage(),plan)
        plan['load_config_sha256']=digest(path)
        s=stage();_,missing=inspect_plan(p,s,plan)
        self.assertFalse(missing)
        self.assertEqual(s.inputs[0]['from_stage'],4)
        self.assertEqual(s.inputs[1]['path'],str(path))

    def test_review_required_never_delivers_or_runs_load(self):
        self.project()
        class Review(FakeExecutor):
            def execute(inner, project, stage, directory, previous):
                if stage.number==8:raise RuntimeError('REVIEW_REQUIRED: mesh warnings')
                return super(Review,inner).execute(project,stage,directory,previous)
        executor=Review();r=BatchRunner(self.root,self.root/'.batchrunner',executor).run()[1][0]
        self.assertEqual(r['stages'][7]['status'],'REVIEW_REQUIRED')
        self.assertEqual(r['stages'][8]['status'],'BLOCKED')
        self.assertEqual(r['execution_result'],'REVIEW_REQUIRED')
        self.assertFalse(r['delivery'].get('published'))


if __name__=='__main__':unittest.main()
