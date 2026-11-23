import sys,types,unittest,math
from unittest.mock import patch
from cadtocae import step07_mesh_runtime as rt

class ThinMeshTests(unittest.TestCase):
 def test_worsening_local_trials_restore_original_seeds(self):
  ns=types.SimpleNamespace
  nodes=[ns(coordinates=x) for x in [(0.,0.,0.),(.004,0.,0.),(0.,.004,0.),(0.,0.,.004)]]
  e=ns(label=19,getNodes=lambda:nodes)
  face=ns(getEdges=lambda:[0])
  faces=ns(getClosest=lambda **kw:{0:(face,(0,0,0))})
  edges=[ns(getSize=lambda **kw:.004) for i in range(4)]
  state={'seeds':{},'generated':0}
  def quality(**kw):
   if kw['criterion']=='analysis':return {'failedElements':[],'naElements':[]}
   return {'failedElements':[e,e] if state['seeds'] else [e],'worst':.02 if state['seeds'] else .04}
  def seed(**kw):state['seeds'][0]=kw['size']
  def clear(**kw):state['seeds'].clear()
  def generate():state['generated']+=1
  p=ns(name='thin',edges=edges,faces=faces,elements=[e],verifyMeshQuality=quality,getUnmeshedRegions=lambda:None,
       deleteMesh=lambda:None,deleteSeeds=clear,seedPart=lambda **kw:None,seedEdgeBySize=seed,generateMesh=generate)
  d={'local_seeds_m':{},'size_m':.008}
  c={'mesh_rules':{'shape_warning':.05,'max_connection_edge_length':.2,'max_repair_edge_fraction':.85,'deviation_factor':.1,'min_size_factor':.1}}
  with patch.dict(sys.modules,{'abaqusConstants':ns(SHAPE_FACTOR='shape',ANALYSIS_CHECKS='analysis',FINER='finer')}),patch.object(rt,'math',math,create=True):
   rt.m3_repair_thin_solid(p,d,c)
  self.assertEqual(state['seeds'],{})
  self.assertEqual(d['adaptive_solid_repair']['initial_score'],d['adaptive_solid_repair']['final_score'])
  self.assertLessEqual(len(d['quality_repairs']),5)
  self.assertGreater(state['generated'],1)
 def test_shape_review_only_for_current_spdc_stage4(self):
  constants=types.SimpleNamespace(ANALYSIS_CHECKS='analysis',SHAPE_FACTOR='shape',ASPECT_RATIO='aspect')
  def quality(**kw):
   return {'failedElements':[types.SimpleNamespace(label=116)] if kw['criterion']=='shape' else [],'naElements':[]}
  p=types.SimpleNamespace(name='thin',verifyMeshQuality=quality)
  base={'mesh_rules':{'shape_warning':.05,'aspect_warning':10}}
  with patch.dict(sys.modules,{'abaqusConstants':constants}):
   c=dict(base,stage=4,summary={'structure_type':'SP_DC'})
   self.assertEqual(rt.m3_quality(p,c)['shape_factor']['failedElements'],[116])
   self.assertEqual(rt.m3_quality(p,dict(c,stage=5))['shape_factor']['failedElements'],[116])
   for structure in ('DP','SP_SC'):
    with self.assertRaisesRegex(ValueError,'LOW_SHAPE_FACTOR'):
     rt.m3_quality(p,dict(base,stage=4,summary={'structure_type':structure}))
   with self.assertRaisesRegex(ValueError,'LOW_SHAPE_FACTOR'):rt.m3_quality(p,dict(base,stage=3,summary={'structure_type':'SP_DC'}))
 def test_analysis_errors_still_block_spdc(self):
  constants=types.SimpleNamespace(ANALYSIS_CHECKS='analysis',SHAPE_FACTOR='shape',ASPECT_RATIO='aspect')
  p=types.SimpleNamespace(name='thin',verifyMeshQuality=lambda **kw:{'failedElements':[types.SimpleNamespace(label=5)] if kw['criterion']=='analysis' else []})
  with patch.dict(sys.modules,{'abaqusConstants':constants}):
   with self.assertRaisesRegex(ValueError,'ANALYSIS_MESH_QUALITY_FAILED'):
    rt.m3_quality(p,{'stage':4,'summary':{'structure_type':'SP_DC'},'mesh_rules':{'shape_warning':.05,'aspect_warning':10}})
