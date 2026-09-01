import unittest
import re

from cadtocae.standards import (
    angle_code,
    component_role,
    component_role_key,
    derive_component_row,
    material_properties,
    normalize_material_grade,
    parse_spec,
    part_name,
    project_prefix,
    support_type_code,
)


class StandardsTest(unittest.TestCase):
    def test_project_prefix_rules(self):
        self.assertEqual(project_prefix("单桩单立柱", "20"), "SP_SC_ANG20")
        self.assertEqual(project_prefix("单桩双立柱", "20"), "SP_DC_ANG20")
        self.assertEqual(project_prefix("双桩", "26.5"), "DP_ANG26P5")
        self.assertEqual(support_type_code("双桩双立柱"), "DP")

    def test_part_name_omits_layout_mark_length_and_quantity(self):
        name = part_name("单桩单立柱", "20", "上立柱")
        self.assertEqual(name, "P_SP_SC_ANG20_COLUMN_UP")
        self.assertIsNone(re.search(r"_M\d+", name))
        self.assertIsNone(re.search(r"_L\d+", name))
        self.assertNotIn("2X7", name)

    def test_component_role_maps_known_component_codes(self):
        cases = {
            "斜梁": "INCLINED_BEAM",
            "上立柱": "COLUMN_UP",
            "下立柱": "COLUMN_DOWN",
            "立柱": "COLUMN",
            "前立柱": "COLUMN_FRONT",
            "后立柱": "COLUMN_REAR",
            "斜撑": "BRACE",
            "前斜撑": "BRACE_FRONT",
            "后斜撑": "BRACE_REAR",
            "檩条": "PURLIN",
            "檩条拼接件": "PURLIN_SPLICE",
            "檩托": "PURLIN_SUPPORT",
            "柱间支撑": "COLUMN_BRACE",
            "柱间支撑连接件": "COLUMN_BRACE_CONNECTOR",
            "斜梁拉杆": "INCLINED_BEAM_TIE_ROD",
            "柱间拉杆": "COLUMN_TIE_ROD",
            "立柱拉杆": "COLUMN_TIE_ROD",
            "水平拉杆": "HORIZONTAL_TIE_ROD",
            "水平拉杆垫脚": "HORIZONTAL_TIE_ROD_PAD",
            "直拉条": "STRAIGHT_TIE_ROD",
            "斜拉条": "DIAGONAL_TIE_ROD",
            "斜撑拉杆": "BRACE_TIE_ROD",
            "预埋钢管": "EMBEDDED_STEEL_PIPE",
            "三角连接件": "TRIANGULAR_CONNECTOR",
            "连接件": "CONNECTOR",
            "抱箍": "HOOP",
            "斜撑抱箍": "BRACE_HOOP",
            "拉杆": "TIE_ROD",
            "边压块": "EDGE_CLAMP",
            "中压块": "MID_CLAMP",
            "背板": "BACK_PLATE",
            "密封圈": "SEAL_RING",
            "U型螺栓": "U_BOLT",
            "M8U型螺栓": "U_BOLT_M8",
            "M8 U型螺栓": "U_BOLT_M8",
            "压块": "PRESS_BLOCK",
            "防水垫圈": "WATERPROOF_GASKET",
        }
        for component_name, expected_code in cases.items():
            with self.subTest(component_name=component_name):
                self.assertEqual(component_role(component_name)["code"], expected_code)

    def test_numbered_component_names_keep_suffix_only_for_known_bases(self):
        cases = {
            "抱箍组合1": "HOOP_ASSEMBLY_1",
            "抱箍组合2": "HOOP_ASSEMBLY_2",
            "抱箍组合3": "HOOP_ASSEMBLY_3",
            "连接件1": "CONNECTOR_1",
            "连接件2": "CONNECTOR_2",
        }
        for component_name, expected_code in cases.items():
            with self.subTest(component_name=component_name):
                self.assertEqual(component_role(component_name)["code"], expected_code)

        self.assertEqual(component_role("未知新构件")["code"], "UNKNOWN_COMPONENT")
        self.assertEqual(component_role("未知新构件1")["code"], "UNKNOWN_COMPONENT")
        self.assertEqual(part_name("双桩双立柱", "35", "未知新构件1"), "P_DP_ANG35_UNKNOWN_COMPONENT")

    def test_numbered_and_front_rear_codes_are_distinct(self):
        self.assertNotEqual(component_role("前立柱")["code"], component_role("后立柱")["code"])
        codes = [component_role("抱箍组合%s" % index)["code"] for index in (1, 2, 3)]
        self.assertEqual(codes, ["HOOP_ASSEMBLY_1", "HOOP_ASSEMBLY_2", "HOOP_ASSEMBLY_3"])
        self.assertEqual(len(set(codes)), 3)

    def test_component_role_alias_is_explicit(self):
        self.assertEqual(component_role_key("柱间拉杆"), "柱间拉杆")
        self.assertEqual(component_role_key("立柱拉杆"), "柱间拉杆")

    def test_decimal_angle_code(self):
        self.assertEqual(angle_code("26.5度"), "ANG26P5")
        self.assertEqual(angle_code("ANG30"), "ANG30")

    def test_parse_common_specs(self):
        c_channel = parse_spec("C75×40×15×2.0")
        self.assertEqual(c_channel.section_type, "C型钢")
        self.assertEqual(c_channel.thickness_mm, 2)
        self.assertEqual(c_channel.section_code, "CX75X40X15X2")

        pipe = parse_spec("Φ127×2.5")
        self.assertEqual(pipe.section_type, "圆管")
        self.assertEqual(pipe.section_params["外径_mm"], 127)
        self.assertEqual(pipe.thickness_mm, 2.5)

        angle = parse_spec("L90×56×5")
        self.assertEqual(angle.section_type, "角钢")
        self.assertEqual(angle.section_params["边长A_mm"], 90)

        hoop = parse_spec("φ140x80x5.0")
        self.assertEqual(hoop.section_type, "抱箍带")
        self.assertEqual(hoop.thickness_mm, 5)

        strut = parse_spec("D24×2.0(Φ10)")
        self.assertEqual(strut.section_type, "套管撑杆")
        self.assertEqual(strut.section_params["内拉杆直径_mm"], 10)

    def test_derive_component_row_flags_missing_fields(self):
        row = {
            "类别": "支架",
            "序号": "13",
            "名称": "柱间拉杆",
            "规格": "Φ10",
            "长度_mm": "",
            "数量": "",
            "备注": "Q235 B",
        }
        component = derive_component_row(row, "单桩单立柱", "20", "2行7列竖向")
        self.assertEqual(component["abaqus_part_name"], "P_SP_SC_ANG20_COLUMN_TIE_ROD")
        self.assertEqual(component["校核状态"], "需人工确认")
        self.assertIn("长度缺失", component["待确认项"])

    def test_material_grade_normalization_for_density_lookup(self):
        cases = [
            ("Q235 B", "Q235B"),
            ("Q355 B", "Q355B"),
            ("S350GD ZM275", "S350GD"),
            ("6063T5", "6063-T5"),
            ("SUS304", "SUS304"),
        ]
        for raw_grade, expected in cases:
            with self.subTest(raw_grade=raw_grade):
                self.assertEqual(normalize_material_grade(raw_grade), expected)

    def test_material_density_mapping_does_not_default_unknowns_to_steel(self):
        for grade in ("Q235B", "Q355B", "Q450B", "S350GD ZM275"):
            with self.subTest(grade=grade):
                self.assertEqual(material_properties(grade)["density_kg_per_m3"], 7850.0)

        unknown = material_properties("SUS304")
        self.assertEqual(unknown["material_grade"], "SUS304")
        self.assertIsNone(unknown["density_kg_per_m3"])

    def test_derive_component_row_adds_mass_and_density_fields(self):
        row = {
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
        }

        component = derive_component_row(row, "单桩双立柱", "28", "2行7列竖向")

        self.assertEqual(component["材料牌号"], "S350GD")
        self.assertEqual(component["材料密度 kg/m³"], 7850.0)
        self.assertEqual(component["构件米重 kg/m"], "2.85")
        self.assertEqual(component["单件质量 kg"], "11.69")
        self.assertEqual(component["总质量 kg"], "46.76")
        self.assertAlmostEqual(component["理论单件质量 kg"], 11.69)
        self.assertAlmostEqual(component["理论总质量 kg"], 46.76)
        self.assertEqual(component["质量校核状态"], "OK")


if __name__ == "__main__":
    unittest.main()
