import ast,json,tempfile,unittest
from pathlib import Path
from cadtocae.step07_inplace import generate_inplace
class InplaceTests(unittest.TestCase):
 def files(self,d):
  p=Path(d);s=p/'summary.json';h=p/'holes.json'
  s.write_text(json.dumps(dict(project_id='DP_TEST',model_name='DP_TEST')));h.write_text(json.dumps(dict(project_id='DP_TEST',status='SUCCESS')))
  return p,s,h
 def test_six_scripts_no_database_or_process_calls(self):
  with tempfile.TemporaryDirectory() as d:
   p,s,h=self.files(d);r=generate_inplace(s,p,h)
   self.assertEqual(len(r['stages']),7);self.assertFalse((p/'CAE_Results').exists())
   for plan in r['stages']:
    code=Path(plan['script']).read_text();tree=ast.parse(code)
    calls=[n.func.attr if isinstance(n.func,ast.Attribute) else getattr(n.func,'id','') for n in ast.walk(tree) if isinstance(n,ast.Call)]
    self.assertTrue(set(calls).isdisjoint({'openMdb','Mdb','closeMdb','saveAs','copyfile','copy2','Popen','system','p7_run','sg_dispatch'}))
    self.assertNotIn('input_cae',plan);self.assertNotIn('output_cae',plan)
    self.assertIn('u7_run(INPLACE_PLAN)',code)
    for old in ('def p7_run(', 'def m3_run(', 'def b2_run(', 'def t4_run('):self.assertNotIn(old,code)
 def test_stable_names_and_explicit_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   p,s,h=self.files(d);a=generate_inplace(s,p,h);b=generate_inplace(s,p,h)
   self.assertEqual(a['stages'],b['stages']);self.assertEqual(b['file_update']['status'],'ALREADY_IDENTICAL');py=Path(a['stages'][0]['script']);py.write_text('historical')
   with self.assertRaisesRegex(ValueError,'OVERWRITE_CONFIRMATION'):generate_inplace(s,p,h)
   self.assertEqual(py.read_text(),'historical');generate_inplace(s,p,h,overwrite=True)
   self.assertIn('u7_run',py.read_text())
 def test_single_stage_without_predecessor_cae(self):
  with tempfile.TemporaryDirectory() as d:
   p,s,h=self.files(d);r=generate_inplace(s,p,h,4)
   self.assertEqual([x['stage'] for x in r['stages']],[4]);self.assertFalse(list(p.rglob('*.cae')))
 def test_project_mismatch_blocks_all_writes(self):
  with tempfile.TemporaryDirectory() as d:
   p,s,h=self.files(d);h.write_text(json.dumps(dict(project_id='OTHER',status='SUCCESS')))
   with self.assertRaisesRegex(ValueError,'HOLE_REPORT_INVALID'):generate_inplace(s,p,h)
   self.assertFalse(list(p.glob('*.py')))
if __name__=='__main__':unittest.main()
