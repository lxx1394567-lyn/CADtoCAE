import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from cadtocae.connector_integration import integrated_plan, integrated_source
from cadtocae.connector_groups import build_group_plan
from test_step06_connector_groups import four

class IntegrationTests(unittest.TestCase):
    def runtime(self,folder):
        holes,report=four();plan=integrated_plan(holes,folder)
        ns={'__name__':'test'};exec(integrated_source(plan,folder/'b.json'),ns)
        return ns,plan,report
    def test_missing_a_report_fails_before_model_access(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);ns,p,r=self.runtime(folder);mdb=Mock()
            with self.assertRaisesRegex(ValueError,'STEP06_A_REQUIRED'):
                ns['execute_integrated_connectors'](p,mdb,str(folder/'b.json'))
            self.assertEqual(mdb.mock_calls,[])
            self.assertEqual(json.loads((folder/'b.json').read_text())['status'],'FAILED')
    def test_embedded_plan_builder_matches_validated_generator(self):
        with tempfile.TemporaryDirectory() as temp:
            ns,p,r=self.runtime(Path(temp))
            self.assertEqual(ns['build_group_plan'](p['hole_plan'],r),build_group_plan(p['hole_plan'],r))
    def test_missing_beam_geometry_blocks_both_families(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);ns,p,r=self.runtime(folder)
            Path(p['hole_report_path']).write_text(json.dumps(r))
            create=Mock();ns['execute_connector_groups']=create
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_P01_P04_GROUPS'):
                ns['execute_integrated_connectors'](p,Mock(),str(folder/'b.json'))
            create.assert_not_called()
    def test_python2_grammar_and_no_load_creation(self):
        from lib2to3.refactor import RefactoringTool
        with tempfile.TemporaryDirectory() as temp:
            ns,p,r=self.runtime(Path(temp));s=integrated_source(p,'report.json')
            RefactoringTool([]).refactor_string(s,'connector.py')
            for value in ('KINEMATIC','5.0e8','2.0e8','20000','STEP06_RP_P01','STEP06_RP_P04','STEP06_CONNECTOR_SECTION_PURLIN_BOLT'):
                self.assertIn(value,s)
            self.assertNotIn('ConnectorForce(',s)
            self.assertNotIn('CutExtrude(',s)
    def test_version_only_legacy_plan_survives_repeated_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);holes={'project_id':'SP_SC_ANG18_TEST','xyz':(1,2,3),'step06_version':'0.2.2'}
            legacy=dict(holes,step06_version='0.2.1')
            (folder/'SP_SC_ANG18_TEST_step06_plan.json').write_text(json.dumps(legacy))
            first=integrated_plan(holes,folder)
            self.assertEqual(len(first['compatible_hole_plans']),1)
            (folder/'SP_SC_ANG18_TEST_step06_plan.json').write_text(json.dumps(holes))
            (folder/'SP_SC_ANG18_TEST_step06_connector_plan.json').write_text(json.dumps(first))
            second=integrated_plan(holes,folder)
            self.assertIn(json.loads(json.dumps(legacy)),second['compatible_hole_plans'])
            changed=dict(holes,xyz=(4,5,6))
            self.assertEqual(integrated_plan(changed,folder)['compatible_hole_plans'],[])
