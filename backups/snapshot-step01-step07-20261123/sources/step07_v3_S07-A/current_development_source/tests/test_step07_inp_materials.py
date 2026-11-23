import unittest
from types import SimpleNamespace as N
from cadtocae.step07_inp_runtime import i6_materials
class Material(N):
 def Elastic(self,table):self.elastic=N(table=table,type='ISOTROPIC')
class InpMaterialTests(unittest.TestCase):
 def fixture(self,material):
  m=N(parts={'P':N(sectionAssignments=[N(sectionName='S')])},rootAssembly=N(instances={'I':N(partName='P')}),sections={'S':N(material='MAT_MANUAL_CHECK')},materials={'MAT_MANUAL_CHECK':material})
  return m,dict(summary=dict(instances=[dict(instance_name='I')])),{}
 def test_empty_material_blocks_without_mutation(self):
  mat=Material();m,c,r=self.fixture(mat)
  with self.assertRaisesRegex(ValueError,'MATERIAL_DATA_REQUIRED'):i6_materials(m,c,r)
  self.assertFalse(hasattr(mat,'elastic'));self.assertEqual(r['material_validation']['MAT_MANUAL_CHECK']['status'],'MISSING_ELASTIC')
 def test_explicit_trial_permission_adds_and_reports_only_missing_elastic(self):
  mat=Material();m,c,r=self.fixture(mat);c['trial_materials']={'MAT_MANUAL_CHECK':dict(confirmed=True,engineering_status='DEMO_ONLY',elastic_modulus_Pa=2.06e11,poisson_ratio=.3,authorization='user trial only')}
  i6_materials(m,c,r);self.assertEqual(mat.elastic.table,((2.06e11,.3),));self.assertTrue(r['model_may_be_changed']);self.assertEqual(len(r['trial_materials_added']),1)
  r2={};i6_materials(m,c,r2);self.assertNotIn('trial_materials_added',r2)
 def test_bad_constants_not_accepted(self):
  m,c,r=self.fixture(Material(elastic=N(table=((0,.3),),type='ISOTROPIC')))
  with self.assertRaisesRegex(ValueError,'MATERIAL_DATA_REQUIRED'):i6_materials(m,c,r)
if __name__=='__main__':unittest.main()
