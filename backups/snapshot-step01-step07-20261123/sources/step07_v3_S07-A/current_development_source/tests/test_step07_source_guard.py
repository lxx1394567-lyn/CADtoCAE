import unittest,tempfile,types,sys,hashlib,os,json
from pathlib import Path
from unittest.mock import patch
from cadtocae import step07_source_guard_runtime as g
class SourceGuardTests(unittest.TestCase):
 def test_source_mutation_is_identified_at_observation(self):
  g.os=os;g.json=json;g.p7_hash=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'source.cae';p.write_bytes(b'original');r={'input_sha256':g.p7_hash(p)};c={'input_cae':str(p),'scratch_cae':str(Path(t)/'scratch.cae')}
   with patch.dict(sys.modules,{'abaqus':types.SimpleNamespace(mdb=types.SimpleNamespace(pathName='copy.cae'))}):
    g.sg_mark(c,r,'before_copy');p.write_bytes(b'externally changed')
    with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_AT: after_open'):
     g.sg_mark(c,r,'after_open')
   self.assertEqual(r['source_changed_at'],'after_open');self.assertEqual(len(r['source_audit']),2)
 def test_changed_snapshot_blocked_even_if_source_unchanged(self):
  g.os=os;g.json=json;g.p7_hash=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'source';p.write_bytes(b'source');c={'input_cae':str(p),'scratch_cae':str(Path(t)/'work')};Path(c['scratch_cae']+'_snapshot.cae').write_bytes(b'wrong')
   with patch.dict(sys.modules,{'abaqus':types.SimpleNamespace(mdb=types.SimpleNamespace(pathName='copy'))}):
    with self.assertRaisesRegex(ValueError,'INPUT_SNAPSHOT_CHANGED_AT'):
     g.sg_mark(c,{'input_sha256':g.p7_hash(p)},'snapshot_check')
