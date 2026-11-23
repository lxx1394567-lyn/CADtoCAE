import unittest, math
from pathlib import Path
class VectorLoadTests(unittest.TestCase):
 def setUp(self):
  self.ns={'math':math};exec(compile(Path('src/cadtocae/step07_load_runtime.py').read_text(encoding='utf-8'),'runtime','exec'),self.ns)
 def test_luan_vector_not_scalar_normal(self):
  t={'wind_direction':[math.sin(math.radians(19)),0,-math.cos(math.radians(19))]}
  d={'tributary_length_m':3.268,'components':[],'vector_components':[{'direction':'PANEL_INWARD_NORMAL','q_N_per_m':588.858984},{'direction':'GLOBAL_DOWN','q_N_per_m':752.4741313932981}]}
  v,n,unit=self.ns['l5_resultant'](d,t)
  self.assertAlmostEqual(v[0],626.5204783211);self.assertAlmostEqual(v[2],-4278.6330496201)
  self.assertAlmostEqual(sum(x*x for x in unit),1)
  self.assertLess(n,(588.858984+752.4741313932981)*3.268)
 def test_legacy_negative_keeps_direction(self):
  v,n,u=self.ns['l5_resultant']({'tributary_length_m':3.7,'components':[{'direction':'PANEL_INWARD_NORMAL','q_N_per_m':-815.328}]},{'wind_direction':[0,0,-1]})
  self.assertAlmostEqual(v[2],3016.7136);self.assertEqual(u,[0,0,1])
 def test_end_lengths_conserve_total(self):
  from cadtocae.step07_tributary import tributary_layout
  layout=dict(project_id='SP_DC_TEST',model_id='LUAN19',structure_type='SP_DC',purlin_length_m=16.336,support_count=4,support_spacing_m=[4.9]*3,support_position='LEFT',support_index=0,cantilever_left_m=.818,cantilever_right_m=.818)
  d=tributary_layout('SP_DC_TEST','LUAN19','SP_DC',layout)
  self.assertAlmostEqual(d['tributary_length_m'],3.268);self.assertAlmostEqual(sum(d['tributary_lengths_m']),16.336)
if __name__=='__main__':unittest.main()
