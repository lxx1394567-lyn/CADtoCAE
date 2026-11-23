import copy,unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from cadtocae import step07_runtime as rt
class SnapshotCompatibilityTests(unittest.TestCase):
 def test_fast_inventory_matches_former_strip_without_losing_regions(self):
  v=N(index=7,pointOn=((1.,2.,3.),));node=N(label=12,coordinates=(1.,2.,3.));element=N(label=9,type='C3D10',connectivity=(1,2,3))
  region=N(vertices=[v],edges=[],faces=[v],cells=[],nodes=[node],elements=[element],referencePoints=[])
  geometry=dict(vertices=[v],edges=[],faces=[v],cells=[],nodes=[node],elements=[element],sets={'kept':region},surfaces={'face':region},referencePoints={},sectionAssignments=[])
  part=N(**geometry);instance=N(partName='P',dependent=True,getTranslation=lambda:(0,0,0),getRotation=lambda:(),**geometry)
  assembly=N(sets={'BC':region},surfaces={'TIE':region},referencePoints={},instances={'I':instance})
  model=N(rootAssembly=assembly,parts={'P':part})
  for name in ('loads','boundaryConditions','interactions','interactionProperties','materials','sections','profiles','fieldOutputRequests','historyOutputRequests'):setattr(model,name,{})
  db=N(jobs={},models={'target':model})
  with patch.object(rt,'s7_snapshot',return_value={'tie':'preserved'}):
   full=rt.s7_stage1_inventory(db);fast=rt.s7_stage1_inventory(db,include_mesh=False)
  def strip(x):
   if isinstance(x,dict):
    for k in list(x):
     if k in ('nodes','elements'):del x[k]
     else:strip(x[k])
   elif isinstance(x,(list,tuple)):
    for v in x:strip(v)
  self.assertIn('nodes',full['models']['target']['parts']['P']);strip(full);self.assertEqual(fast,full)
  self.assertEqual(fast['models']['target']['assembly_surfaces']['TIE']['faces'],[7])
if __name__=='__main__':unittest.main()
