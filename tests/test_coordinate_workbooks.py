from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from cadtocae.coordinate_workbooks import create_coordinate_formula_workbooks


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "examples" / "sp_sc_ang20_coordinate_layout.json"


class CoordinateWorkbookTest(unittest.TestCase):
    def test_coordinate_workbooks_use_project_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            full, simple = create_coordinate_formula_workbooks(
                LAYOUT,
                tmp_path / "DP_ANG26P5_coordinate_formula_full_fixed.xlsx",
                tmp_path / "DP_ANG26P5_coordinate_formula_simple_fixed.xlsx",
                "DP_ANG26P5",
            )
            self.assertTrue(full.exists())
            self.assertTrue(simple.exists())

            wb = load_workbook(full, data_only=False)
            ws = wb["构件轴线校核"]
            part_names = [ws.cell(row=row, column=2).value for row in range(4, 7)]
            instance_names = [ws.cell(row=row, column=3).value for row in range(4, 7)]
            self.assertIn("P_DP_ANG26P5_BRACE_FRONT", part_names)
            self.assertIn("I_DP_ANG26P5_BRACE_FRONT_01", instance_names)


if __name__ == "__main__":
    unittest.main()
