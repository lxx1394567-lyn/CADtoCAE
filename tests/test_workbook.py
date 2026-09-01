from pathlib import Path
import json
import tempfile
import unittest

from openpyxl import load_workbook

from cadtocae.standards import component_role, load_standards
from cadtocae import workbook as workbook_module
from cadtocae.workbook import (
    COMPONENT_HEADERS,
    RAW_HEADERS,
    create_material_workbook,
    export_abaqus_json,
    read_component_rows_for_processing,
    read_raw_material_csv,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkbookTest(unittest.TestCase):
    def test_create_material_workbook(self):
        raw_rows = read_raw_material_csv(ROOT / "examples" / "single_pile_single_column_2x7_raw_materials.csv")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test_components.xlsx"
            create_material_workbook(
                raw_rows,
                support_type="单桩单立柱",
                angle="20",
                array_layout="2行7列竖向",
                output_path=output,
            )

            wb = load_workbook(output, data_only=False)
            resolved_rows, _headers = read_component_rows_for_processing(output)
        self.assertEqual(wb.sheetnames, ["原始材料表", "建模构件表"])

        raw_ws = wb["原始材料表"]
        raw_headers = [cell.value for cell in raw_ws[1]]
        self.assertEqual(raw_headers, RAW_HEADERS)
        self.assertEqual(raw_ws.cell(row=4, column=raw_headers.index("备注") + 1).value, "Q355 B")

        component_ws = wb["建模构件表"]
        headers = [cell.value for cell in component_ws[1]]
        self.assertEqual(headers, COMPONENT_HEADERS)
        part_name_col = headers.index("abaqus_part_name") + 1
        name_col = headers.index("构件名称") + 1
        self.assertEqual(part_name_col, name_col + 1)
        self.assertIn("'原始材料表'!C2", component_ws.cell(row=2, column=name_col).value)
        self.assertTrue(str(component_ws.cell(row=2, column=part_name_col).value).startswith("="))
        self.assertIn("INCLINED_BEAM", component_ws.cell(row=2, column=part_name_col).value)
        self.assertEqual(resolved_rows[0]["abaqus_part_name"], "P_SP_SC_ANG20_INCLINED_BEAM")
        self.assertNotIn("构件代码", headers)
        self.assertNotIn("是否重点分析", headers)
        self.assertNotIn("校核状态", headers)
        self.assertNotIn("Step02建模提示", headers)

        spec_col = headers.index("规格") + 1
        length_col = headers.index("长度_mm") + 1
        length_m_col = headers.index("长度_m") + 1
        material_col = headers.index("材料牌号") + 1
        model_policy_col = headers.index("建模方式") + 1
        self.assertIn("'原始材料表'!D2", component_ws.cell(row=2, column=spec_col).value)
        self.assertIn("/1000", component_ws.cell(row=2, column=length_m_col).value)
        self.assertIn("Q355B", component_ws.cell(row=2, column=material_col).value)
        self.assertIn("'原始材料表'!J2", component_ws.cell(row=2, column=material_col).value)
        self.assertEqual(component_ws.cell(row=1, column=spec_col).fill.fgColor.rgb, "FFC00000")
        self.assertIn("Step02", component_ws.cell(row=1, column=spec_col).comment.text)
        self.assertEqual(component_ws.cell(row=12, column=length_col).fill.fgColor.rgb, "FFFFC7CE")
        self.assertIn("长度", component_ws.cell(row=12, column=length_col).comment.text)
        self.assertEqual(component_ws.cell(row=15, column=model_policy_col).fill.fgColor.rgb, "FFFFC7CE")
        self.assertIn("人工模板", component_ws.cell(row=15, column=model_policy_col).comment.text)

    def test_export_approved_components_json(self):
        raw_rows = read_raw_material_csv(ROOT / "examples" / "single_pile_single_column_2x7_raw_materials.csv")
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "test_components_approved.xlsx"
            create_material_workbook(
                raw_rows,
                support_type="单桩单立柱",
                angle="20",
                array_layout="2行7列竖向",
                output_path=workbook_path,
            )

            wb = load_workbook(workbook_path)
            ws = wb["建模构件表"]
            status_col = ws.max_column + 1
            ws.cell(row=1, column=status_col).value = "校核状态"
            ws.cell(row=2, column=status_col).value = "已确认"
            wb.save(workbook_path)

            json_path = Path(tmp) / "test_abaqus_components.json"
            export_abaqus_json(workbook_path, json_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["components"]), 1)
        self.assertEqual(payload["components"][0]["part_name"], "P_SP_SC_ANG20_INCLINED_BEAM")

    def test_export_complete_components_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "SP_SC_ANG20_components.xlsx"
            raw_rows = read_raw_material_csv(ROOT / "examples" / "single_pile_single_column_2x7_raw_materials.csv")
            create_material_workbook(
                raw_rows,
                support_type="单桩单立柱",
                angle="20",
                array_layout="2行7列竖向",
                output_path=workbook_path,
            )
            json_path = Path(tmp) / "test_complete_components.json"
            export_abaqus_json(workbook_path, json_path, selection="complete")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        names = {component["part_name"] for component in payload["components"]}
        self.assertIn("P_SP_SC_ANG20_INCLINED_BEAM", names)
        self.assertIn("P_SP_SC_ANG20_HOOP", names)
        self.assertIn("P_SP_SC_ANG20_TIE_ROD", names)
        self.assertNotIn("P_SP_SC_ANG20_U_BOLT", names)
        self.assertNotIn("P_SP_SC_ANG20_PRESS_BLOCK", names)
        tie_rod = next(component for component in payload["components"] if component["part_name"] == "P_SP_SC_ANG20_TIE_ROD")
        self.assertEqual(tie_rod["model_policy"], "SOLID")
        self.assertEqual(tie_rod["component_code"], "TIE_ROD")
        inclined = next(component for component in payload["components"] if component["part_name"] == "P_SP_SC_ANG20_INCLINED_BEAM")
        self.assertEqual(inclined["length_m"], 3.948)
        self.assertEqual(inclined["thickness_m"], 0.002)
        self.assertEqual(inclined["section_params_m"]["h_m"], 0.075)
        self.assertEqual(inclined["material"]["density_kg_per_m3"], 7850.0)

    def test_workbook_preserves_raw_mass_columns_and_adds_model_mass_fields(self):
        raw_rows = [
            {
                "类别": "支架",
                "序号": "1",
                "名称": "斜梁",
                "规格": "C80×40×15×2.0",
                "长度_mm": "4102",
                "数量": "4",
                "构件米重 kg/m": "2.85",
                "单位重量 kg": "11.69",
                "总重量 kg": "46.76",
                "备注": "S350GD ZM275",
                "来源页码": "1",
                "识别置信度": "0.99",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "SP_DC_ANG28_components.xlsx"
            create_material_workbook(
                raw_rows,
                support_type="单桩双立柱",
                angle="28",
                array_layout="2行7列竖向",
                output_path=workbook_path,
            )

            wb = load_workbook(workbook_path, data_only=False)
            raw_ws = wb["原始材料表"]
            raw_headers = [cell.value for cell in raw_ws[1]]
            self.assertEqual(raw_ws.cell(row=2, column=raw_headers.index("构件米重 kg/m") + 1).value, "2.85")
            self.assertEqual(raw_ws.cell(row=2, column=raw_headers.index("单位重量 kg") + 1).value, "11.69")
            self.assertEqual(raw_ws.cell(row=2, column=raw_headers.index("总重量 kg") + 1).value, "46.76")
            self.assertEqual(raw_ws.cell(row=2, column=raw_headers.index("备注") + 1).value, "S350GD ZM275")
            wb.close()

            component_rows, headers = read_component_rows_for_processing(workbook_path)

        self.assertIn("材料密度 kg/m³", headers)
        self.assertIn("质量校核状态", headers)
        component = component_rows[0]
        self.assertEqual(component["材料牌号"], "S350GD")
        self.assertEqual(component["材料密度 kg/m³"], 7850.0)
        self.assertEqual(component["构件米重 kg/m"], "2.85")
        self.assertEqual(component["单件质量 kg"], "11.69")
        self.assertEqual(component["总质量 kg"], "46.76")
        self.assertAlmostEqual(component["理论单件质量 kg"], 11.69)
        self.assertAlmostEqual(component["理论总质量 kg"], 46.76)
        self.assertEqual(component["质量校核状态"], "OK")

    def test_workbook_leaves_unknown_material_density_blank(self):
        raw_rows = [
            {
                "类别": "支架",
                "序号": "1",
                "名称": "斜梁",
                "规格": "C80×40×15×2.0",
                "长度_mm": "4102",
                "数量": "4",
                "备注": "SUS304",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "SP_DC_ANG28_components.xlsx"
            create_material_workbook(raw_rows, "单桩双立柱", "28", "2行7列竖向", workbook_path)
            component_rows, _headers = read_component_rows_for_processing(workbook_path)

        self.assertEqual(component_rows[0]["材料牌号"], "SUS304")
        self.assertIn(component_rows[0]["材料密度 kg/m³"], (None, ""))

    def test_export_uses_step01_section_columns_when_spec_needs_manual_parse(self):
        raw_rows = read_raw_material_csv(ROOT / "examples" / "single_pile_single_column_2x7_raw_materials.csv")
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "SP_SC_ANG20_components.xlsx"
            create_material_workbook(
                raw_rows,
                support_type="单桩单立柱",
                angle="20",
                array_layout="2行7列竖向",
                output_path=workbook_path,
            )

            wb = load_workbook(workbook_path)
            ws = wb["建模构件表"]
            headers = [cell.value for cell in ws[1]]
            header_to_col = {header: index + 1 for index, header in enumerate(headers)}
            ws.cell(row=2, column=header_to_col["规格"]).value = "CUSTOM_C_CHANNEL"
            ws.cell(row=2, column=header_to_col["截面类型"]).value = "C型钢"
            ws.cell(row=2, column=header_to_col["截面参数"]).value = "高度_mm=75; 翼缘宽_mm=40; 卷边_mm=15; 厚度_mm=2"
            ws.cell(row=2, column=header_to_col["厚度_mm"]).value = 2
            status_col = ws.max_column + 1
            ws.cell(row=1, column=status_col).value = "校核状态"
            ws.cell(row=2, column=status_col).value = "已确认"
            wb.save(workbook_path)

            json_path = Path(tmp) / "components.json"
            export_abaqus_json(workbook_path, json_path, selection="approved")
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        component = payload["components"][0]
        self.assertEqual(component["section_kind"], "C_CHANNEL")
        self.assertEqual(component["section_params_m"]["h_m"], 0.075)
        self.assertEqual(component["section_params_m"]["b_m"], 0.04)
        self.assertEqual(component["section_params_m"]["lip_m"], 0.015)
        self.assertEqual(component["thickness_m"], 0.002)

    def test_workbook_component_codes_cover_new_naming_map(self):
        expected_codes = {
            "立柱": "COLUMN",
            "前立柱": "COLUMN_FRONT",
            "后立柱": "COLUMN_REAR",
            "柱间支撑": "COLUMN_BRACE",
            "柱间支撑连接件": "COLUMN_BRACE_CONNECTOR",
            "斜梁拉杆": "INCLINED_BEAM_TIE_ROD",
            "立柱拉杆": "COLUMN_TIE_ROD",
            "水平拉杆": "HORIZONTAL_TIE_ROD",
            "水平拉杆垫脚": "HORIZONTAL_TIE_ROD_PAD",
            "直拉条": "STRAIGHT_TIE_ROD",
            "斜拉条": "DIAGONAL_TIE_ROD",
            "斜撑拉杆": "BRACE_TIE_ROD",
            "拉杆": "TIE_ROD",
            "预埋钢管": "EMBEDDED_STEEL_PIPE",
            "三角连接件": "TRIANGULAR_CONNECTOR",
            "连接件1": "CONNECTOR_1",
            "斜撑抱箍": "BRACE_HOOP",
            "抱箍组合1": "HOOP_ASSEMBLY_1",
            "抱箍组合2": "HOOP_ASSEMBLY_2",
            "抱箍组合3": "HOOP_ASSEMBLY_3",
            "边压块": "EDGE_CLAMP",
            "中压块": "MID_CLAMP",
            "背板": "BACK_PLATE",
            "密封圈": "SEAL_RING",
            "M8 U型螺栓": "U_BOLT_M8",
            "未知新构件1": "UNKNOWN_COMPONENT",
        }
        raw_rows = [
            {
                "类别": "支架",
                "序号": str(index),
                "名称": component_name,
                "规格": "C80×40×15×2.0",
                "长度_mm": "1000",
                "数量": "1",
                "备注": "Q235B",
            }
            for index, component_name in enumerate(expected_codes, start=1)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "DP_ANG35_components.xlsx"
            create_material_workbook(raw_rows, "双桩双立柱", "35", "2行7列竖向", workbook_path)
            rows, _headers = read_component_rows_for_processing(workbook_path)

            wb = load_workbook(workbook_path, data_only=False)
            ws = wb["建模构件表"]
            headers = [cell.value for cell in ws[1]]
            part_col = headers.index("abaqus_part_name") + 1
            formula = str(ws.cell(row=2, column=part_col).value)
            wb.close()

        by_name = {str(row["构件名称"]): row for row in rows}
        for component_name, expected_code in expected_codes.items():
            with self.subTest(component_name=component_name):
                row = by_name[component_name]
                self.assertEqual(row["abaqus_part_name"], "P_DP_ANG35_%s" % expected_code)
                self.assertEqual(component_role(component_name)["code"], expected_code)

        self.assertIn("COLUMN_FRONT", formula)
        self.assertIn("HOOP_ASSEMBLY", formula)
        self.assertIn("UNKNOWN_COMPONENT", formula)

    def test_component_role_formula_uses_same_config_entries_as_python(self):
        standards = load_standards()
        formula = workbook_module._component_role_expr("D2", standards, "code", "UNKNOWN_COMPONENT")
        for component_name in ("前立柱", "后立柱", "抱箍组合1", "连接件1", "M8 U型螺栓", "未知新构件1"):
            expected_code = component_role(component_name, standards)["code"]
            with self.subTest(component_name=component_name):
                if component_name in {"抱箍组合1", "连接件1"}:
                    self.assertIn(expected_code.rsplit("_", 1)[0], formula)
                else:
                    self.assertIn(expected_code, formula)

    def test_workbook_marks_unexpected_part_name_collision(self):
        standards = load_standards()
        standards["component_roles"]["后立柱"]["code"] = standards["component_roles"]["前立柱"]["code"]
        raw_rows = [
            {"类别": "支架", "序号": "1", "名称": "前立柱", "规格": "φ60×2.0", "长度_mm": "1000", "数量": "1", "备注": "Q235B"},
            {"类别": "支架", "序号": "2", "名称": "后立柱", "规格": "φ60×2.0", "长度_mm": "1000", "数量": "1", "备注": "Q235B"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            standards_path = Path(tmp) / "standards.json"
            standards_path.write_text(json.dumps(standards, ensure_ascii=False), encoding="utf-8")
            workbook_path = Path(tmp) / "DP_ANG35_components.xlsx"
            create_material_workbook(raw_rows, "双桩双立柱", "35", "2行7列竖向", workbook_path, standards_path)

            wb = load_workbook(workbook_path, data_only=False)
            ws = wb["建模构件表"]
            headers = [cell.value for cell in ws[1]]
            part_col = headers.index("abaqus_part_name") + 1
            comment_text = ws.cell(row=2, column=part_col).comment.text
            wb.close()

        self.assertIn("不同构件名称生成相同 Abaqus Part 名称", comment_text)
        self.assertIn("前立柱", comment_text)
        self.assertIn("后立柱", comment_text)

    def test_configured_alias_does_not_raise_part_name_collision(self):
        raw_rows = [
            {"类别": "支架", "序号": "1", "名称": "柱间拉杆", "规格": "φ10", "长度_mm": "1000", "数量": "1", "备注": "Q235B"},
            {"类别": "支架", "序号": "2", "名称": "立柱拉杆", "规格": "φ10", "长度_mm": "1000", "数量": "1", "备注": "Q235B"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "DP_ANG35_components.xlsx"
            create_material_workbook(raw_rows, "双桩双立柱", "35", "2行7列竖向", workbook_path)

            wb = load_workbook(workbook_path, data_only=False)
            ws = wb["建模构件表"]
            headers = [cell.value for cell in ws[1]]
            part_col = headers.index("abaqus_part_name") + 1
            comments = [
                ws.cell(row=row_index, column=part_col).comment.text
                for row_index in (2, 3)
                if ws.cell(row=row_index, column=part_col).comment
            ]
            rows, _headers = read_component_rows_for_processing(workbook_path)
            wb.close()

        self.assertEqual({row["abaqus_part_name"] for row in rows}, {"P_DP_ANG35_COLUMN_TIE_ROD"})
        self.assertFalse(any("不同构件名称生成相同 Abaqus Part 名称" in text for text in comments))


if __name__ == "__main__":
    unittest.main()
