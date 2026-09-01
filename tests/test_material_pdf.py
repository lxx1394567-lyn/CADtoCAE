from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from PIL import Image, ImageDraw

from cadtocae.material_pdf import (
    OcrToken,
    PdfMaterialResult,
    batch_extract_material_workbooks,
    detect_project_info,
    detect_table_grid,
    looks_like_unreliable_component_name,
    normalize_ocr_component_name,
    normalize_ocr_material_grade,
    normalize_ocr_section_spec,
    parse_angle_from_image_filename,
    preprocess_name_cell_crop,
    rows_from_positioned_words,
    rows_from_tables,
    rows_from_text,
    source_key_from_material_filename,
)
from cadtocae.workbook import create_material_workbook, read_component_rows_for_processing


class MaterialPdfExtractionTest(unittest.TestCase):
    def test_rows_from_headered_pdf_table(self):
        table = [
            ["序号", "名称", "规格", "长度", "数量", "备注"],
            ["1", "斜梁", "C75×40×15×2.0", "3948", "2", "Q355 B"],
            ["2", "上立柱", "Φ127×2.5", "2050", "2", "Q355 B"],
        ]

        rows = rows_from_tables([(1, table)])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["名称"], "斜梁")
        self.assertEqual(rows[0]["规格"], "C75×40×15×2.0")
        self.assertEqual(rows[0]["来源页码"], "1")
        self.assertEqual(rows[0]["构件米重 kg/m"], "")
        self.assertEqual(rows[0]["单位重量 kg"], "")
        self.assertEqual(rows[0]["总重量 kg"], "")

    def test_quality_header_aliases_are_preserved(self):
        cases = [
            (
                ["序号", "名称", "规格", "长度(mm)", "数量", "构件米重", "单位重量", "总重量", "备注"],
                ["1", "斜梁", "C80×40×15×2.0", "4102", "4", "2.85", "11.69", "46.76", "S350GD ZM275"],
            ),
            (
                ["序号", "名称", "规格", "长度(mm)", "数量", "每米重量", "单件重量", "总重", "备注"],
                ["1", "斜梁", "C80×40×15×2.0", "4102", "4", "2.85", "11.69", "46.76", "S350GD ZM275"],
            ),
            (
                ["序号", "名称", "规格", "长度(mm)", "数量", "米重", "单位重量", "总重量", "备注"],
                ["1", "斜梁", "C80×40×15×2.0", "4102", "4", "2.85", "11.69", "46.76", "S350GD ZM275"],
            ),
            (
                ["序号", "名称", "规格", "长度(mm)", "数量", "单位长度重量", "单件重量", "总重量", "备注"],
                ["1", "斜梁", "C80×40×15×2.0", "4102", "4", "2.85", "11.69", "46.76", "S350GD ZM275"],
            ),
        ]

        for header, row in cases:
            with self.subTest(header=header):
                rows = rows_from_tables([(1, [header, row])])
                self.assertEqual(rows[0]["构件米重 kg/m"], "2.85")
                self.assertEqual(rows[0]["单位重量 kg"], "11.69")
                self.assertEqual(rows[0]["总重量 kg"], "46.76")
                self.assertEqual(rows[0]["备注"], "S350GD ZM275")

    def test_length_m_header_is_converted_to_length_mm_only_when_explicit(self):
        rows_from_m = rows_from_tables(
            [
                (
                    1,
                    [
                        ["序号", "名称", "规格", "长度(m)", "数量", "备注"],
                        ["1", "斜梁", "C80×40×15×2.0", "4.102", "4", "S350GD"],
                    ],
                )
            ]
        )
        rows_from_mm = rows_from_tables(
            [
                (
                    1,
                    [
                        ["序号", "名称", "规格", "长度(mm)", "数量", "备注"],
                        ["1", "斜梁", "C80×40×15×2.0", "4102", "4", "S350GD"],
                    ],
                )
            ]
        )

        self.assertEqual(rows_from_m[0]["长度_mm"], "4102")
        self.assertEqual(rows_from_mm[0]["长度_mm"], "4102")

    def test_merged_material_cell_bbox_propagates_within_covered_rows(self):
        verticals = [0, 80, 220, 400, 520, 640, 780]
        horizontals = [0, 40, 80, 120, 160, 200, 240]
        tokens = [
            OcrToken("序号", 20, 10, 30, 16, 96),
            OcrToken("名称", 100, 10, 40, 16, 96),
            OcrToken("规格", 260, 10, 40, 16, 96),
            OcrToken("长度(mm)", 430, 10, 70, 16, 96),
            OcrToken("数量", 560, 10, 40, 16, 96),
            OcrToken("材质", 680, 10, 40, 16, 96),
            OcrToken("S350GD ZM275", 670, 44, 90, 112, 94),
            OcrToken("S550GD ZM275", 670, 164, 90, 72, 94),
        ]
        data_rows = [
            ("1", "斜梁", "C80×40×15×2.0", "4102", "4"),
            ("2", "前立柱", "φ60×2.0", "1811", "5"),
            ("3", "后立柱", "φ60×2.0", "2509", "5"),
            ("4", "檩条", "C90×50×15×1.8", "16326", "4"),
            ("5", "檩托", "L75×50×5", "50", "8"),
        ]
        column_lefts = [20, 100, 260, 430, 560]
        for row_offset, values in enumerate(data_rows, start=1):
            top = row_offset * 40 + 12
            for col_index, value in enumerate(values):
                tokens.append(OcrToken(value, column_lefts[col_index], top, 80, 16, 92))

        rows = rows_from_positioned_words(tokens, verticals, horizontals)

        self.assertEqual([row["备注"] for row in rows[:3]], ["S350GD ZM275"] * 3)
        self.assertEqual([row["备注"] for row in rows[3:]], ["S550GD ZM275"] * 2)

        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "SP_DC_ANG28_components.xlsx"
            create_material_workbook(rows, "单桩双立柱", "28", "2行7列竖向", workbook_path)
            component_rows, _headers = read_component_rows_for_processing(workbook_path)

        self.assertEqual([row["材料牌号"] for row in component_rows[:3]], ["S350GD"] * 3)
        self.assertEqual([row["材料牌号"] for row in component_rows[3:]], ["S550GD"] * 2)

    def test_rows_from_ocr_like_text(self):
        text = "\n".join(
            [
                "材料表",
                "1 斜梁 C75×40×15×2.0 3948 2 Q355 B",
                "2 上立柱 Φ127×2.5 2050 2 Q355 B",
            ]
        )

        rows = rows_from_text([(1, text)])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["名称"], "上立柱")
        self.assertEqual(rows[1]["数量"], "2")

    def test_rows_from_positioned_words_uses_table_grid(self):
        verticals = [0, 100, 200, 400, 650, 820, 950, 1150]
        horizontals = [0, 60, 120, 180]
        tokens = [
            OcrToken("1", 130, 80, 10, 20, 95),
            OcrToken("斜梁", 260, 80, 40, 20, 92),
            OcrToken("C75×40×15×2.0", 470, 80, 120, 20, 90),
            OcrToken("3948", 720, 80, 50, 20, 96),
            OcrToken("2", 880, 80, 10, 20, 97),
            OcrToken("Q355", 1010, 80, 45, 20, 94),
            OcrToken("B", 1060, 80, 10, 20, 94),
            OcrToken("2", 130, 140, 10, 20, 95),
            OcrToken("上立柱", 250, 140, 60, 20, 92),
            OcrToken("Φ127×2.5", 480, 140, 90, 20, 91),
            OcrToken("2050", 720, 140, 50, 20, 96),
            OcrToken("2", 880, 140, 10, 20, 97),
        ]

        rows = rows_from_positioned_words(tokens, verticals, horizontals)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["名称"], "斜梁")
        self.assertEqual(rows[0]["规格"], "C75×40×15×2.0")
        self.assertEqual(rows[0]["长度_mm"], "3948")
        self.assertEqual(rows[0]["备注"], "Q355 B")
        self.assertEqual(rows[1]["名称"], "上立柱")
        self.assertEqual(rows[1]["规格"], "φ127×2.5")

    def test_detect_table_grid_merges_near_duplicate_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "grid.png"
            image = Image.new("RGB", (240, 160), "white")
            draw = ImageDraw.Draw(image)
            for x in [10, 50, 52, 90, 130, 170, 210]:
                draw.line((x, 10, x, 140), fill="black", width=1)
            for y in [10, 50, 90, 130]:
                draw.line((10, y, 210, y), fill="black", width=1)
            image.save(image_path)

            verticals, _horizontals, messages = detect_table_grid(image_path)

        self.assertEqual(len(verticals), 6)
        self.assertTrue(all(right - left > 3 for left, right in zip(verticals, verticals[1:])))
        self.assertTrue(any("竖线近距离重复线过滤" in message for message in messages))

    def test_preprocess_name_cell_crop_scales_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "cell.png"
            image = Image.new("RGB", (80, 40), "white")
            draw = ImageDraw.Draw(image)
            draw.text((16, 12), "abc", fill="black")
            image.save(image_path)
            original_bytes = image_path.read_bytes()

            crop = preprocess_name_cell_crop(image_path, (10, 8, 60, 32), scale=3, padding=8)

            self.assertEqual(crop.mode, "L")
            self.assertGreater(crop.width, 50 * 2)
            self.assertGreater(crop.height, 24 * 2)
            self.assertEqual(image_path.read_bytes(), original_bytes)

    def test_preprocess_name_cell_crop_handles_empty_bbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "cell.png"
            Image.new("RGB", (80, 40), "white").save(image_path)

            crop = preprocess_name_cell_crop(image_path, (20, 20, 20, 25))

        self.assertEqual(crop.size, (3, 3))
        self.assertEqual(crop.mode, "L")

    def test_unreliable_component_name_detects_spec_like_text(self):
        unreliable_names = [
            "",
            "C80×40×15×2.0",
            "L75×50×5",
            "φ300×80×6.0",
            "T=3.0",
            "M10",
            "热镀锌热轧圆钢M10",
        ]
        reliable_names = [
            "斜梁",
            "立柱",
            "前斜撑",
            "后斜撑",
            "檩条",
            "檩托",
            "M8 U型螺栓",
            "横梁连接板",
        ]

        for name in unreliable_names:
            with self.subTest(name=name):
                self.assertTrue(looks_like_unreliable_component_name(name))
        for name in reliable_names:
            with self.subTest(name=name):
                self.assertFalse(looks_like_unreliable_component_name(name))

    def test_missing_name_cell_uses_mocked_secondary_ocr_without_shifting_spec(self):
        verticals = [0, 80, 220, 500, 620, 740, 860]
        horizontals = [0, 40, 90]
        tokens = [
            OcrToken("序号", 20, 10, 30, 14, 96),
            OcrToken("名称", 120, 10, 40, 14, 96),
            OcrToken("规格", 280, 10, 40, 14, 96),
            OcrToken("长度", 540, 10, 40, 14, 96),
            OcrToken("数量", 660, 10, 40, 14, 96),
            OcrToken("材质", 780, 10, 40, 14, 96),
            OcrToken("1", 25, 55, 10, 14, 95),
            OcrToken("热镀锌热轧圆钢M10", 120, 55, 150, 14, 88),
            OcrToken("1200", 540, 55, 40, 14, 96),
            OcrToken("4", 660, 55, 10, 14, 96),
            OcrToken("Q235B", 780, 55, 50, 14, 96),
        ]
        calls: list[tuple[int, int, int, int]] = []

        def fake_name_ocr(bbox: tuple[int, int, int, int]) -> tuple[str, float]:
            calls.append(bbox)
            return "柱间支撑", 88.0

        stats: dict[str, object] = {}
        diagnostics: list[str] = []
        rows = rows_from_positioned_words(
            tokens,
            verticals,
            horizontals,
            name_cell_ocr=fake_name_ocr,
            diagnostics=diagnostics,
            name_ocr_stats=stats,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["名称"], "柱间支撑")
        self.assertEqual(rows[0]["规格"], "热镀锌热轧圆钢M10")
        self.assertEqual(rows[0]["备注"], "Q235B")
        self.assertEqual(calls, [(80, 40, 220, 90)])
        self.assertEqual(stats.get("triggered"), 1)
        self.assertEqual(stats.get("replaced"), 1)
        self.assertTrue(any("名称二次 OCR 替换" in message for message in diagnostics))

    def test_low_confidence_name_cell_uses_more_confident_secondary_ocr(self):
        verticals = [0, 80, 220, 500, 620, 740, 860]
        horizontals = [0, 40, 90]
        tokens = [
            OcrToken("序号", 20, 10, 30, 14, 96),
            OcrToken("名称", 120, 10, 40, 14, 96),
            OcrToken("规格", 280, 10, 40, 14, 96),
            OcrToken("长度", 540, 10, 40, 14, 96),
            OcrToken("数量", 660, 10, 40, 14, 96),
            OcrToken("材质", 780, 10, 40, 14, 96),
            OcrToken("2", 25, 55, 10, 14, 95),
            OcrToken("柱间支橕", 120, 55, 70, 14, 38),
            OcrToken("M10", 280, 55, 40, 14, 93),
            OcrToken("1200", 540, 55, 40, 14, 96),
            OcrToken("4", 660, 55, 10, 14, 96),
            OcrToken("Q235B", 780, 55, 50, 14, 96),
        ]

        rows = rows_from_positioned_words(
            tokens,
            verticals,
            horizontals,
            name_cell_ocr=lambda _bbox: ("柱间支撑", 91.0),
            name_ocr_stats={},
        )

        self.assertEqual(rows[0]["名称"], "柱间支撑")

    def test_reliable_name_does_not_call_secondary_ocr(self):
        verticals = [0, 80, 220, 500, 620, 740, 860]
        horizontals = [0, 40, 90]
        tokens = [
            OcrToken("序号", 20, 10, 30, 14, 96),
            OcrToken("名称", 120, 10, 40, 14, 96),
            OcrToken("规格", 280, 10, 40, 14, 96),
            OcrToken("长度", 540, 10, 40, 14, 96),
            OcrToken("数量", 660, 10, 40, 14, 96),
            OcrToken("材质", 780, 10, 40, 14, 96),
            OcrToken("3", 25, 55, 10, 14, 95),
            OcrToken("前斜撑", 120, 55, 50, 14, 92),
            OcrToken("C55×40×10×2.0", 280, 55, 110, 14, 93),
            OcrToken("2100", 540, 55, 40, 14, 96),
            OcrToken("2", 660, 55, 10, 14, 96),
            OcrToken("Q235B", 780, 55, 50, 14, 96),
        ]

        def fail_if_called(_bbox: tuple[int, int, int, int]) -> tuple[str, float]:
            raise AssertionError("secondary OCR should not run for a reliable name")

        rows = rows_from_positioned_words(tokens, verticals, horizontals, name_cell_ocr=fail_if_called)

        self.assertEqual(rows[0]["名称"], "前斜撑")

    def test_unknown_component_name_is_not_forced_to_candidate(self):
        self.assertEqual(normalize_ocr_component_name("横梁连接板"), "横梁连接板")
        verticals = [0, 80, 220, 500, 620, 740, 860]
        horizontals = [0, 40, 90]
        tokens = [
            OcrToken("序号", 20, 10, 30, 14, 96),
            OcrToken("名称", 120, 10, 40, 14, 96),
            OcrToken("规格", 280, 10, 40, 14, 96),
            OcrToken("长度", 540, 10, 40, 14, 96),
            OcrToken("数量", 660, 10, 40, 14, 96),
            OcrToken("材质", 780, 10, 40, 14, 96),
            OcrToken("4", 25, 55, 10, 14, 95),
            OcrToken("横梁连接板", 120, 55, 80, 14, 92),
            OcrToken("T=5.0", 280, 55, 50, 14, 93),
            OcrToken("2", 660, 55, 10, 14, 96),
            OcrToken("Q235B", 780, 55, 50, 14, 96),
        ]

        rows = rows_from_positioned_words(tokens, verticals, horizontals)

        self.assertEqual(rows[0]["名称"], "横梁连接板")

    def test_normalize_ocr_section_spec_diameter_symbols(self):
        cases = [
            ("φ60×2.0", "φ60×2.0"),
            ("Φ60×2.0", "φ60×2.0"),
            ("Ø60×2.0", "φ60×2.0"),
            ("ø60×2.0", "φ60×2.0"),
            ("∅60×2.0", "φ60×2.0"),
            ("O60×2.0", "φ60×2.0"),
            ("o60×2.0", "φ60×2.0"),
            ("060×2.0", "φ60×2.0"),
            ("φ76×4.0", "φ76×4.0"),
            ("O76×4.0", "φ76×4.0"),
            ("φ10", "φ10"),
            ("010", "φ10"),
            ("C80×40×15×2.0", "C80×40×15×2.0"),
            ("C50×30×15×2.0", "C50×30×15×2.0"),
            ("C90×50×15×1.8", "C90×50×15×1.8"),
        ]

        for raw_spec, expected_spec in cases:
            with self.subTest(raw_spec=raw_spec):
                self.assertEqual(normalize_ocr_section_spec(raw_spec), expected_spec)

    def test_normalize_ocr_section_spec_engineering_font_errors(self):
        cases = [
            ("C8O×40×10×2.O", "C80×40×10×2.0"),
            ("钢管Φ159×3.0", "钢管φ159×3.0"),
            ("钢管O159×3.O", "钢管φ159×3.0"),
            ("钢管0159×3.0", "钢管φ159×3.0"),
            ("C55×40×10×2.O", "C55×40×10×2.0"),
            ("C60×45×15×2.0", "C60×45×15×2.0"),
            ("C100×50×15×2.0", "C100×50×15×2.0"),
            ("C108×55×3.0", "C108×55×3.0"),
            ("L90×56×5.O", "L90×56×5.0"),
            ("热镀锌热轧圆钢M10", "热镀锌热轧圆钢M10"),
            ("T=3.O", "T=3.0"),
            ("L75×50×5", "L75×50×5"),
            ("T=5.0 Φ=180", "T=5.0 φ=180"),
            ("T = 5.O ? = 159", "T=5.0 φ=159"),
            ("L25×2.O", "L25×2.0"),
        ]

        for raw_spec, expected_spec in cases:
            with self.subTest(raw_spec=raw_spec):
                self.assertEqual(normalize_ocr_section_spec(raw_spec), expected_spec)

    def test_normalize_ocr_material_grade_common_errors(self):
        cases = [
            ("Q235B", "Q235B"),
            ("Q235", "Q235"),
            ("Q355 B", "Q355B"),
            ("Q3558", "Q355B"),
            ("0355B", "Q355B"),
            ("O4508", "Q450B"),
            ("Q450B", "Q450B"),
            ("S35OGD", "S350GD"),
            ("S420G0", "S420GD"),
            ("S250GD", "S250GD"),
            ("S350GD ZM275", "S350GD"),
        ]

        for raw_grade, expected_grade in cases:
            with self.subTest(raw_grade=raw_grade):
                self.assertEqual(normalize_ocr_material_grade(raw_grade), expected_grade)

    def test_normalize_ocr_component_name_engineering_candidates(self):
        cases = [
            ("斜梁", "斜梁"),
            ("立柱", "立柱"),
            ("檬条", "檩条"),
            ("標托", "檩托"),
            ("檩条拼接仵", "檩条拼接件"),
            ("柱间支撑连接仵", "柱间支撑连接件"),
            ("抱箍组台1", "抱箍组合1"),
            ("抱菇组合2", "抱箍组合2"),
            ("斜撑抱箍", "斜撑抱箍"),
            ("前斜撑", "前斜撑"),
            ("后斜撑", "后斜撑"),
            ("支架", "支架"),
        ]

        for raw_name, expected_name in cases:
            with self.subTest(raw_name=raw_name):
                self.assertEqual(normalize_ocr_component_name(raw_name), expected_name)

    def test_engineering_font_table_field_postprocess(self):
        table = [
            ["序号", "构件名称", "规格", "材质", "长度", "数量"],
            ["1", "斜粱", "C8O×40×10×2.O", "Q3558", "4000", "5"],
            ["2", "立柱", "钢管O159×3.O", "0355B", "3500", "2"],
            ["3", "前斜撑", "C55×40×10×2.O", "Q235B", "2100", "2"],
            ["4", "后斜撑", "C60×45×15×2.0", "Q235 B", "2600", "2"],
            ["5", "檬条", "C100×50×15×2.0", "Q4508", "6000", "4"],
            ["6", "檩条拼接仵", "C108×55×3.O", "Q450B", "800", "8"],
            ["7", "標托", "L90×56×5.O", "Q235B", "50", "8"],
            ["8", "柱间支撑", "热镀锌热轧圆钢M10", "Q235B", "1200", "4"],
            ["9", "三角连接件", "T=3.O", "Q235B", "", "4"],
            ["10", "柱间支撑连接仵", "L75×50×5", "Q235B", "", "4"],
            ["11", "抱箍组台1", "T=5.0 ?=180", "Q2358", "", "2"],
            ["12", "抱菇组合2", "T=5.O 0=159", "Q235B", "", "2"],
            ["13", "斜拉条", "L25×2.O", "Q235B", "900", "2"],
            ["14", "直拉条", "L25×2.0", "Q235B", "850", "2"],
        ]

        rows = rows_from_tables([(1, table)])

        self.assertEqual(
            [row["名称"] for row in rows],
            [
                "斜梁",
                "立柱",
                "前斜撑",
                "后斜撑",
                "檩条",
                "檩条拼接件",
                "檩托",
                "柱间支撑",
                "三角连接件",
                "柱间支撑连接件",
                "抱箍组合1",
                "抱箍组合2",
                "斜拉条",
                "直拉条",
            ],
        )
        self.assertEqual(
            [row["规格"] for row in rows],
            [
                "C80×40×10×2.0",
                "钢管φ159×3.0",
                "C55×40×10×2.0",
                "C60×45×15×2.0",
                "C100×50×15×2.0",
                "C108×55×3.0",
                "L90×56×5.0",
                "热镀锌热轧圆钢M10",
                "T=3.0",
                "L75×50×5",
                "T=5.0 φ=180",
                "T=5.0 φ=159",
                "L25×2.0",
                "L25×2.0",
            ],
        )
        self.assertEqual(rows[0]["备注"], "Q355B")
        self.assertEqual(rows[4]["备注"], "Q450B")
        self.assertEqual(rows[11]["备注"], "Q235B")

    def test_partial_steel_pipe_name_uses_material_context(self):
        table = [
            ["序号", "构件名称", "规格", "材质", "长度(m)", "数量"],
            ["3", "钢管", "O76×4.0", "Q235B", "0.700", "10"],
        ]

        rows = rows_from_tables([(1, table)])

        self.assertEqual(rows[0]["名称"], "预埋钢管")
        self.assertEqual(rows[0]["规格"], "φ76×4.0")
        self.assertEqual(rows[0]["长度_mm"], "700")

    def test_image_batch_writes_normalized_phi_specs_to_excel(self):
        verticals = [0, 100, 200, 400, 650, 820, 950, 1150]
        row_count = 8
        horizontals = [index * 60 for index in range(row_count + 2)]
        material_rows = [
            ("1", "前立柱", "O60×2.0", "1500", "2", "Q355 B", "φ60×2.0"),
            ("2", "后立柱", "060×2.0", "1800", "2", "Q355 B", "φ60×2.0"),
            ("3", "预埋钢管", "Ø76×4.0", "1200", "2", "Q355 B", "φ76×4.0"),
            ("4", "立柱拉杆", "010", "900", "2", "Q235 B", "φ10"),
            ("5", "斜梁", "C80×40×15×2.0", "3948", "2", "Q355 B", "C80×40×15×2.0"),
            ("6", "前斜撑", "C50×30×15×2.0", "2114", "2", "Q355 B", "C50×30×15×2.0"),
            ("7", "后斜撑", "C50×30×15×2.0", "2916", "2", "Q355 B", "C50×30×15×2.0"),
            ("8", "檩条", "C90×50×15×1.8", "8218", "4", "Q420 B", "C90×50×15×1.8"),
        ]
        tokens: list[OcrToken] = []
        for row_offset, (seq, name, spec, length, quantity, remark, _expected_spec) in enumerate(material_rows, start=1):
            top = row_offset * 60 + 20
            tokens.extend(
                [
                    OcrToken(seq, 130, top, 10, 20, 95),
                    OcrToken(name, 250, top, 70, 20, 92),
                    OcrToken(spec, 470, top, 120, 20, 90),
                    OcrToken(length, 720, top, 50, 20, 96),
                    OcrToken(quantity, 880, top, 10, 20, 97),
                    OcrToken(remark, 1010, top, 65, 20, 94),
                ]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "14-项目A-T0101-单桩单立柱.png"
            image.write_bytes(b"not a real image")
            with (
                patch("cadtocae.material_pdf.detect_table_grid", return_value=(verticals, horizontals, [])),
                patch("cadtocae.material_pdf.ocr_image_tokens", return_value=(tokens, [])),
            ):
                outputs = batch_extract_material_workbooks([image], root / "out")

            self.assertEqual(outputs[0].project_prefix, "SP_SC_ANG14")
            workbook_path = Path(outputs[0].workbook_path or "")
            raw_wb = load_workbook(workbook_path, data_only=False)
            try:
                raw_ws = raw_wb["原始材料表"]
                raw_headers = [cell.value for cell in raw_ws[1]]
                name_col = raw_headers.index("名称") + 1
                spec_col = raw_headers.index("规格") + 1
                raw_specs = {
                    str(raw_ws.cell(row=row_index, column=name_col).value): raw_ws.cell(row=row_index, column=spec_col).value
                    for row_index in range(2, raw_ws.max_row + 1)
                }
                for _seq, name, _spec, _length, _quantity, _remark, expected_spec in material_rows:
                    self.assertEqual(raw_specs[name], expected_spec)
            finally:
                raw_wb.close()

            component_rows, _headers = read_component_rows_for_processing(workbook_path)
            component_specs = {str(row.get("构件名称")): row.get("规格") for row in component_rows}
            for _seq, name, _spec, _length, _quantity, _remark, expected_spec in material_rows:
                self.assertEqual(component_specs[name], expected_spec)

    def test_engineering_material_table_headers_prevent_column_shift(self):
        verticals = [0, 160, 330, 420, 530, 630, 730, 820, 950]
        material_rows = [
            ("前立柱", "O60×2.0", "S350GD", "2.86", "1.811", "5.18", "5", "25.91", "φ60×2.0"),
            ("后立柱", "060×2.0", "S350GD", "2.86", "2.509", "7.18", "5", "35.89", "φ60×2.0"),
            ("预埋钢管", "O76×4.0", "Q235B", "7.10", "0.700", "4.97", "10", "49.70", "φ76×4.0"),
            ("斜梁", "C80×40×15×2.0", "S350GD", "2.86", "4.000", "11.43", "5", "57.14", "C80×40×15×2.0"),
            ("前斜撑", "C50×30×15×2.0", "S250GD", "2.07", "2.080", "4.31", "5", "21.55", "C50×30×15×2.0"),
            ("后斜撑", "C50×30×15×2.0", "S250GD", "2.07", "2.080", "4.31", "5", "21.55", "C50×30×15×2.0"),
            ("檩条", "C90×50×15×1.8", "S420GD", "3.01", "16.326", "49.14", "4", "196.56", "C90×50×15×1.8"),
            ("立柱拉杆", "010", "Q235B", "", "", "", "8", "", "φ10"),
        ]
        horizontals = [index * 60 for index in range(len(material_rows) + 2)]
        column_lefts = [45, 205, 345, 445, 555, 655, 760, 850]
        tokens = [
            OcrToken("构件名称", column_lefts[0], 20, 80, 20, 96),
            OcrToken("规格", column_lefts[1], 20, 50, 20, 96),
            OcrToken("材质", column_lefts[2], 20, 50, 20, 96),
            OcrToken("每米重量(kg/m)", column_lefts[3], 20, 80, 20, 96),
            OcrToken("长度(m)", column_lefts[4], 20, 60, 20, 96),
            OcrToken("单件重量(kg)", column_lefts[5], 20, 80, 20, 96),
            OcrToken("数量", column_lefts[6], 20, 45, 20, 96),
            OcrToken("总重量(kg)", column_lefts[7], 20, 70, 20, 96),
        ]
        for row_offset, values in enumerate(material_rows, start=1):
            top = row_offset * 60 + 20
            for col_index, value in enumerate(values[:8]):
                if value:
                    tokens.append(OcrToken(value, column_lefts[col_index], top, 80, 20, 94))

        rows = rows_from_positioned_words(tokens, verticals, horizontals)

        self.assertEqual([row["名称"] for row in rows], [row[0] for row in material_rows])
        self.assertEqual([row["规格"] for row in rows], [row[8] for row in material_rows])
        self.assertEqual(rows[0]["类别"], "支架")
        self.assertEqual(rows[0]["序号"], "1")
        self.assertEqual(rows[0]["长度_mm"], "1811")
        self.assertEqual(rows[0]["构件米重 kg/m"], "2.86")
        self.assertEqual(rows[0]["单位重量 kg"], "5.18")
        self.assertEqual(rows[0]["总重量 kg"], "25.91")
        self.assertEqual(rows[1]["数量"], "5")
        self.assertEqual(rows[2]["备注"], "Q235B")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "14-平塘-FA03521S-T0104-02-双桩双立柱.png"
            image.write_bytes(b"not a real image")
            with (
                patch("cadtocae.material_pdf.detect_table_grid", return_value=(verticals, horizontals, [])),
                patch("cadtocae.material_pdf.ocr_image_tokens", return_value=(tokens, [])),
            ):
                outputs = batch_extract_material_workbooks([image], root / "out")

            self.assertEqual(outputs[0].project_prefix, "DP_ANG14")
            workbook_path = Path(outputs[0].workbook_path or "")
            raw_wb = load_workbook(workbook_path, data_only=False)
            try:
                raw_ws = raw_wb["原始材料表"]
                raw_headers = [cell.value for cell in raw_ws[1]]
                name_col = raw_headers.index("名称") + 1
                spec_col = raw_headers.index("规格") + 1
                raw_specs = {
                    str(raw_ws.cell(row=row_index, column=name_col).value): raw_ws.cell(row=row_index, column=spec_col).value
                    for row_index in range(2, raw_ws.max_row + 1)
                }
                meter_weight_col = raw_headers.index("构件米重 kg/m") + 1
                unit_weight_col = raw_headers.index("单位重量 kg") + 1
                total_weight_col = raw_headers.index("总重量 kg") + 1
                length_col = raw_headers.index("长度_mm") + 1
                self.assertEqual(raw_ws.cell(row=2, column=length_col).value, "1811")
                self.assertEqual(raw_ws.cell(row=2, column=meter_weight_col).value, "2.86")
                self.assertEqual(raw_ws.cell(row=2, column=unit_weight_col).value, "5.18")
                self.assertEqual(raw_ws.cell(row=2, column=total_weight_col).value, "25.91")
                for name, _spec, _material, _weight, _length, _unit_weight, _quantity, _total, expected_spec in material_rows:
                    self.assertEqual(raw_specs[name], expected_spec)
            finally:
                raw_wb.close()

            component_rows, _headers = read_component_rows_for_processing(workbook_path)
            self.assertEqual({row["构件名称"] for row in component_rows}, {row[0] for row in material_rows})
            component_specs = {str(row.get("构件名称")): row.get("规格") for row in component_rows}
            for name, _spec, _material, _weight, _length, _unit_weight, _quantity, _total, expected_spec in material_rows:
                self.assertEqual(component_specs[name], expected_spec)

    def test_engineering_material_table_fills_missing_names_from_row_context(self):
        verticals = [0, 160, 330, 420, 530, 630, 730, 820, 950]
        material_rows = [
            ("前立柱", "O60×2.0", "S350GD", "2.86", "1.811", "5.18", "5", "25.91", "φ60×2.0"),
            ("后立柱", "O60×2.0", "S350GD", "2.86", "2.509", "7.18", "5", "35.89", "φ60×2.0"),
            ("预埋钢管", "O76×4.0", "Q235B", "7.10", "0.700", "4.97", "10", "49.70", "φ76×4.0"),
            ("斜梁", "C80×40×15×2.0", "S350GD", "2.86", "4.000", "11.43", "5", "57.14", "C80×40×15×2.0"),
            ("前斜撑", "C50×30×15×2.0", "S250GD", "2.07", "2.080", "4.31", "5", "21.55", "C50×30×15×2.0"),
            ("后斜撑", "C50×30×15×2.0", "S250GD", "2.07", "2.080", "4.31", "5", "21.55", "C50×30×15×2.0"),
            ("檩条", "C90×50×15×1.8", "S420GD", "3.01", "16.326", "49.14", "4", "196.56", "C90×50×15×1.8"),
            ("立柱拉杆", "010", "Q235B", "", "", "", "8", "", "φ10"),
        ]
        missing_name_rows = {1, 4, 7, 8}
        horizontals = [index * 60 for index in range(len(material_rows) + 2)]
        column_lefts = [45, 205, 345, 445, 555, 655, 760, 850]
        tokens = [
            OcrToken("构件名称", column_lefts[0], 20, 80, 20, 96),
            OcrToken("规格", column_lefts[1], 20, 50, 20, 96),
            OcrToken("材质", column_lefts[2], 20, 50, 20, 96),
            OcrToken("每米重量(kg/m)", column_lefts[3], 20, 80, 20, 96),
            OcrToken("长度(m)", column_lefts[4], 20, 60, 20, 96),
            OcrToken("单件重量(kg)", column_lefts[5], 20, 80, 20, 96),
            OcrToken("数量", column_lefts[6], 20, 45, 20, 96),
            OcrToken("总重量(kg)", column_lefts[7], 20, 70, 20, 96),
        ]
        for row_offset, values in enumerate(material_rows, start=1):
            top = row_offset * 60 + 20
            for col_index, value in enumerate(values[:8]):
                if col_index == 0 and row_offset in missing_name_rows:
                    continue
                if value:
                    tokens.append(OcrToken(value, column_lefts[col_index], top, 80, 20, 94))

        rows = rows_from_positioned_words(tokens, verticals, horizontals)

        self.assertEqual([row["名称"] for row in rows], [row[0] for row in material_rows])
        self.assertEqual([row["规格"] for row in rows], [row[8] for row in material_rows])
        self.assertEqual(rows[0]["长度_mm"], "1811")

    def test_detect_project_info_uses_filename_and_angle_text(self):
        support_type, angle, prefix, messages = detect_project_info(
            "项目A-双桩.pdf",
            ["光伏板倾角 26.5°"],
            fallback_support_type="单桩单立柱",
            fallback_angle="20",
        )

        self.assertEqual(support_type, "双桩")
        self.assertEqual(angle, "26.5")
        self.assertEqual(prefix, "DP_ANG26P5")
        self.assertTrue(any("识别支架类型" in message for message in messages))

    def test_parse_angle_from_image_filename_examples(self):
        cases = [
            ("14-平塘-FA03521S-T0104-02-双桩双立柱.png", "14"),
            ("17-和县-11042110101187S-T0201-单桩双立柱.png", "17"),
            ("18-洋县-11042210101041S-T0202-单桩单立柱.png", "18"),
            ("21-盱眙-11042410101070S-T0203-单桩双立柱.png", "21"),
            ("28-烟台福山-xxx-单桩双立柱.png", "28"),
            ("33-承德-xxx-单桩单立柱.png", "33"),
            ("35-三一-xxx-双桩双立柱.png", "35"),
            ("12.5-项目A-xxx-单桩单立柱.png", "12.5"),
        ]

        for filename, expected_angle in cases:
            with self.subTest(filename=filename):
                self.assertEqual(parse_angle_from_image_filename(filename), expected_angle)

    def test_source_key_from_material_filename_examples(self):
        cases = [
            ("33-承德-11042310101105Z-04-T0102-单桩单立柱.png", "11042310101105Z-04-T0102"),
            ("14-平塘-FA03521S-T0104-02-双桩双立柱.png", "FA03521S-T0104-02"),
            ("18-洋县-11042210101041S-T0202-单桩单立柱.png", "11042210101041S-T0202"),
            (
                "28-烟台福山-1042110101170S-T0202-支架结构图（管桩）-张国恒-单桩双立柱.png",
                "1042110101170S-T0202",
            ),
            (
                "28-烟台福山-1042110101170S-T0204-支架结构图（灌注桩）-张国恒-单桩单立柱.png",
                "1042110101170S-T0204",
            ),
        ]

        for filename, expected_key in cases:
            with self.subTest(filename=filename):
                self.assertEqual(source_key_from_material_filename(filename), expected_key)

    def test_image_batch_uses_filename_angle_for_prefix_and_excel(self):
        cases = [
            ("14-平塘-FA03521S-T0104-02-双桩双立柱.png", "14", "DP_ANG14", "FA03521S-T0104-02"),
            ("17-和县-11042110101187S-T0201-单桩双立柱.png", "17", "SP_DC_ANG17", "11042110101187S-T0201"),
            ("18-洋县-11042210101041S-T0202-单桩单立柱.png", "18", "SP_SC_ANG18", "11042210101041S-T0202"),
            ("21-盱眙-11042410101070S-T0203-单桩双立柱.png", "21", "SP_DC_ANG21", "11042410101070S-T0203"),
            ("28-烟台福山-xxx-单桩双立柱.png", "28", "SP_DC_ANG28", "XXX"),
            ("33-承德-xxx-单桩单立柱.png", "33", "SP_SC_ANG33", "XXX"),
            ("35-三一-11042410101020S-T0201-双桩双立柱.png", "35", "DP_ANG35", "11042410101020S-T0201"),
        ]
        verticals = [0, 100, 200, 400, 650, 820, 950, 1150]
        horizontals = [0, 60, 120]
        tokens = [
            OcrToken("1", 130, 80, 10, 20, 95),
            OcrToken("斜梁", 260, 80, 40, 20, 92),
            OcrToken("C75×40×15×2.0", 470, 80, 120, 20, 90),
            OcrToken("3948", 720, 80, 50, 20, 96),
            OcrToken("2", 880, 80, 10, 20, 97),
            OcrToken("Q355", 1010, 80, 45, 20, 94),
            OcrToken("B", 1060, 80, 10, 20, 94),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("cadtocae.material_pdf.detect_table_grid", return_value=(verticals, horizontals, [])),
                patch("cadtocae.material_pdf.ocr_image_tokens", return_value=(tokens, [])),
            ):
                for filename, expected_angle, expected_prefix, expected_key in cases:
                    with self.subTest(filename=filename):
                        image = root / filename
                        image.write_bytes(b"not a real image")

                        outputs = batch_extract_material_workbooks([image], root / "out")

                        self.assertEqual(outputs[0].project_prefix, expected_prefix)
                        workbook_path = Path(outputs[0].workbook_path or "")
                        self.assertEqual(workbook_path.name, "%s_%s_components.xlsx" % (expected_prefix, expected_key))
                        self.assertEqual(workbook_path.parent, root / "out")
                        wb = load_workbook(workbook_path, data_only=False)
                        try:
                            ws = wb["建模构件表"]
                            headers = [cell.value for cell in ws[1]]
                            angle_col = headers.index("角度") + 1
                            self.assertEqual(str(ws.cell(row=2, column=angle_col).value), expected_angle)
                        finally:
                            wb.close()
                        rows, _headers = read_component_rows_for_processing(workbook_path)
                        self.assertEqual(rows[0]["角度"], expected_angle)
                        self.assertEqual(rows[0]["abaqus_part_name"], "P_%s_INCLINED_BEAM" % expected_prefix)

            self.assertFalse(any(path.is_dir() for path in (root / "out").iterdir()))

    def test_batch_uses_root_excel_paths_and_deterministic_duplicate_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = [
                root / "33-承德-11042310101105Z-04-T0102-单桩单立柱.png",
                root / "33-承德-11042310101105Z-04-T0102-支架结构图-单桩单立柱.png",
            ]
            for image in images:
                image.write_bytes(b"not a real image")

            result = PdfMaterialResult(
                pdf_path=str(images[0]),
                project_prefix="SP_SC_ANG33",
                support_type="单桩单立柱",
                angle="33",
                rows=[
                    {
                        "类别": "支架",
                        "序号": "1",
                        "名称": "斜梁",
                        "规格": "C80×40×10×2.0",
                        "长度_mm": "4000",
                        "数量": "5",
                        "备注": "Q355 B",
                        "来源页码": "1",
                        "识别置信度": "0.90",
                    }
                ],
                status="ok",
                messages=[],
                used_pages=[1],
                extraction_method="image_ocr_grid",
            )

            with patch("cadtocae.material_pdf.extract_material_table_from_document", return_value=result):
                outputs = batch_extract_material_workbooks(images, root / "out")

            self.assertEqual(
                [Path(output.workbook_path or "").name for output in outputs],
                [
                    "SP_SC_ANG33_11042310101105Z-04-T0102_components.xlsx",
                    "SP_SC_ANG33_11042310101105Z-04-T0102_02_components.xlsx",
                ],
            )
            self.assertEqual({Path(output.workbook_path or "").parent for output in outputs}, {root / "out"})
            self.assertFalse(any(path.is_dir() for path in (root / "out").iterdir()))

    def test_invalid_image_filename_angle_does_not_use_default(self):
        invalid_names = [
            "平塘-14-xxx.png",
            "ANG20-xxx.png",
            "xxx.png",
        ]

        for filename in invalid_names:
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, "无法从文件名读取支架倾角"):
                    parse_angle_from_image_filename(filename)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "平塘-xxx-单桩单立柱.png"
            image.write_bytes(b"not a real image")

            with self.assertRaisesRegex(ValueError, "无法从文件名读取支架倾角"):
                batch_extract_material_workbooks([image], root / "out")
            self.assertFalse(list((root / "out").glob("**/*ANG20*")))

    def test_batch_writes_prefixed_component_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "项目A-单桩双立柱-20度.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            result = PdfMaterialResult(
                pdf_path=str(pdf),
                project_prefix="SP_DC_ANG20",
                support_type="单桩双立柱",
                angle="20",
                rows=[
                    {
                        "类别": "支架",
                        "序号": "1",
                        "名称": "斜梁",
                        "规格": "C75×40×15×2.0",
                        "长度_mm": "3948",
                        "数量": "2",
                        "备注": "Q355 B",
                        "来源页码": "1",
                        "识别置信度": "0.90",
                    }
                ],
                status="ok",
                messages=["识别到材料表行数: 1"],
                used_pages=[1],
                extraction_method="pdf_table",
            )

            with patch("cadtocae.material_pdf.extract_material_table_from_document", return_value=result):
                outputs = batch_extract_material_workbooks([pdf], root / "out")

            self.assertEqual(len(outputs), 1)
            workbook_path = Path(outputs[0].workbook_path or "")
            self.assertEqual(workbook_path.name, "SP_DC_ANG20_A-20_components.xlsx")
            self.assertEqual(workbook_path.parent, root / "out")
            self.assertTrue(workbook_path.exists())

            wb = load_workbook(workbook_path, data_only=False)
            ws = wb["建模构件表"]
            headers = [cell.value for cell in ws[1]]
            part_col = headers.index("abaqus_part_name") + 1
            self.assertTrue(str(ws.cell(2, part_col).value).startswith("="))
            rows, _headers = read_component_rows_for_processing(workbook_path)
            self.assertEqual(rows[0]["abaqus_part_name"], "P_SP_DC_ANG20_INCLINED_BEAM")

    def test_batch_failure_writes_template_without_component_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "项目B-双桩-26.5度.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            result = PdfMaterialResult(
                pdf_path=str(pdf),
                project_prefix="DP_ANG26P5",
                support_type="双桩",
                angle="26.5",
                rows=[],
                status="needs_review",
                messages=["未识别到可用材料表"],
                used_pages=[],
                extraction_method="none",
            )

            with patch("cadtocae.material_pdf.extract_material_table_from_document", return_value=result):
                outputs = batch_extract_material_workbooks([pdf], root / "out")

            self.assertIsNone(outputs[0].workbook_path)
            self.assertTrue(Path(outputs[0].manual_template_path or "").exists())
            self.assertEqual(Path(outputs[0].manual_template_path or "").parent, root / "out")
            self.assertFalse(list((root / "out").glob("**/*_components.xlsx")))
            self.assertIsNone(outputs[0].report_path)
            self.assertFalse(list((root / "out").glob("**/step01_material_recognition_report.json")))


if __name__ == "__main__":
    unittest.main()
