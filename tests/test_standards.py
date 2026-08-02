import unittest
import re

from cadtocae.standards import angle_code, derive_component_row, parse_spec, part_name, project_prefix, support_type_code


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


if __name__ == "__main__":
    unittest.main()
