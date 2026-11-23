import copy
import json
import tempfile
import unittest
from pathlib import Path
from cadtocae.step07_setup import build_plan, generate

class Step07Tests(unittest.TestCase):
    def setUp(self):
        self.summary=dict(model_name='MODEL',structure_type='SP_SC',instances=[dict(instance_name='P1',canonical_role='PURLIN_LOCAL',connection_group='P01',part_name='PART')])
        self.config=dict(model_name='MODEL',loads=[dict(instance='P1',force=[0,0,-100])])
    def test_defaults_and_no_input_mutation(self):
        original=copy.deepcopy(self.config)
        p=build_plan(self.config,self.summary)
        self.assertEqual(p['loads'][0]['rp_set'],'STEP06_RP_P01_PURLIN')
        self.assertFalse(p['job']['submit'])
        self.assertEqual(original,self.config)
    def test_reject_invalid_analysis_settings(self):
        for settings in ({'mesh':{'size':0}},{'step':{'initialInc':.2,'maxInc':.1}},{'step':{'nlgeom':'OFF'}},{'job':{'submit':'false'}},{'job':{'name':'../bad'}},{'units':'mm-N-MPa'}):
            c=copy.deepcopy(self.config);c.update(settings)
            with self.subTest(settings=settings),self.assertRaises(ValueError):build_plan(c,self.summary)
    def test_force_and_target_fail_closed(self):
        for load in (dict(instance='P1',force=[0,0,0]),dict(instance='P1',force=[0,float('nan'),1]),dict(instance='column',force=[0,0,1]),dict(instance='P1',force=[0,True,1])):
            c=copy.deepcopy(self.config);c['loads']=[load]
            with self.subTest(load=load),self.assertRaises(ValueError):build_plan(c,self.summary)
    def test_duplicate_and_identity_rejected(self):
        c=copy.deepcopy(self.config);c['loads']*=2
        with self.assertRaises(ValueError):build_plan(c,self.summary)
        c=copy.deepcopy(self.config);c['model_name']='other'
        with self.assertRaises(ValueError):build_plan(c,self.summary)
    def test_completion_requires_solver_and_matching_job(self):
        from cadtocae.step07_runtime import s7_completion_evidence
        sta='THE ANALYSIS HAS COMPLETED SUCCESSFULLY'
        self.assertTrue(s7_completion_evidence(sta,'Abaqus JOB Demo COMPLETED','Demo'))
        self.assertTrue(s7_completion_evidence(sta,'Abaqus/Analysis completed successfully','Demo'))
        self.assertFalse(s7_completion_evidence('THE ANALYSIS HAS NOT BEEN COMPLETED','Abaqus JOB Demo COMPLETED','Demo'))
        self.assertFalse(s7_completion_evidence(sta,'Abaqus JOB Other COMPLETED','Demo'))

    def test_assumption_requires_explicit_boolean(self):
        c=copy.deepcopy(self.config)
        p=build_plan(c,self.summary)
        self.assertFalse(p['validation_assumptions'].get('fix_purlin_rp_rotations',False))
        c['validation_assumptions']={'fix_purlin_rp_rotations':'false'}
        with self.assertRaises(ValueError):build_plan(c,self.summary)

    def test_solver_diagnostics_refuse_false_success(self):
        import os
        from cadtocae.step07_runtime import s7_solver_diagnostics
        old=os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as t:
                os.chdir(t)
                Path('test.dat').write_text('***WARNING: sample')
                Path('test.msg').write_text('NUMERICAL SINGULARITY')
                report={}
                with self.assertRaises(ValueError):s7_solver_diagnostics({'job':{'name':'test'}},report)
                self.assertEqual(report['solver_diagnostics']['msg']['singularities'],1)
                Path('test.msg').write_text('complete')
                s7_solver_diagnostics({'job':{'name':'test'}},{})
                os.chdir(old)
        finally:os.chdir(old)

    def test_generator_paths_runtime_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'source.cae').write_bytes(b'test')
            c=copy.deepcopy(self.config);c['input_cae']='source.cae'
            (root/'config.json').write_text(json.dumps(c))
            (root/'summary.json').write_text(json.dumps(self.summary))
            p=generate(root/'config.json',root/'summary.json',root/'run')
            compile(p.read_text(),'generated','exec')
            verifier=(root/'run/step07_verify_results.py').read_text()
            self.assertIn('verify_saved_step07(STEP07_PLAN)',verifier)
            compile(verifier,'verifier','exec')
            plan=json.loads((root/'run/step07_plan.json').read_text())
            self.assertEqual(Path(plan['input_cae']),root/'source.cae')
            with self.assertRaises(ValueError):generate(root/'config.json',root/'summary.json',root/'run')
            self.assertEqual((root/'source.cae').read_bytes(),b'test')

if __name__=='__main__':unittest.main()
