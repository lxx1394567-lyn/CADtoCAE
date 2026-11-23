import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from cadtocae.hole_projects import _row

spec=importlib.util.spec_from_file_location('step06_gui',Path(__file__).resolve().parents[1]/'scripts/step06_hole_setup_gui.py')
gui=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.app=gui.Step06App();self.app.withdraw();self.addCleanup(self.app.destroy)
        self.app.folder.set(str(Path.cwd()))
        row=_row(Path.cwd(),'TEST');row.update(input_status='READY',capability='READY')
        self.row=row
        self.app.scan=dict(source_folder=str(Path.cwd()),include_subfolders=False,projects=[row])
        self.app.table.insert('','end',iid='0',values=self.app.row_values(row));self.app.buttons()

    def test_single_folder_columns_and_defaults(self):
        self.assertFalse(self.app.recursive.get());self.assertFalse(hasattr(self.app,'output'))
        self.assertEqual(len(self.app.table['columns']),7)
        self.assertEqual(str(self.app.all_ready['state']),'normal')
        self.assertEqual(str(self.app.selected['state']),'disabled')

    def test_generate_selected_and_all_dispatch(self):
        self.app.table.selection_set('0');self.app.buttons()
        self.assertEqual(str(self.app.selected['state']),'normal')
        with patch.object(self.app,'run',side_effect=lambda fn:fn()),patch.object(gui,'generate_batch') as generate:
            self.app.start_generate(True)
            self.assertEqual(generate.call_args.args[1],{(str(Path.cwd()),'TEST')})
            self.app.start_generate(False);self.assertIsNone(generate.call_args.args[1])

    def test_needs_review_disabled_and_details_visible(self):
        self.row.update(input_status='NEEDS_REVIEW',capability='NEEDS_REVIEW',first_blocking_reason='Missing support')
        self.app.table.selection_set('0');self.app.details()
        self.assertEqual(str(self.app.all_ready['state']),'disabled')
        self.assertEqual(str(self.app.selected['state']),'disabled')
        self.assertIn('Missing support',self.app.log.get('1.0','end'))

    def test_settings_change_invalidates_scan(self):
        self.app.recursive.set(True);self.assertIsNone(self.app.scan)
        self.assertEqual(self.app.table.get_children(),())

    def test_generate_tables_available_before_dimensions_and_dispatches(self):
        self.row.update(input_status='MISSING_TABLE',capability='NEEDS_REVIEW')
        self.app.buttons()
        self.assertEqual(str(self.app.hole_tables['state']),'normal')
        self.assertEqual(str(self.app.all_ready['state']),'disabled')
        with patch.object(self.app,'run',side_effect=lambda fn:fn()),patch.object(gui,'generate_hole_tables') as generate:
            self.app.start_tables();self.assertEqual(generate.call_args.args[0],self.app.scan)

    def test_busy_prevents_scan_generate_and_folder_changes(self):
        self.app.busy=True;self.app.buttons()
        self.assertTrue(all(str(w['state'])=='disabled' for w in self.app.inputs))
        with patch.object(self.app,'run') as run:
            self.app.start_scan();self.app.start_generate(False);self.app.start_tables();run.assert_not_called()
