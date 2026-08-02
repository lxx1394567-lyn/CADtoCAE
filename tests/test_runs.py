from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cadtocae.runs import RUN_SUBDIRS, create_run_paths, update_manifest


class RunDirectoryTest(unittest.TestCase):
    def test_create_timestamped_run_directory_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = create_run_paths("SP_SC_ANG20", outputs_root=tmp)

            self.assertTrue(paths.root.name)
            self.assertEqual(paths.root.parent.name, "SP_SC_ANG20_runs")
            for name in RUN_SUBDIRS:
                self.assertTrue((paths.root / name).is_dir())

            manifest = update_manifest(
                paths,
                "SP_SC_ANG20",
                "step_test",
                inputs={"source": "input.xlsx"},
                outputs={"json": {"assembly_inputs": "assembly_inputs.json"}},
                warnings=["check me"],
            )
            self.assertEqual(manifest["project_code"], "SP_SC_ANG20")
            self.assertEqual(manifest["project_prefix"], "SP_SC_ANG20")
            self.assertIn("step_test", manifest["stages"])
            self.assertTrue(paths.manifest.exists())

            latest = Path(tmp) / "latest_run_manifest.json"
            self.assertTrue(latest.exists())
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(Path(latest_payload["run_dir"]), paths.root.resolve())
            self.assertEqual(latest_payload["project_prefix"], "SP_SC_ANG20")

            latest_paths = create_run_paths("SP_SC_ANG20", outputs_root=tmp, run_dir="latest")
            self.assertEqual(latest_paths.root, paths.root.resolve())


if __name__ == "__main__":
    unittest.main()
