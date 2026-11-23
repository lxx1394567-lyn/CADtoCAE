import unittest,ast
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1]/'src/cadtocae'
class ContractTests(unittest.TestCase):
 def run_contract(self,names):
  ns={};exec(compile((ROOT/'step07_bc_runtime.py').read_text(encoding='utf-8'),'<runtime>','exec'),ns)
  ns['b2_plan']=lambda m,c: ([{'tag':'BASE','data':{}}],[{'tag':'P01_PURLIN_FRONT','data':{},'faces':[]}])
  ns['b2_verify']=lambda m,r:r.update(verified=True)
  report={};m=NS(constraints={},boundaryConditions=dict.fromkeys(names))
  return ns,m,report
 def test_actual_contract_and_dofs(self):
  ns,m,r=self.run_contract(['STEP07_BC_BASE','STEP07_BC_P01_PURLIN_FRONT'])
  x=ns['b2_validate_existing'](m,{},r)
  self.assertEqual(x['validation_status'],'SUCCESS');self.assertEqual(x['missing_bc_names'],[])
  self.assertEqual(x['required_dofs']['STEP07_BC_P01_PURLIN_FRONT'],['U2','UR1','UR2','UR3'])
 def test_missing_is_reported_not_accepted(self):
  ns,m,r=self.run_contract(['STEP07_BC_BASE'])
  with self.assertRaisesRegex(ValueError,'BC_STAGE_INCOMPLETE'):ns['b2_validate_existing'](m,{},r)
  self.assertEqual(r['bc_validation']['missing_bc_names'],['STEP07_BC_P01_PURLIN_FRONT'])
  self.assertEqual(r['bc_validation']['validation_status'],'FAILED')
 def test_extra_owned_bc_blocked(self):
  ns,m,r=self.run_contract(['STEP07_BC_BASE','STEP07_BC_P01_PURLIN_FRONT','STEP07_BC_BAD'])
  with self.assertRaises(ValueError):ns['b2_validate_existing'](m,{},r)
  self.assertEqual(r['bc_validation']['unexpected_bc_names'],['STEP07_BC_BAD'])
 def test_both_stages_call_shared_validator(self):
  for filename,name in [('step07_bc_runtime.py','b2_apply'),('step07_mesh_runtime.py','m3_apply')]:
   tree=ast.parse((ROOT/filename).read_text(encoding='utf-8'));f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
   self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='b2_validate_existing' for n in ast.walk(f)))
if __name__=='__main__':unittest.main()
