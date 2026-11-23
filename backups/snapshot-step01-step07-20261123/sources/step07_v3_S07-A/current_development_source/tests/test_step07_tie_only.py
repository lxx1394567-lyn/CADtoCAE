import unittest,tempfile,json
from pathlib import Path
from cadtocae.step06_execution_mode import connection_mode
from cadtocae.step07_tie_runtime import t4_clip,t4_area
from cadtocae.step07_tie_setup import generate_tie_setup
class TieOnlyTests(unittest.TestCase):
 def test_modes_default_and_identity(self):
  with tempfile.TemporaryDirectory() as td:
   self.assertEqual(connection_mode(td,'DP_FULL_ID'),'full');p=Path(td)/'DP_FULL_ID_step06_execution.json'
   p.write_text(json.dumps(dict(project_id='DP_FULL_ID',connection_mode='tie_only')));self.assertEqual(connection_mode(td,'DP_FULL_ID'),'tie_only')
   p.write_text(json.dumps(dict(project_id='other',connection_mode='tie_only')))
   with self.assertRaises(ValueError):connection_mode(td,'DP_FULL_ID')
 def test_footprint_clipping_excludes_nonoverlap(self):
  a=[(0,0),(2,0),(2,2),(0,2)];b=[(1,1),(3,1),(3,3),(1,3)]
  self.assertAlmostEqual(t4_area(t4_clip(a,b)),1.)
  self.assertEqual(t4_clip(a,[(4,4),(5,4),(5,5),(4,5)]),[])
 def test_versions_and_old_input_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);summary=root/'summary.json';summary.write_text(json.dumps(dict(project_id='DP_FULL_ID',model_name='DP_FULL_ID')))
   source=root/'DP_FULL_ID_step06_tie_only_fresh.cae';source.write_bytes(b'fresh')
   x=generate_tie_setup(summary,source,root);y=generate_tie_setup(summary,source,root)
   self.assertNotEqual(x['script'],y['script']);self.assertEqual(source.read_bytes(),b'fresh')
   self.assertEqual(Path(x['plan']['working_copy']).read_bytes(),b'fresh')
   old=root/'DP_FULL_ID_step07_03_v5.cae';old.write_bytes(b'old')
   with self.assertRaises(ValueError):generate_tie_setup(summary,old,root)

class DispatchTests(unittest.TestCase):
 def test_tie_only_dispatch_never_generates_connectors(self):
  from unittest.mock import patch
  from cadtocae.step06_release import generate_release_batch
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project='DP_FULL_ID';(root/(project+'_step06_execution.json')).write_text(json.dumps(dict(project_id=project,connection_mode='tie_only')))
   row=dict(source_folder=td,project_id=project,input_identity={},plan={'project_id':project},errors=[])
   scan=dict(source_folder=td,include_subfolders=False,projects=[row])
   with patch('cadtocae.step06_release.hole_projects.scan_projects',return_value=scan),patch('cadtocae.step06_release.hole_projects.can_generate',return_value=True),patch('cadtocae.step06_execution_mode.write_tie_only',return_value={'script':root/'holes.py'}),patch('cadtocae.step06_release.integrated_plan',side_effect=AssertionError('Connector branch called')):
    result=generate_release_batch(scan)
   self.assertEqual(result['generation_counts']['succeeded'],1)
   self.assertEqual(result['projects'][0]['connection_mode'],'tie_only')
