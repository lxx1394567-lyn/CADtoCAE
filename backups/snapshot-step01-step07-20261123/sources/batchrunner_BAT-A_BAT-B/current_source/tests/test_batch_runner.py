import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ast
from cadtocae.batch_runner import cae_worker_source
from cadtocae.batch_runner.scanner import scan, SUFFIXES
from cadtocae.batch_runner.dependencies import check
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.executor import AbaqusExecutor, adapt

class FakeExecutor:
    kind = 'simulation'
    identity = {'kind': 'simulation'}
    def __init__(self, fail=None, callback=None, missing=False):
        self.calls = []
        self.fail = fail
        self.callback = callback
        self.missing = missing
    def execute(self, project, stage, directory, previous):
        self.calls.append((project.prefix, stage.number, previous))
        if stage.number > 1:
            assert previous and Path(previous).is_file()
        if self.fail == stage.number:
            raise RuntimeError('SIMULATED abnormal Abaqus exit')
        checkpoint = directory/'checkpoint.cae'
        if not self.missing:
            checkpoint.write_bytes(b'SIMULATION ONLY - NOT AN ABAQUS DATABASE')
        if self.callback:
            self.callback(stage)
        return dict(checkpoint=str(checkpoint), returncode=0, evidence={'status': 'SUCCESS', 'simulation': True})

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='batch 中文 空格 ')
        self.base = Path(self.temp.name)
        self.root = self.base/'projects'
        self.root.mkdir()
        self.output = self.base/'runs'
    def tearDown(self):
        self.temp.cleanup()
    def project(self, prefix='A', steps=(1,2,3,4,5), folder=None):
        folder = folder or self.root
        folder.mkdir(parents=True, exist_ok=True)
        manifest = {'project': prefix, 'stages': {}}
        for i in steps:
            (folder/(prefix+SUFFIXES[i-1][0])).write_text('# simulation fixture\n', encoding='utf-8')
            manifest['stages'][str(i)] = {'validation': {'parts': ['P_TEST']}}
        (folder/(prefix+'_batchrunner.json')).write_text(json.dumps(manifest), encoding='utf-8')
        return folder
    def run_batch(self, executor=None, mode='full', start=1):
        executor = executor or FakeExecutor()
        runner = BatchRunner(self.root, self.output, executor)
        directory, records = runner.run(mode, start)
        return executor, records
    def statuses(self, records):
        # Legacy fixtures exercise the first five positions; V4 tests cover all nine.
        return [s['status'] for s in records[0]['stages'][:5]]
    def test_all_five(self):
        self.project()
        exe, records = self.run_batch()
        self.assertEqual(len(exe.calls), 5)
        self.assertEqual(records[0]['execution_result'], 'PARTIAL_SUCCESS')
        self.assertEqual(records[0]['result'], 'NOT_VERIFIED')
    def test_nine_projects_shared_directory_and_suffixes(self):
        for i in range(9):
            self.project('P%d' % i)
        exe, records = self.run_batch()
        self.assertEqual(len(records), 9)
        self.assertEqual(len(exe.calls), 45)
        self.assertEqual([c[1] for c in exe.calls], [1,2,3,4,5]*9)
    def test_partial_two_and_three(self):
        for count in (2,3):
            with self.subTest(count=count):
                self.project(steps=range(1,count+1))
                exe, records = self.run_batch()
                self.assertEqual(records[0]['execution_result'], 'PARTIAL_SUCCESS')
                self.assertEqual(records[0]['delivery']['status'], 'NOT_VERIFIED')
                self.assertEqual(self.statuses(records), ['SUCCESS']*count + ['MISSING']*(5-count))
    def test_gap(self):
        self.project(steps=(1,2,4,5))
        exe, records = self.run_batch()
        self.assertEqual(self.statuses(records), ['SUCCESS','SUCCESS','MISSING','BLOCKED','BLOCKED'])
    def test_no_first(self):
        self.project(steps=(2,3,4,5))
        exe, records = self.run_batch()
        self.assertFalse(exe.calls)
        self.assertEqual(self.statuses(records), ['MISSING']+['BLOCKED']*4)
    def test_missing_runtime_json_and_excel(self):
        self.project()
        manifest_path = self.root/'A_batchrunner.json'
        config = json.loads(manifest_path.read_text())
        for name in ('A_input.json', 'A_material.xlsx'):
            with self.subTest(name=name):
                config['stages']['3']['inputs'] = [{'path': name}]
                manifest_path.write_text(json.dumps(config))
                exe, records = self.run_batch()
                self.assertEqual(self.statuses(records), ['SUCCESS']*2 + ['MISSING_INPUT','BLOCKED','BLOCKED'])
                self.assertIn(name, str(records[0]['stages'][2]['reasons']))
    def test_third_failure(self):
        self.project()
        exe, records = self.run_batch(FakeExecutor(fail=3))
        self.assertEqual(self.statuses(records), ['SUCCESS','SUCCESS','FAILED','BLOCKED','BLOCKED'])
    def test_stage_four_change_rerun(self):
        self.project()
        self.run_batch()
        with (self.root/('A'+SUFFIXES[3][0])).open('a') as handle:
            handle.write('# changed\n')
        exe, records = self.run_batch(mode='from', start=4)
        self.assertEqual([c[1] for c in exe.calls], [4,5])
        self.assertIn('step3', exe.calls[0][2])
        self.assertEqual(records[0]['stages'][3]['history_status'], 'STALE')
    def test_upstream_input_invalidates_all(self):
        self.project()
        source = self.root/'A_components.xlsx'
        source.write_bytes(b'v1')
        manifest_path = self.root/'A_batchrunner.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['stages']['1']['inputs'] = [{'path':'A_components.xlsx'}]
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        self.run_batch()
        source.write_bytes(b'v2')
        exe, records = self.run_batch(mode='resume')
        self.assertEqual(len(exe.calls), 5)
        self.assertEqual(records[0]['stages'][0]['history_status'], 'STALE')
    def test_missing_checkpoint(self):
        self.project()
        _, records = self.run_batch()
        Path(records[0]['stages'][1]['checkpoint']).unlink()
        exe, records = self.run_batch(mode='resume')
        self.assertEqual([c[1] for c in exe.calls], [2,3,4,5])
    def test_stop_boundary(self):
        self.project()
        self.project('B')
        exe = FakeExecutor()
        runner = BatchRunner(self.root, self.output, exe)
        exe.callback = lambda stage: runner.stop.set()
        _, records = runner.run()
        self.assertEqual(len(exe.calls), 1)
        self.assertEqual(records[0]['stages'][1]['status'], 'SKIPPED')
        self.assertEqual(records[1]['stages'][0]['status'], 'SKIPPED')
    def test_append_steps(self):
        self.project(steps=(1,2,3))
        self.run_batch()
        # Only scripts are supplemented: existing config must remain byte-identical.
        for i in (4,5):
            (self.root/('A'+SUFFIXES[i-1][0])).write_text("import json\nPLAN = json.loads('{\"project_id\":\"A\"}')\n")
        exe, records = self.run_batch(mode='resume')
        self.assertEqual([c[1] for c in exe.calls], [4,5])
    def test_duplicate_prefix_directories_and_alias(self):
        self.project(folder=self.root/'a')
        self.project(folder=self.root/'b')
        self.assertTrue(all(p.conflicts for p in scan(self.root)))
        (self.root/'a'/'A_step06_connector_setup.py').write_text('# ignored legacy Connector')
        exe, records = self.run_batch()
        self.assertFalse(exe.calls)
    def test_unknown_script_blocked(self):
        (self.root/('A'+SUFFIXES[0][0])).write_text('print(1)')
        exe, records = self.run_batch()
        self.assertEqual(self.statuses(records)[0], 'BLOCKED')
    def test_missing_receipt_or_checkpoint_not_success(self):
        self.project()
        _, records = self.run_batch(FakeExecutor(missing=True))
        self.assertEqual(self.statuses(records)[0], 'FAILED')
    def test_from_without_checkpoint(self):
        self.project()
        exe, records = self.run_batch(mode='from', start=4)
        self.assertFalse(exe.calls)
    def test_history_tamper(self):
        self.project()
        _, records = self.run_batch()
        Path(records[0]['stages'][0]['checkpoint']).write_bytes(b'corrupt')
        exe, records = self.run_batch(mode='resume')
        self.assertEqual(len(exe.calls), 5)
    def test_source_changed_mid_execution(self):
        self.project()
        script = self.root/('A'+SUFFIXES[0][0])
        exe = FakeExecutor(callback=lambda _: script.write_text('# changed'))
        _, records = self.run_batch(exe)
        self.assertEqual(self.statuses(records)[0], 'FAILED')
    def test_project_selection(self):
        self.project()
        self.project('B')
        exe = FakeExecutor()
        runner = BatchRunner(self.root, self.output, exe)
        _, records = runner.run(selected=[runner.inspect()[0].key])
        self.assertEqual(len(exe.calls), 5)
        self.assertEqual(records[1]['result'], 'SKIPPED')
    def test_continue_after_failure(self):
        self.project()
        self.project('B')
        exe, records = self.run_batch(FakeExecutor(fail=3))
        self.assertEqual(len(exe.calls), 6)
    def test_output_excluded_from_scan(self):
        self.project()
        output = self.root/'.batchrunner'
        self.project('COPY', folder=output)
        self.assertEqual(len(BatchRunner(self.root, output, FakeExecutor()).inspect()), 1)
    def test_source_output_assignments_adapted_only_in_copy(self):
        source = "REPORT_PATH = '/original/report.json'\nSAVE_AS_PATH = '/original/model.cae'\ncreate_parts()\n"
        adapted = adapt(source)
        self.assertIn("REPORT_PATH = 'runtime_report.json'", adapted)
        self.assertIn('_batch_parts_result = create_parts()', adapted)
        self.assertIn('/original/report.json', source)
    def test_no_external_input_traversal(self):
        self.project()
        path = self.root/'A_batchrunner.json'
        config = json.loads(path.read_text())
        config['stages']['1']['inputs'] = [{'path':'../secret.xlsx'}]
        path.write_text(json.dumps(config))
        exe, records = self.run_batch()
        self.assertFalse(exe.calls)

    def test_failed_forced_replay_retires_previous_success(self):
        self.project()
        self.run_batch()
        self.run_batch(FakeExecutor(fail=3), mode='from', start=3)
        exe, records = self.run_batch(mode='resume')
        self.assertEqual([c[1] for c in exe.calls], [3,4,5])

    def test_upstream_output_missing_is_blocked(self):
        self.project()
        path = self.root/'A_batchrunner.json'
        config = json.loads(path.read_text())
        config['stages']['1']['outputs'] = ['A_transfer.json']
        config['stages']['2']['inputs'] = [{'path':'A_transfer.json', 'from_stage':1}]
        path.write_text(json.dumps(config))
        exe, records = self.run_batch()
        self.assertEqual(self.statuses(records), ['SUCCESS']+['BLOCKED']*4)
        self.assertIn('Missing upstream outputs', str(records[0]['stages'][1]['reasons']))

    def test_undeclared_upstream_output_blocked(self):
        self.project()
        path = self.root/'A_batchrunner.json'
        config = json.loads(path.read_text())
        config['stages']['2']['inputs'] = [{'path':'A_transfer.json', 'from_stage':1}]
        path.write_text(json.dumps(config))
        exe, records = self.run_batch()
        self.assertEqual([c[1] for c in exe.calls], [1])

    def test_nonzero_process_and_zero_without_receipt_fail(self):
        self.project(steps=(1,))
        project = check(scan(self.root)[0])
        for code in (17, 0):
            directory = self.base/str(code)
            directory.mkdir()
            with patch('cadtocae.batch_runner.executor.subprocess.Popen') as process:
                process.return_value.wait.return_value = code
                with self.assertRaises(RuntimeError):
                    AbaqusExecutor(['abaqus']).execute(project, project.stages[0], directory, None)
                self.assertEqual(json.loads((directory/'process.json').read_text())['returncode'], code)

    def test_receipt_wrong_token_rejected(self):
        self.project(steps=(1,))
        project = check(scan(self.root)[0])
        directory = self.base/'execute'
        directory.mkdir()
        (directory/'receipt.json').write_text(json.dumps({'token':'old', 'status':'SUCCESS', 'model':'A'}))
        with patch('cadtocae.batch_runner.executor.subprocess.Popen') as process:
            process.return_value.wait.return_value = 0
            with self.assertRaisesRegex(RuntimeError, 'identity/status'):
                AbaqusExecutor(['abaqus'])._execute(project, project.stages[0], directory, None)

    def test_nested_runtime_errors_detected(self):
        tree = ast.parse(cae_worker_source())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'report_errors')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<report-validator>', 'exec'), namespace)
        with self.assertRaises(RuntimeError):
            namespace['report_errors']({'validation':{'column':{'errors':['anchor mismatch']}}})
        namespace['report_errors']({'warnings':['review'], 'errors':[]})

    def test_hardcoded_original_cae_write_is_blocked(self):
        self.project(steps=(1,))
        (self.root/('A'+SUFFIXES[0][0])).write_text("mdb.saveAs(pathName='C:/original.cae')")
        exe, records = self.run_batch()
        self.assertFalse(exe.calls)

    def test_current_step05_report_alias_redirected(self):
        source = "REPORT = 'C:/user/original_analysis_report.json'\n"
        self.assertEqual(adapt(source), "REPORT = 'runtime_report.json'\n")

    def test_legacy_connector_is_not_a_stage(self):
        self.project(steps=(1,2,3,4))
        script = self.root/'A_step06_connector_setup.py'
        script.write_text('raise RuntimeError("MUST NOT EXECUTE")')
        original = script.read_bytes()
        exe, records = self.run_batch()
        self.assertEqual([n for _,n,_ in exe.calls], [1,2,3,4])
        self.assertEqual(records[0]['execution_result'], 'PARTIAL_SUCCESS')
        self.assertEqual([r['status'] for r in records[0]['stages'][4:]], ['MISSING']*5)
        self.assertEqual(script.read_bytes(), original)

if __name__ == '__main__':
    unittest.main()
