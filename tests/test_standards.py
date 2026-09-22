import unittest
import re

from cadtocae.standards import (
    angle_code,
    component_role,
    component_role_key,
    derive_component_row,
    effective_model_policy,
    has_complete_model_dimensions,
    is_hoop_component_code,
    material_properties,
    normalize_material_grade,
    parse_hoop_spec,
    parse_clamp_spec,
    parse_component_spec,
    parse_simple_c_spec,
    parse_rectangular_washer_spec,
    parse_spec,
    part_name,
    project_prefix,
    section_kind_and_model_params,
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

        brace_channel = parse_spec("C50×30×15×2.0")
        self.assertEqual(brace_channel.section_type, "C型钢")
        self.assertEqual(brace_channel.section_params["高度_mm"], 50)
        self.assertEqual(brace_channel.section_params["翼缘宽_mm"], 30)
        self.assertEqual(brace_channel.section_params["卷边_mm"], 15)
        self.assertEqual(brace_channel.thickness_mm, 2)

        pipe = parse_spec("Φ127×2.5")
        self.assertEqual(pipe.section_type, "圆管")
        self.assertEqual(pipe.section_params["外径_mm"], 127)
        self.assertEqual(pipe.thickness_mm, 2.5)

        angle = parse_spec("L90×56×5")
        self.assertEqual(angle.section_type, "角钢")
        self.assertEqual(angle.section_params["边长A_mm"], 90)

        legacy_three_value_phi = parse_spec("φ140x80x5.0")
        self.assertEqual(legacy_three_value_phi.section_type, "未识别")

        strut = parse_spec("D24×2.0(Φ10)")
        self.assertEqual(strut.section_type, "套管撑杆")
        self.assertEqual(strut.section_params["内拉杆直径_mm"], 10)

    def test_hoop_spec_is_context_ready_and_pipe_spec_is_unchanged(self):
        hoop = parse_hoop_spec("HOOP(D=60,W=40,T=3,L=57,R=117)")
        self.assertEqual(hoop.section_type, "抱箍带")
        self.assertEqual(hoop.section_params["内径_mm"], 60)
        self.assertEqual(hoop.section_params["带宽_mm"], 40)
        self.assertEqual(hoop.section_params["厚度_mm"], 3)
        self.assertEqual(hoop.section_params["左直段_mm"], 57)
        self.assertEqual(hoop.section_params["右直段_mm"], 117)
        self.assertEqual(hoop.section_params["内半径_mm"], 30)
        self.assertEqual(hoop.section_params["外半径_mm"], 33)

        pipe = parse_spec("φ60×2.5")
        self.assertEqual(pipe.section_type, "圆管")
        self.assertEqual(pipe.section_params["外径_mm"], 60)
        self.assertEqual(pipe.section_params["厚度_mm"], 2.5)

    def test_hoop_model_params_are_meters(self):
        kind, params = section_kind_and_model_params(parse_hoop_spec("HOOP(D=60,W=40,T=3,L=57,R=117)"))
        self.assertEqual(kind, "HOOP_BAND")
        self.assertAlmostEqual(params["diameter_m"], 0.06)
        self.assertAlmostEqual(params["inner_radius_m"], 0.03)
        self.assertAlmostEqual(params["outer_radius_m"], 0.033)
        self.assertAlmostEqual(params["width_m"], 0.04)
        self.assertAlmostEqual(params["t_m"], 0.003)
        self.assertAlmostEqual(params["left_extension_m"], 0.057)
        self.assertAlmostEqual(params["right_extension_m"], 0.117)

        _kind, large = section_kind_and_model_params(parse_hoop_spec("HOOP(D=190,W=40,T=6,L=80,R=80)"))
        self.assertAlmostEqual(large["inner_radius_m"], 0.095)
        self.assertAlmostEqual(large["outer_radius_m"], 0.101)
        self.assertAlmostEqual(large["t_m"], 0.006)

    def test_precision_part_specs_keep_component_identity_separate_from_section_kind(self):
        support = parse_component_spec({"构件代码": "PURLIN_SUPPORT", "规格": "L100×63×6.0"})
        self.assertEqual(support.section_params["内根圆角_mm"], 6)
        kind, support_params = section_kind_and_model_params(support)
        self.assertEqual(kind, "ANGLE")
        self.assertAlmostEqual(support_params["inner_root_radius_m"], 0.006)

        splice = parse_simple_c_spec("C106×52×3.0")
        kind, splice_params = section_kind_and_model_params(splice)
        self.assertEqual(kind, "C_CHANNEL_SIMPLE")
        self.assertAlmostEqual(splice_params["h_m"], 0.106)
        self.assertAlmostEqual(splice_params["b_m"], 0.052)
        self.assertAlmostEqual(splice_params["t_m"], 0.003)

        hoop = parse_hoop_spec("HOOP(D=60,W=40,T=3,L=57,R=117,RF=4)")
        self.assertEqual(hoop.section_params["过渡圆角_mm"], 4)
        _kind, hoop_params = section_kind_and_model_params(hoop)
        self.assertAlmostEqual(hoop_params["transition_fillet_m"], 0.004)

    def test_mid_and_edge_clamp_v1_specs_are_distinct(self):
        mid = parse_clamp_spec("MIDCLAMP_V1(L=90,SLOT=9X12,E=15,P=60)", "MID_CLAMP")
        edge = parse_clamp_spec("EDGECLAMP_V1(L=90,SLOT=9X12,E=15,P=60)", "EDGE_CLAMP")
        mid_kind, mid_params = section_kind_and_model_params(mid)
        edge_kind, edge_params = section_kind_and_model_params(edge)
        self.assertEqual(mid_kind, "MID_CLAMP_PROFILE")
        self.assertEqual(edge_kind, "EDGE_CLAMP_PROFILE")
        self.assertNotEqual(mid_kind, edge_kind)
        for params in (mid_params, edge_params):
            self.assertAlmostEqual(params["length_m"], 0.09)
            self.assertAlmostEqual(params["slot_width_m"], 0.009)
            self.assertAlmostEqual(params["slot_length_m"], 0.012)
            self.assertAlmostEqual(params["end_distance_m"], 0.015)
            self.assertAlmostEqual(params["pitch_m"], 0.06)
            self.assertAlmostEqual(params["hole_1_center_m"], 0.015)
            self.assertAlmostEqual(params["hole_2_center_m"], 0.075)

    def test_rectangular_washer_parser_is_reserved_without_auto_model_policy(self):
        parsed = parse_rectangular_washer_spec("RECT_WASHER(L=40,W=20,T=3,HOLE=10)")
        self.assertEqual(parsed.section_type, "矩形垫片")
        self.assertEqual(parsed.section_params["孔径_mm"], 10)
        row = {
            "构件名称": "矩形垫片",
            "构件代码": "RECTANGULAR_WASHER",
            "规格": "RECT_WASHER(L=40,W=20,T=3,HOLE=10)",
            "建模方式": "人工模板",
        }
        self.assertEqual(effective_model_policy(row)[0], "MANUAL_TEMPLATE")

    def test_implemented_precision_parts_force_solid_despite_excel_policy(self):
        rows = [
            {"构件代码": "PURLIN_SUPPORT", "规格": "L100×63×6", "建模方式": "壳单元", "单元类型": "S4R"},
            {"构件代码": "PURLIN_SPLICE", "规格": "C106×52×3", "建模方式": "SHELL", "单元类型": "S4R"},
            {"构件代码": "HOOP", "规格": "HOOP(D=60,W=40,T=3,L=57,R=117,RF=4)", "建模方式": "人工模板"},
            {"构件代码": "MID_CLAMP", "规格": "MIDCLAMP_V1(L=90,SLOT=9X12,E=15,P=60)", "建模方式": ""},
            {"构件代码": "EDGE_CLAMP", "规格": "EDGECLAMP_V1(L=90,SLOT=9X12,E=15,P=60)", "建模方式": "MANUAL_TEMPLATE"},
        ]
        for row in rows:
            self.assertEqual(effective_model_policy(row), ("SOLID", "C3D8R"))

    def test_parseable_hoop_roles_can_override_manual_template(self):
        row = {
            "构件名称": "抱箍组合1",
            "构件代码": "HOOP_ASSEMBLY_1",
            "规格": "HOOP(D=60,W=40,T=3,L=57,R=117)",
            "数量": "2",
            "材料牌号": "Q235B",
            "建模方式": "实体单元",
            "单元类型": "C3D8R",
            "abaqus_part_name": "P_SP_SC_ANG20_HOOP_ASSEMBLY_1",
        }

        self.assertTrue(is_hoop_component_code("HOOP_ASSEMBLY_1"))
        self.assertTrue(is_hoop_component_code("BRACE_HOOP"))
        self.assertEqual(effective_model_policy(row), ("SOLID", "C3D8R"))
        complete, issues = has_complete_model_dimensions(row)
        self.assertTrue(complete, issues)

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
