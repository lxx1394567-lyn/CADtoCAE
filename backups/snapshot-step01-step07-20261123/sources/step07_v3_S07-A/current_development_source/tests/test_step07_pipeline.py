import json,tempfile,unittest,hashlib
from pathlib import Path
from cadtocae.step07_pipeline import generate_pipeline
class PipelineTests(unittest.TestCase):
 def setup_files(self,td):
  root=Path(td);s=root/'summary.json';s.write_text(json.dumps(dict(project_id='DP_EXACT_ID',model_name='DP_EXACT_ID')))
  c=root/'holes.cae';c.write_bytes(b'CAE source')
  h=root/'holes.json';h.write_text(json.dumps(dict(project_id='DP_EXACT_ID',status='SUCCESS')))
  return root,s,c,h
 def test_independent_scripts_and_explicit_chain(self):
  with tempfile.TemporaryDirectory() as td:
   root,s,c,h=self.setup_files(td);r=generate_pipeline(s,c,root,h)
   self.assertEqual(len(r['stages']),6)
   for n,stage in enumerate(r['stages'],1):
    source=Path(stage['script']).read_text();compile(source,stage['script'],'exec')
    self.assertIn('p7_run(PIPELINE_PLAN)',source);self.assertEqual(stage['stage'],n)
    self.assertEqual(Path(stage['script']).parent,root)
    self.assertEqual(Path(stage['output_cae']).parent,root/'CAE_Results')
    if n>1:self.assertEqual(stage['input_cae'],r['stages'][n-2]['output_cae'])
   r2=generate_pipeline(s,c,root,h);self.assertNotEqual(r['manifest'],r2['manifest']);self.assertEqual(c.read_bytes(),b'CAE source')
 def test_single_stage_rejects_wrong_or_changed_predecessor(self):
  with tempfile.TemporaryDirectory() as td:
   root,s,c,h=self.setup_files(td)
   with self.assertRaises(ValueError):generate_pipeline(s,c,root,h,3)
   report=root/'prev.json';data=dict(status='SUCCESS',stage=2,project_id='DP_EXACT_ID',output_cae=str(c),output_sha256=hashlib.sha256(c.read_bytes()).hexdigest());report.write_text(json.dumps(data))
   r=generate_pipeline(s,c,root,h,3,report);self.assertEqual(len(r['stages']),1)
   c.write_bytes(b'changed')
   with self.assertRaises(ValueError):generate_pipeline(s,c,root,h,3,report)
 def test_runtime_refuses_missing_predecessor_before_open(self):
  from cadtocae import step07_pipeline_runtime as rt
  import os,re,traceback
  rt.os=os;rt.hashlib=hashlib;rt.json=json
  with tempfile.TemporaryDirectory() as td:
   root,s,c,h=self.setup_files(td)
   with self.assertRaises(ValueError):rt.p7_check_input(dict(input_cae=str(c),input_sha256=None,predecessor_report=None,stage=4))
