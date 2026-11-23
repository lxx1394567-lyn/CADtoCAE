import unittest
from types import SimpleNamespace as N
from cadtocae.step07_postprocess_runtime import pp_base_rf

class RFTests(unittest.TestCase):
    def run_rf(self,sets,project='DP_TEST',fields=True):
        repo={k:N(nodes=[N(label=v[0])],value=N(instance=None,nodeLabel=v[0],data=v[1],localCoordSystem=None)) for k,v in sets.items()}
        field=N(getSubset=lambda region:N(values=[region.value]))
        return pp_base_rf(N(rootAssembly=N(nodeSets=repo)),N(fieldOutputs={'RF':field} if fields else {}),{'project_id':project})
    def test_vector_sum_not_sum_of_magnitudes(self):
        r=self.run_rf({'STEP07_RP_BASE_FRONT':(1,(3,0,4)),'STEP07_RP_BASE_REAR':(2,(-3,0,4))})
        self.assertEqual(r['status'],'SUCCESS');self.assertEqual(r['total_magnitude_N'],8)
    def test_duplicate_rejected(self):
        r=self.run_rf({'STEP07_RP_BASE_FRONT':(1,(3,0,4)),'STEP07_RP_BASE_REAR':(1,(3,0,4))})
        self.assertEqual(r['status'],'REVIEW_REQUIRED');self.assertIsNone(r['total_components_N'])
    def test_missing_rf_not_zero(self):
        r=self.run_rf({},fields=False);self.assertEqual(r['issues'],['RF_FIELD_MISSING']);self.assertIsNone(r['total_magnitude_N'])
    def test_coupling_alias_excluded(self):
        r=self.run_rf({'STEP07_RP_BASE':(1,(3,0,4)),'ASSEMBLY_STEP07_COUPLING_BASE_REFERENCE_POINT':(1,(3,0,4))},'SP_DC_TEST')
        self.assertEqual(len(r['rows']),1);self.assertEqual(r['total_magnitude_N'],5)

if __name__=='__main__':unittest.main()
