import json,tempfile,unittest,copy
from pathlib import Path
import openpyxl
from cadtocae.step07_load_input import read_load_cases
class DualCasesTests(unittest.TestCase):
 def fixture(self,root,structure='SP_SC',count=2):
  p=Path(root)/'loads.xlsx';w=openpyxl.Workbook();w.remove(w.active)
  models=w.create_sheet('9套基准荷载');tasks=w.create_sheet('16组Abaqus任务')
  kind={'SP_SC':'单桩单立柱','SP_DC':'单桩双立柱','DP':'双桩双立柱'}[structure]
  for col,val in {'A':'M01','B':'Example','C':kind,'D':14,'M':1.25,'N':-.8}.items():models[col+'5']=val
  for row,job,label,q,direction in [(5,'J01','正风压+恒雪',1.25,'下压'),(6,'J02','负风吸力',-.8,'上拔')]:
   for col,val in {'A':job,'B':'M01','C':'Example','D':14,'E':label,'F':q,'G':'=F%d*1000'%row,'H':direction}.items():tasks[col+str(row)]=val
  w.save(p);w.close()
  project=structure+'_TEST';summary=dict(project_id=project,model_name=project,structure_type=structure,instances=[dict(instance_name='PURLIN_LOCAL_%02d'%k,canonical_role='PURLIN_LOCAL',connection_group='P%02d'%k,geometry_info=dict(length=.05)) for k in range(1,count+1)])
  layout=dict(project_id=project,model_id='M01',structure_type=structure,purlin_length_m=5.,support_count=2,support_spacing_m=[4.],support_position='LEFT',support_index=0,cantilever_left_m=.5,cantilever_right_m=.5)
  mapping=dict(confirmed=True,source='Synthetic test fixture only',project_id=project,model_id='M01',project_site='Example',structure_type=structure,angle_deg=14,support_layout=layout)
  return p,summary,mapping
 def test_all_three_types_distinct_layout_and_variable_instances(self):
  with tempfile.TemporaryDirectory() as root:
   for typ,n in [('SP_SC',2),('SP_DC',3),('DP',4)]:
    p,s,m=self.fixture(root,typ,n);a,b=read_load_cases(p,s,m)
    self.assertEqual([a['case_id'],b['case_id']],['POS','NEG']);self.assertEqual(a['tributary_length_m'],2.5)
    self.assertEqual(a['all_purlins_total_force_N'],3125*n);self.assertEqual(b['all_purlins_total_force_N'],-2000*n)
    self.assertTrue(any(x['method']=='RECALCULATED_NO_CACHE' for x in b['formula_audit']))
 def test_same_angle_other_site_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   p,s,m=self.fixture(root);m['project_site']='Other'
   with self.assertRaisesRegex(ValueError,'METADATA_MISMATCH'):read_load_cases(p,s,m)
 def test_no_inference_for_missing_layout(self):
  with tempfile.TemporaryDirectory() as root:
   p,s,m=self.fixture(root);m['support_layout']=None
   with self.assertRaisesRegex(ValueError,'SUPPORT_LAYOUT_REQUIRED'):read_load_cases(p,s,m)
 def test_m08_blocked(self):
  with tempfile.TemporaryDirectory() as root:
   p,s,m=self.fixture(root);m['model_id']='M08'
   with self.assertRaisesRegex(ValueError,'M08_MODEL_MISSING'):read_load_cases(p,s,m)
 def test_wrong_negative_sign_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   p,s,m=self.fixture(root);w=openpyxl.load_workbook(p);w['16组Abaqus任务']['F6']=.8;w.save(p);w.close()
   with self.assertRaisesRegex(ValueError,'SIGN_OR_FORMULA'):read_load_cases(p,s,m)
 def test_existing_any_load_blocked_without_mutation(self):
  source=Path('src/cadtocae/step07_load_runtime.py').read_text(encoding='utf-8');ns={};exec(compile(source,'runtime','exec'),ns)
  from types import SimpleNamespace
  for name in ['STEP07_LOAD_J13_POS_P01_COMBINED','STEP07_LOAD_J14_NEG_P01_COMBINED','Gravity-1','UserPressure']:
   loads={name:object()};m=SimpleNamespace(loads=loads)
   with self.assertRaisesRegex(ValueError,'RESTORE_COMMON_BASE_MODEL'):ns['l5_exclusive_preflight'](m)
   self.assertEqual(list(loads),[name])
if __name__=='__main__':unittest.main()
