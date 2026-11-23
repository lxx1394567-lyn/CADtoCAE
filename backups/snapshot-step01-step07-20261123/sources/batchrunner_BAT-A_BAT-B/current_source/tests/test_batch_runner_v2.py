import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_batch_runner as helpers
from cadtocae.batch_runner.dependencies import check, values
from cadtocae.batch_runner.scanner import scan, SUFFIXES
from cadtocae.batch_runner.matching import bind_reads
from cadtocae.batch_runner.runner import BatchRunner
from cadtocae.batch_runner.settings import detected_command, save_successful_configuration

class MatchingTests(unittest.TestCase):
    setUp=helpers.BatchTests.setUp
    tearDown=helpers.BatchTests.tearDown
    project=helpers.BatchTests.project

    def stage_source(self, number, source):
        path=self.root/('A'+SUFFIXES[number-1][0])
        path.write_text(source,encoding='utf-8')
        return path

    def checked(self, number):
        return check(scan(self.root)[0]).stages[number-1]

    def test_automatic_literal_json_and_binding(self):
        self.project()
        source="import json\nwith open('A_holes.json') as handle:\n    result=json.load(handle)\n"
        path=self.stage_source(4,source)
        data=self.root/'A_holes.json'
        data.write_text('{"project_id":"A"}')
        stage=self.checked(4)
        self.assertEqual(stage.status,'READY')
        item=next(i for i in stage.inputs if i['role']=='runtime')
        self.assertEqual(Path(item['path']),data)
        bound=bind_reads(source,stage.contract['read_bindings'])
        self.assertIn(item['relative'],bound)
        self.assertEqual(path.read_text(),source)

    def test_missing_hole_and_connector_json(self):
        self.project()
        for number in (4,5):
            with self.subTest(number=number):
                path=self.stage_source(number,"with open('A_required%d.json') as f:\n    data=f.read()\n"%number)
                stage=self.checked(number)
                self.assertEqual(stage.status,'MISSING_INPUT')
                self.assertTrue(any(i.get('expected') for i in stage.inputs))
                path.write_text('# restore fixture')

    def test_wrong_project_json(self):
        self.project()
        self.stage_source(4,"open('A_required.json').read()")
        (self.root/'A_required.json').write_text('{"project_id":"B"}')
        self.assertEqual(self.checked(4).status,'BLOCKED')
        self.assertIn('identity mismatch',str(self.checked(4).reasons))

    def test_multiple_exact_candidates(self):
        self.project()
        self.stage_source(4,"open('A_required.json').read()")
        (self.root/'json').mkdir()
        for folder in (self.root,self.root/'json'):
            (folder/'A_required.json').write_text('{}')
        stage=self.checked(4)
        self.assertEqual(stage.status,'BLOCKED')
        self.assertIn('Multiple exact',str(stage.reasons))

    def test_absolute_variable_path_relocated_and_bound(self):
        self.project()
        source="INPUT = r'C:/obsolete/A_required.json'\nopen(INPUT).read()\n"
        self.stage_source(3,source)
        (self.root/'A_required.json').write_text('{}')
        stage=self.checked(3)
        self.assertEqual(stage.status,'READY')
        bound=bind_reads(source,stage.contract['read_bindings'])
        self.assertNotIn('open(INPUT)',bound)
        self.assertIn('open(\'inputs/',bound)

    def test_directory_expression_and_keyword_file(self):
        self.project()
        source="import os\nINPUT=os.path.join(os.path.dirname(__file__), 'A_required.json')\nopen(file=INPUT, mode='r').read()\n"
        self.stage_source(3,source)
        (self.root/'A_required.json').write_text('{}')
        stage=self.checked(3)
        self.assertEqual(stage.status,'READY')
        self.assertIn("file='inputs/",bind_reads(source,stage.contract['read_bindings']))

    def test_upstream_declared_input_waits_instead_of_missing(self):
        self.project()
        path=self.root/'A_batchrunner.json'
        data=json.loads(path.read_text())
        data['stages']['3']['outputs']=['A_transfer.json']
        data['stages']['4']['inputs']=[{'path':'A_transfer.json','from_stage':3}]
        path.write_text(json.dumps(data))
        self.stage_source(4,"open('A_transfer.json').read()")
        stage=self.checked(4)
        self.assertEqual(stage.status,'READY')
        self.assertEqual(stage.inputs[0]['validation'],'WAITING_UPSTREAM')

    def test_embedded_hole_plan_does_not_require_sidecar(self):
        self.project()
        self.stage_source(4,"import json\nPLAN=json.loads('{\"project_id\":\"A\"}')\n")
        self.assertFalse((self.root/'A_step06_plan.json').exists())
        self.assertEqual(self.checked(4).status,'READY')

    def test_old_report_is_not_automatic_input(self):
        self.project()
        self.stage_source(5,"open('A_step06_hole_report.json').read()")
        (self.root/'A_step06_hole_report.json').write_text('{"status":"SUCCESS"}')
        self.assertEqual(self.checked(5).status,'BLOCKED')

    def test_dynamic_unresolved_read_blocks_before_launch(self):
        self.project()
        self.stage_source(4,"def read_dynamic(path):\n    return open(path).read()\n")
        self.assertEqual(self.checked(4).status,'BLOCKED')

    def test_smart_reuses_and_shows_stale_chain(self):
        self.project()
        executor=helpers.FakeExecutor()
        runner=BatchRunner(self.root,self.output,executor)
        runner.run()
        executor.calls.clear()
        self.assertTrue(all(s.history_status=='SUCCESS' for s in runner.inspect()[0].stages[:5]))
        runner.run()
        self.assertFalse(executor.calls)
        path=self.root/('A'+SUFFIXES[3][0])
        path.write_text('# regenerated')
        stages=runner.inspect()[0].stages
        self.assertEqual([s.history_status for s in stages],['SUCCESS']*3+['STALE']*2+['MISSING']*4)
        runner.run()
        self.assertEqual([n for _,n,_ in executor.calls],[4,5])

    def test_missing_optional_sources_do_not_block_three_stages(self):
        self.project(steps=(1,2,3))
        stages=BatchRunner(self.root,self.output,helpers.FakeExecutor()).inspect()[0].stages
        self.assertEqual([s.status for s in stages],['READY']*3+['MISSING']*6)

    def test_exact_prefix_no_cross_project_selection(self):
        self.project('A')
        self.project('B')
        self.stage_source(4,"open('A_required.json').read()")
        (self.root/'B_required.json').write_text('{"project_id":"B"}')
        self.assertEqual(self.checked(4).status,'MISSING_INPUT')

    def test_settings_saved_only_valid_launcher(self):
        import sys
        target=self.base/'settings.json'
        with patch.dict('os.environ',{'BATCHRUNNER_SETTINGS':str(target)}):
            save_successful_configuration(['not-a-real-command-123'],{})
            self.assertFalse(target.exists())
            save_successful_configuration([sys.executable],{})
            self.assertEqual(detected_command(),[sys.executable])

    def test_external_plan_interface_needs_no_manifest(self):
        self.project()
        manifest=self.root/'A_batchrunner.json'
        config=json.loads(manifest.read_text())
        config['stages'].pop('4')
        manifest.write_text(json.dumps(config))
        self.stage_source(4,"import json\nPLAN=json.load(open('A_step06_plan.json'))\nREPORT_PATH='A_runtime_report.json'\n")
        self.assertEqual(self.checked(4).status,'MISSING_INPUT')
        (self.root/'A_step06_plan.json').write_text('{"project_id":"A"}')
        stage=self.checked(4)
        self.assertEqual(stage.status,'READY')
        self.assertEqual(stage.contract['kind'],'report')

    def test_optional_runtime_absence_and_existence_check_binding(self):
        self.project()
        path=self.root/'A_batchrunner.json'
        config=json.loads(path.read_text())
        config['stages']['4']['inputs']=[{'path':'A_optional.json','required':False}]
        path.write_text(json.dumps(config))
        source="import os\nif os.path.isfile('A_optional.json'):\n    data=open('A_optional.json').read()\n"
        self.stage_source(4,source)
        stage=self.checked(4)
        self.assertEqual(stage.status,'READY')
        self.assertEqual(len(stage.contract['read_bindings']),2)

    def test_excel_present_and_corrupt(self):
        from openpyxl import Workbook
        self.project()
        self.stage_source(4,"from openpyxl import load_workbook\nw=load_workbook('A_material.xlsx')\n")
        self.assertEqual(self.checked(4).status,'MISSING_INPUT')
        path=self.root/'A_material.xlsx'
        book=Workbook();book.save(path);book.close()
        self.assertEqual(self.checked(4).status,'READY')
        path.write_bytes(b'broken workbook')
        self.assertEqual(self.checked(4).status,'BLOCKED')

    def test_gui_folder_selection_autoscans_and_hides_advanced(self):
        import tkinter as tk
        from cadtocae.batch_runner.gui import BatchRunnerGUI
        self.project(steps=(1,2,3))
        with patch.dict('os.environ',{'BATCHRUNNER_SETTINGS':str(self.base/'prefs.json')}):
            root=tk.Tk();root.withdraw()
            try:
                gui=BatchRunnerGUI(root)
                self.assertEqual(gui.mode.get(),'smart')
                self.assertFalse(gui.advanced.grid_info())
                with patch('cadtocae.batch_runner.gui.filedialog.askdirectory',return_value=str(self.root)):
                    gui.choose(gui.source)
                self.assertEqual(gui.output.get(),str(self.root/'.batchrunner'))
                self.assertEqual(len(gui.projects),1)
                self.assertEqual(len(gui.details.get_children()),9)
                self.assertEqual([s.status for s in gui.projects[0].stages],['READY']*3+['MISSING']*6)
            finally:
                root.destroy()

if __name__=='__main__':
    unittest.main()
