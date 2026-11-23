import unittest,types,tempfile,json,hashlib
from pathlib import Path
from cadtocae.step07_load_input import WorkbookValues,read_load_case
class FormulaTests(unittest.TestCase):
 def workbook(self,values,cache=None):
  w=object.__new__(WorkbookValues);w.active=set();w.used={};w.formulas={'S':{k:types.SimpleNamespace(value=v) for k,v in values.items()}};w.cached={'S':{k:types.SimpleNamespace(value=(cache or {}).get(k,None) if isinstance(v,str) and v.startswith('=') else v) for k,v in values.items()}};return w
 def test_formula_without_cache(self):
  w=self.workbook({'A1':.4,'B1':1.5,'C1':'=A1*B1*1.2*.8','D1':'=MAX(14,15)','E1':'=IF(D1<=15,C1,100)'})
  self.assertAlmostEqual(w.value('S','E1'),.576);self.assertEqual(w.used['S!E1']['method'],'RECALCULATED_NO_CACHE')
 def test_stale_cache_rejected(self):
  with self.assertRaisesRegex(ValueError,'STALE'):self.workbook({'A1':2,'B1':'=A1*1000'},{'B1':0}).value('S','B1')
 def test_blank_is_not_zero(self):
  with self.assertRaisesRegex(ValueError,'MISSING_CELL'):self.workbook({'A1':None,'B1':'=A1*2'}).value('S','B1')
 def test_cycle_rejected(self):
  with self.assertRaisesRegex(ValueError,'CYCLE'):self.workbook({'A1':'=B1','B1':'=A1'}).value('S','A1')
 def test_unsupported_formula_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNSUPPORTED'):self.workbook({'A1':'=SUM(1,2)'}).value('S','A1')
 def test_wrong_project_not_inferred_by_angle(self):
  with tempfile.NamedTemporaryFile(suffix='.xlsx') as f:
   with self.assertRaisesRegex(ValueError,'BINDING_REQUIRED'):read_load_case(f.name,{'project_id':'OTHER_ANG14'})
 def test_other_job_not_silently_j13(self):
  from unittest.mock import patch
  with patch('cadtocae.step07_load_input.read_load_cases',return_value=[{'job_id':'J13'},{'job_id':'J14'}]):
   with self.assertRaisesRegex(ValueError,'NOT_YET_VALIDATED'):read_load_case('unused',{},'J15')
 def test_json_hash_is_bytes(self):
  from cadtocae.step07_inplace import generate_inplace
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);s=p/'s.json';h=p/'h.json';s.write_text(json.dumps({'project_id':'DP_TEST','model_name':'DP_TEST'}));h.write_text(json.dumps({'project_id':'DP_TEST','status':'SUCCESS'}))
   with patch('cadtocae.step07_load_input.read_load_cases',return_value=[dict(case_id=k,job_id=j,model_id='M07',groups=['P01']) for k,j in [('POS','J13'),('NEG','J14')]]):
    r=generate_inplace(s,p,h,5,load_workbook='fake')
   c=r['stages'][0];self.assertEqual(hashlib.sha256(Path(c['load_config_path']).read_bytes()).hexdigest(),c['load_config_sha256'])
if __name__=='__main__':unittest.main()
