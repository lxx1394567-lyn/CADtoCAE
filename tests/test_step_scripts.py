from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "examples" / "洋县-11042210101041S-T0202-单桩单立柱.pdf"
if not PDF.exists():
    PDF = ROOT / "洋县-11042210101041S-T0202-单桩单立柱.pdf"


class StepScriptTest(unittest.TestCase):
    def test_step01_pdf_only_does_not_fake_components(self):
        if not PDF.exists():
            self.skipTest("sample PDF is not available")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "step01_generate_part_excel.py"),
                    "--pdf",
                    str(PDF),
                    "--outputs-root",
                    tmp,
                    "--support-type",
                    "单桩单立柱",
                    "--angle",
                    "20",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(list(Path(tmp).glob("**/*_components.xlsx")))


if __name__ == "__main__":
    unittest.main()
