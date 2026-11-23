import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cadtocae.step07_desktop import new_run,inspect_summary,load_configuration,abaqus_command
from cadtocae.step07_setup import build_plan

class DesktopTests(unittest.TestCase):
    def fixture(self,root):
        s=dict(project_id='Demo',model_name='Demo',structure_type='SP_SC',instances=[dict(instance_name='Base',part_name='BasePart',canonical_role='COLUMN_DOWN'),dict(instance_name='P1',part_name='P',canonical_role='PURLIN_LOCAL',connection_group='P01')])
        summary=root/'Demo_assembly_summary.json';summary.write_text(json.dumps(s))
        cae=root/'input.cae';cae.write_bytes(b'untouched input')
        c=dict(model_name='Demo',input_cae=str(cae),loads=[dict(instance='P1',force=[0,0,-100])],job=dict(name='DemoJob',submit=True))
        return c,summary
    def test_runs_are_isolated_and_never_autosubmit(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c,s=self.fixture(root)
            a=new_run(c,s,root/'out');b=new_run(c,s,root/'out')
            self.assertNotEqual(a,b)
            for run in (a,b):
                plan=json.loads((run/'step07_plan.json').read_text())
                self.assertFalse(plan['job']['submit'])
                self.assertFalse(plan['enable_column_tie_correction'])
                self.assertNotIn('column_tie',plan)
                self.assertTrue((run/'step07_submit_job.py').is_file())
                self.assertTrue((run/'assembly_summary.json').is_file())
            self.assertTrue(c['job']['submit'])
            self.assertEqual((root/'input.cae').read_bytes(),b'untouched input')
    def test_connection_plan_is_information_not_consent(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c,s=self.fixture(root)
            cp=root/'Demo_analysis_plan.json';cp.write_text(json.dumps(dict(project_id='Demo',column_column_tie=dict(enabled=True,tie='T',members=[]))))
            c['connection_plan']=str(cp)
            run=new_run(c,s,root/'out')
            self.assertNotIn('column_tie',json.loads((run/'step07_plan.json').read_text()))
            c['enable_column_tie_correction']=True
            run=new_run(c,s,root/'out')
            self.assertIn('column_tie',json.loads((run/'step07_plan.json').read_text()))
    def test_summary_roles_and_connection_discovery(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);_,s=self.fixture(root)
            data=inspect_summary(s)
            self.assertEqual(data['bottoms'],['Base']);self.assertEqual(data['purlins'][0]['rp_set'],'STEP06_RP_P01_PURLIN')
    def test_missing_launcher_is_clear(self):
        with self.assertRaisesRegex(ValueError,'ABAQUS'):abaqus_command('Z:/does_not_exist.bat')
    def test_tie_switch_requires_boolean(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c,s=self.fixture(root);c['enable_column_tie_correction']='false'
            with self.assertRaises(ValueError):build_plan(c,json.loads(s.read_text()))

if __name__=='__main__':unittest.main()
