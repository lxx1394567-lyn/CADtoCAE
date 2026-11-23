"""Engineering rows, workbook contract and required user dimensions."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook

from cadtocae.hole_inputs import HEADERS, SHEET_NAME, normalize_hole_rows, read_hole_inputs

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples/step06/step06_bolt_hole_location.xlsx"


def input_rows():
    # Synthetic dimensions only: 100 x 63 x 6, Ri=7, extrusion length=80 mm.
    common = dict(project_id="TEST_STEP06", connection_group="P01", component_role="PURLIN_SUPPORT",
                  distance_from_end_mm=40., end_reference="START", hole_diameter_mm=14., enabled=True, note="")
    return [dict(common, hole_id="PS_TO_PURLIN", connection_target="PURLIN_LOCAL", leg="LONG_LEG",
                 distance_from_angle_corner_mm=50.),
            dict(common, hole_id="PS_TO_BEAM", connection_target="INCLINED_BEAM", leg="SHORT_LEG",
                 distance_from_angle_corner_mm=35.)]


class InputTests(unittest.TestCase):
    def test_valid_two_rows(self):
        rows = normalize_hole_rows(input_rows())
        self.assertEqual([r.source_row for r in rows], [2, 3])
        self.assertEqual(rows[0].distance_from_angle_corner_mm, 50.)

    def test_invalid_engineering_fields(self):
        for key, value in (("component_role", "PURLIN_LOCAL"), ("hole_id", "OTHER"),
                           ("connection_target", "INCLINED_BEAM"), ("leg", "X"),
                           ("distance_from_angle_corner_mm", -1), ("distance_from_end_mm", 0),
                           ("hole_diameter_mm", 0), ("hole_diameter_mm", float("inf")),
                           ("hole_diameter_mm", float("nan")), ("hole_diameter_mm", True),
                           ("distance_from_end_mm", "40"), ("end_reference", "LEFT"),
                           ("enabled", "maybe"), ("connection_group", "../P01")):
            with self.subTest(key=key, value=value):
                rows = input_rows(); rows[0][key] = value
                with self.assertRaises(ValueError): normalize_hole_rows(rows)

    def test_duplicate_hole(self):
        rows = input_rows()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalize_hole_rows([rows[0], deepcopy(rows[0])])

    def test_old_side_xyz_schema_rejected(self):
        for key in ("side", "x_mm", "target_instance"):
            rows = input_rows(); rows[0][key] = "A"
            with self.assertRaises(ValueError): normalize_hole_rows(rows)

    def test_mixed_projects_rejected(self):
        rows = input_rows(); rows[1]["project_id"] = "OTHER"
        with self.assertRaises(ValueError): normalize_hole_rows(rows)

    def test_empty_rows_rejected(self):
        with self.assertRaises(ValueError): normalize_hole_rows([])

    def test_legacy_template_has_two_driving_rows(self):
        with TEMPLATE.open("rb") as handle:
            wb = load_workbook(handle)
            try:
                self.assertEqual(wb.sheetnames, [SHEET_NAME])
                sheet = wb[SHEET_NAME]
                self.assertEqual(sheet.max_row, 3)
                self.assertEqual(tuple(next(sheet.values)), HEADERS)
                for row in (2, 3):
                    self.assertEqual(sheet.cell(row, 2).value, "P01")
                    self.assertEqual(sheet.cell(row, 3).value, "PURLIN_SUPPORT")
                    # This example is user-editable; do not freeze engineering dimensions.
                    for col in (7, 8, 10):
                        value = sheet.cell(row, col).value
                        if value is not None: self.assertGreater(value, 0)
            finally: wb.close()
        with self.assertRaises(ValueError): read_hole_inputs(TEMPLATE)

    def filled_workbook(self, tmp):
        wb = load_workbook(TEMPLATE)
        sheet = wb[SHEET_NAME]
        from cadtocae.hole_inputs import FIELDS
        for index, row in enumerate(input_rows(), 2):
            for col, key in enumerate(FIELDS, 1): sheet.cell(index, col, row[key])
        path = Path(tmp)/"filled.xlsx"
        wb.save(path); wb.close()
        return path

    def test_engineering_excel_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = read_hole_inputs(self.filled_workbook(tmp))
        self.assertEqual([replace(r,source_file='',source_sheet='') for r in rows], normalize_hole_rows(input_rows()))
        self.assertTrue(all(r.source_file and r.source_sheet for r in rows))

    def test_excel_formula_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.filled_workbook(tmp)
            wb = load_workbook(path); wb[SHEET_NAME]["G2"] = "=25*2"; wb.save(path); wb.close()
            with self.assertRaisesRegex(ValueError, "Formulas"): read_hole_inputs(path)

    def test_excel_old_header_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.filled_workbook(tmp)
            wb = load_workbook(path); wb[SHEET_NAME]["G1"] = "x_mm"; wb.save(path); wb.close()
            with self.assertRaisesRegex(ValueError, "headers"): read_hole_inputs(path)
