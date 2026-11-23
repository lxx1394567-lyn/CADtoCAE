import sys,types,math,unittest
from unittest.mock import patch
from cadtocae import step07_quality_runtime as q
from cadtocae import step07_tie_runtime as t
class QualityTests(unittest.TestCase):
 def run_case(self,warning=False,failure=False,complete=True,shape=False):
  n=lambda label,coords:types.SimpleNamespace(label=label,coordinates=coords)
  e=types.SimpleNamespace(label=1,type='S3',getNodes=lambda:[n(1,(0,0,0)),n(2,(1,0,0)),n(3,(0,1,0))])
  class Elements(list):
   def sequenceFromLabels(self,labels):return self
  elements=Elements([e]);sets={}
  p=types.SimpleNamespace(nodes=[1,2,3],elements=elements,faces=[],sets=sets,getUnmeshedRegions=lambda:None if complete else 'missing')
  p.Set=lambda name,elements:sets.update({name:types.SimpleNamespace(elements=elements)})
  m=types.SimpleNamespace(parts={'part':p},constraints={})
  r={'parts':{'part':dict(quality={'analysis':{'warningElements':[1] if warning else [],'failedElements':[1] if failure else []},'aspect_ratio':{'failedElements':[]},'shape_factor':{'failedElements':[1] if shape else []}},instances=['instance'],element_types={'S3':1})}}
  const=types.ModuleType('abaqusConstants');const.ANALYSIS_CHECKS='ANALYSIS_CHECKS'
  q.math=math;q.t4_sub=t.t4_sub;q.t4_cross=t.t4_cross;q.t4_dot=t.t4_dot
  with patch.dict(sys.modules,{'abaqusConstants':const}),patch.object(q,'q4_metrics',return_value={}):
   try:q.q4_diagnostics(m,{},r)
   except ValueError:
    self.assertTrue(failure or not complete)
  return r,p
 def test_warning_is_review_and_creates_inspection_set(self):
  r,p=self.run_case(warning=True);self.assertEqual(r['mesh_acceptance']['status'],'REVIEW_REQUIRED')
  self.assertFalse(r['mesh_acceptance']['next_stage_allowed']);self.assertIn('STEP07_QA_ANALYSIS_WARN',p.sets)
 def test_analysis_error_is_failed_even_with_warnings(self):
  r,_=self.run_case(warning=True,failure=True);self.assertEqual(r['mesh_acceptance']['status'],'FAILED')
 def test_unmeshed_is_failed(self):
  r,_=self.run_case(complete=False);self.assertEqual(r['mesh_acceptance']['status'],'FAILED')
 def test_clean_mesh_passes_checks(self):
  r,_=self.run_case();self.assertEqual(r['mesh_acceptance']['status'],'SUCCESS')
 def test_shape_only_failure_is_explicit_review_not_success(self):
  r,p=self.run_case(shape=True)
  self.assertEqual(r['mesh_acceptance']['status'],'REVIEW_REQUIRED')
  self.assertIn('STEP07_QA_SHAPE',p.sets)
  self.assertEqual(r['mesh_acceptance']['parts']['part']['shape_labels'],[1])
  self.assertTrue(r['mesh_acceptance']['parts']['part']['issues'][0]['shape_threshold_exceeded'])
