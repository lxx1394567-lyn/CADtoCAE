import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('step05_gui',ROOT/'scripts/step05_analysis_script_gui.py')
gui=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.info=self.enterContext(patch.object(gui.messagebox,'showinfo'))
        self.warning=self.enterContext(patch.object(gui.messagebox,'showwarning'))
        self.app=gui.Step05App();self.app.withdraw();self.addCleanup(self.app.destroy)
        self.app.folder.set(str(self.folder))
        self.row=dict(status='READY',input_status='READY',source_folder=str(self.folder),project_id='TEST',
                      structure_type='SP_SC',capability='SP_SC_FULL_CONNECTION_SETUP',generation_status='NOT_GENERATED',
                      supported_rules=[],errors=[])

    def ready(self,generation='NOT_GENERATED'):
        self.row['generation_status']=generation
        self.app.scan=dict(source_folder=str(self.folder),projects=[dict(self.row)])
        self.app.table.insert('','end',iid='0',values=self.app.row_values(self.row))
        self.app.buttons()

    def test_single_folder_and_ready_buttons(self):
        self.assertFalse(hasattr(self.app,'output'));self.assertFalse(hasattr(self.app,'source'))
        self.assertFalse(self.app.recursive.get());self.ready()
        self.assertEqual(str(self.app.all_ready['state']),'normal')
        self.assertEqual(str(self.app.selected['state']),'disabled')
        self.app.table.selection_set('0');self.app.buttons()
        self.assertEqual(str(self.app.selected['state']),'normal')

    def test_mixed_sc_dc_ready_selection(self):
        self.ready()
        dc=dict(self.row,project_id='DC',structure_type='SP_DC',capability='SP_DC_FULL_CONNECTION_SETUP')
        self.app.scan['projects'].append(dc)
        self.app.table.insert('','end',iid='1',values=self.app.row_values(dc))
        self.app.table.selection_set('1');self.app.buttons()
        self.assertEqual(str(self.app.selected['state']),'normal')
        self.assertEqual(self.app.row_values(dc)[3],'FULL')
        with patch.object(gui,'generate_batch') as generate,patch.object(self.app,'run',side_effect=lambda fn:fn()):
            self.app.start_generate(False)
        self.assertEqual(len(generate.call_args.args[0]['projects']),2)

    def test_complete_outputs_can_regenerate(self):
        self.ready('GENERATED');self.assertEqual(str(self.app.all_ready['state']),'normal')

    def test_partial_outputs_can_regenerate(self):
        self.ready('PARTIAL');self.assertEqual(str(self.app.all_ready['state']),'normal')

    def test_incomplete_disables_generate(self):
        self.row['input_status']='INPUT_INCOMPLETE';self.ready()
        self.assertEqual(str(self.app.all_ready['state']),'disabled')

    def test_folder_change_invalidates_scan(self):
        self.ready();self.app.recursive.set(True)
        self.assertIsNone(self.app.scan);self.assertEqual(self.app.table.get_children(),())

    def test_scan_logs_without_generation(self):
        with patch.object(gui,'scan_projects',return_value={}) as scan,patch.object(gui,'generate_batch') as generate,patch.object(self.app,'run',side_effect=lambda fn:fn()):
            self.app.start_scan()
        scan.assert_called_once_with(str(self.folder),False);generate.assert_not_called()
        self.assertIn('Scanning folder:',self.app.log.get('1.0','end'))
        self.assertEqual(list(self.folder.iterdir()),[])

    def test_selected_generation(self):
        self.ready();self.app.table.selection_set('0')
        with patch.object(gui,'generate_batch') as generate,patch.object(self.app,'run',side_effect=lambda fn:fn()):self.app.start_generate(True)
        self.assertEqual(generate.call_args.args[1],{(str(self.folder),'TEST')})
        self.assertIn('Generate Selected:',self.app.log.get('1.0','end'))

    def test_all_generation(self):
        self.ready()
        with patch.object(gui,'generate_batch') as generate,patch.object(self.app,'run',side_effect=lambda fn:fn()):self.app.start_generate(False)
        self.assertIsNone(generate.call_args.args[1])

    def test_live_row_log_and_completion(self):
        self.ready();self.app.operation='generate';self.app.busy=True
        row=dict(self.row,generation_status='GENERATED',result='Success')
        self.app.events.put(('progress',dict(event='finished',row=row,index=1,total=1)))
        self.app.poll()
        self.assertEqual(self.app.table.item('0')['values'][4],'GENERATED')
        self.assertIn('AnalysisPlan generated',self.app.log.get('1.0','end'))
        self.app.events.put(('done',dict(self.app.scan,generation_counts={'succeeded':1,'failed':0})))
        self.app.poll()
        self.assertIn('Succeeded: 1\nFailed: 0',self.app.log.get('1.0','end'))
        self.assertEqual(str(self.app.all_ready['state']),'normal')
        self.app.details();self.assertIn('AnalysisPlan generated',self.app.log.get('1.0','end'))

    def test_ready_requires_full_capability(self):
        self.row['capability']=None;self.ready()
        self.assertEqual(str(self.app.all_ready['state']),'disabled')

    def test_scan_completion_immediately_enables_generate(self):
        self.app.operation='scan';self.app.busy=True
        self.app.events.put(('done',dict(source_folder=str(self.folder),projects=[self.row])))
        self.app.poll()
        self.assertEqual(str(self.app.all_ready['state']),'normal')
        self.app.table.selection_set('0');self.app.details()
        self.assertEqual(str(self.app.selected['state']),'normal')

    def test_completion_success_message(self):
        self.app.show_completion({'succeeded':3,'failed':0})
        self.info.assert_called_once()
        self.assertIn('Succeeded: 3',self.info.call_args.args[1])
        self.assertIn(str(self.folder),self.info.call_args.args[1])
        self.warning.assert_not_called()

    def test_failure_row_reason_traceback_and_message(self):
        self.ready();self.app.operation='generate';self.app.busy=True
        row=dict(self.row,generation_status='FAILED',result='Failed: Missing HOOP group',errors=['Missing HOOP group'],traceback='TRACEBACK_FULL')
        self.app.events.put(('progress',dict(event='finished',row=row,index=1,total=1)))
        self.app.events.put(('done',dict(self.app.scan,projects=[row],generation_counts={'succeeded':0,'failed':1})))
        self.app.poll()
        self.assertEqual(self.app.table.item('0')['values'][4],'FAILED')
        self.assertIn('Missing HOOP group',self.app.table.item('0')['values'][5])
        self.assertIn('TRACEBACK_FULL',self.app.log.get('1.0','end'))
        self.warning.assert_called_once();self.assertIn('Failed: 1',self.warning.call_args.args[1])
        self.assertIn('See log',self.warning.call_args.args[1])

    def test_compact_table(self):
        self.ready()
        values=self.app.row_values(self.row)
        self.assertEqual(values[3],'FULL')
        self.assertNotIn('BEAM_BRACE_TIE',str(values))

    def test_review_details_and_skipped_log(self):
        self.row.update(status='NEEDS_REVIEW',input_status='NEEDS_REVIEW',capability='NEEDS_REVIEW',
            supported_rules=['BEAM_BRACE_TIE','COLUMN_BEAM_TIE','COLUMN_HOOP_TIE'],
            geometry_review=[{}],expected_nominal_tie_count=10,first_blocking_reason='HOOP_03 axial band exceeds COLUMN_DOWN range.',
            warnings=['COLUMN_DOWN: 0.000-2.000 m; HOOP_03: 1.960-2.040 m; Actual overlap: 1.960-2.000 m; Overlap length: 0.040 m'],
            missing_requirements=dict(files=[],roles=[],points=[],hoop_groups=[]))
        self.ready();self.app.table.selection_set('0');self.app.details()
        log=self.app.log.get('1.0','end')
        for text in ('Status: NEEDS_REVIEW','Supported Rules:','Missing Requirements:','Warnings:',
                     'First Blocking Reason: HOOP_03','Expected nominal Tie count: 10','Executable Tie count: not confirmed','0.040 m'):
            self.assertIn(text,log)
        self.assertEqual(str(self.app.selected['state']),'disabled')
        row=dict(self.row,skip_reason='geometry review required: HOOP_03')
        self.app.events.put(('progress',dict(event='skipped',row=row,index=0,total=1)))
        self.app.poll();self.assertIn('TEST skipped: geometry review required',self.app.log.get('1.0','end'))
        self.assertNotIn('FAILED:',self.app.log.get('1.0','end'))

    def test_missing_requirements_in_details_when_errors_empty(self):
        row=dict(self.row,missing_requirements=dict(hoop_groups=['HOOP_01 component mismatch']),warnings=[])
        self.assertIn('First Blocking Reason: hoop_groups: HOOP_01 component mismatch',self.app.project_details(row))

    def test_ready_details_include_expected_ties(self):
        row=dict(self.row,expected_tie_count=10)
        self.assertIn('Expected Tie count: 10',self.app.project_details(row))
