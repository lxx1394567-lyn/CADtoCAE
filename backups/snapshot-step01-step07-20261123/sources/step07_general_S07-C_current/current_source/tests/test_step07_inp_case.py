import unittest,types
from pathlib import Path
class InpCaseTests(unittest.TestCase):
 def test_mixed_missing_or_foreign_loads_blocked_before_export(self):
  ns={};exec(compile(Path('src/cadtocae/step07_inp_runtime.py').read_text(encoding='utf-8'),'runtime','exec'),ns)
  ns['l5_config']=lambda c:dict(job_id=c['job'],case_id=c['case'],groups=['P01'])
  ns['l5_prefix']=lambda d:'STEP07_LOAD_'+d['job_id']+'_'+d['case_id']+'_'
  cases=[dict(job='J13',case='POS'),dict(job='J14',case='NEG')]
  for names in [[],['STEP07_LOAD_J13_POS_P01_COMBINED','STEP07_LOAD_J14_NEG_P01_COMBINED'],['STEP07_LOAD_J13_POS_P01_COMBINED','Gravity-1']]:
   with self.assertRaisesRegex(ValueError,'EXACTLY_ONE_VERIFIED_CASE'):ns['i6_validate_loads'](types.SimpleNamespace(loads=dict.fromkeys(names)),dict(load_case_configs=cases))
if __name__=='__main__':unittest.main()
