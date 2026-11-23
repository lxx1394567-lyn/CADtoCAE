import ast,unittest
from pathlib import Path
from cadtocae.step07_runtime_bundle import bundle_runtime
from cadtocae.step07_pipeline import RUNTIMES
class RuntimeBundleTests(unittest.TestCase):
 def test_legacy_entries_removed_live_functions_unchanged(self):
  root=Path(__file__).parents[1]/'src/cadtocae'
  sources=[(n,(root/n).read_text(encoding='utf-8-sig')) for n in RUNTIMES]
  code,audit=bundle_runtime(sources)
  original={n.name:ast.dump(n) for _,s in sources for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
  current={n.name:ast.dump(n) for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)}
  for name,node in current.items():self.assertEqual(node,original[name])
  self.assertIn('mc_cleanup',current);self.assertIn('s7_apply_static_step',current)
  self.assertNotIn('t4_run',current);self.assertNotIn('m3_run',current)
  self.assertGreater(len(audit['removed_functions']),0)
 def test_duplicate_definitions_fail_before_generation(self):
  with self.assertRaisesRegex(ValueError,'RUNTIME_DUPLICATE_FUNCTION'):
   bundle_runtime([('a','def p7_run(): pass\n'),('b','def p7_run(): pass\n')])
 def test_dependency_closure_retains_callbacks(self):
  code,_=bundle_runtime([('a','def callback(): return 1\ndef p7_run(): return list(map(callback, []))\ndef unused(): pass\n')])
  self.assertIn('def callback',code);self.assertNotIn('def unused',code)
