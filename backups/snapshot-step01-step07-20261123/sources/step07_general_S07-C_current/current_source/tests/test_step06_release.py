import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cadtocae.step06_release import versioned_source, matching_hole_plan, generate_release_batch
from cadtocae.step06_version import STEP06_VERSION, version_fields
from cadtocae.connector_b1_plan import fingerprint

class ReleaseTests(unittest.TestCase):
    def test_generated_runtime_report_version(self):
        with tempfile.TemporaryDirectory() as temp:
            report=Path(temp)/'report.json'
            source="import json\nREPORT_PATH = %r\nif __name__ == '__main__':\n    with open(REPORT_PATH,'w') as handle:\n        json.dump({'status':'SUCCESS'},handle)\n" % str(report)
            exec(compile(versioned_source(source),'generated','exec'),{'__name__':'__main__'})
            data=json.loads(report.read_text())
            self.assertEqual(data['status'],'SUCCESS')
            self.assertEqual(data['step06_version'],STEP06_VERSION)
            self.assertEqual(data['generator_version'],STEP06_VERSION)
    def test_legacy_and_versioned_report_fingerprints(self):
        with tempfile.TemporaryDirectory() as temp:
            fresh={'project_id':'TEST'}
            for plan in (fresh,dict(fresh,**version_fields())):
                self.assertEqual(matching_hole_plan(fresh,{'plan_fingerprint':fingerprint(plan)},Path(temp),'TEST'),plan)
            with self.assertRaisesRegex(ValueError,'does not match'):
                matching_hole_plan(fresh,{'plan_fingerprint':'bad'},Path(temp),'TEST')
    def test_fresh_generation_includes_connector_without_reports_or_preload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);script=folder/'TEST.py'
            script.write_text("import json\nREPORT_PATH='unused'\nif __name__ == '__main__':\n    pass\n")
            row=dict(source_folder=temp,project_id='TEST',plan={'project_id':'SP_SC_ANG18_TEST'},input_identity={},warnings=[],errors=[])
            scan=dict(source_folder=temp,include_subfolders=False,projects=[row])
            with patch('cadtocae.hole_projects.scan_projects',return_value=scan),patch('cadtocae.hole_projects.can_generate',return_value=True),patch('cadtocae.step06_release.write_hole_setup',return_value={'script':script}) as write:
                result=generate_release_batch(scan)
            self.assertEqual(result['generation_counts']['succeeded'],1)
            self.assertEqual(write.call_args.args[0]['step06_version'],STEP06_VERSION)
            self.assertEqual(set(result['projects'][0]['generated_files']),{'script','connector_plan','connector_script'})
            self.assertIn('Hole + Connector',result['projects'][0]['result'])
            self.assertNotIn('ConnectorForce',script.read_text())
