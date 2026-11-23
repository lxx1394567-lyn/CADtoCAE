import unittest,copy
from cadtocae.step07_tributary import tributary_layout,CONFIRMED_LAYOUTS
class TributaryTests(unittest.TestCase):
 def test_m07_conservation_and_middle_force(self):
  d=tributary_layout('DP_ANG14_FA03521S-T0104-02','M07','DP')
  self.assertEqual(d['tributary_lengths_m'],[2.1790000000000003,3.7,2.1790000000000003])
  self.assertAlmostEqual(sum(d['tributary_lengths_m']),8.058)
  self.assertAlmostEqual(1251.58808*d['tributary_length_m'],4630.875896)
 def test_429_conflict_rejected(self):
  d=copy.deepcopy(next(iter(CONFIRMED_LAYOUTS.values())));d['cantilever_left_m']=d['cantilever_right_m']=.429
  with self.assertRaisesRegex(ValueError,'SUM_MISMATCH'):tributary_layout(d['project_id'],'M07','DP',d)
 def test_no_defaults_for_other_project(self):
  with self.assertRaisesRegex(ValueError,'LAYOUT_REQUIRED'):tributary_layout('SP_SC_X','M01','SP_SC')
 def test_explicit_other_structure_layout(self):
  for kind in ('SP_SC','SP_DC'):
   d=dict(project_id=kind+'_X',model_id='M01',structure_type=kind,purlin_length_m=5.,support_count=2,support_spacing_m=[4.],support_position='LEFT',support_index=0,cantilever_left_m=.5,cantilever_right_m=.5)
   self.assertEqual(tributary_layout(d['project_id'],'M01',kind,d)['tributary_length_m'],2.5)
if __name__=='__main__':unittest.main()
