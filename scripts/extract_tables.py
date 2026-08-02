from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.pdf_tables import (
    create_manual_table_template,
    extract_selectable_text,
    pdf_has_selectable_text,
    render_pdf_pages,
)
from cadtocae.workbook import create_material_workbook, read_raw_material_csv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="材料表提取入口。当前版本支持手工校核 CSV 生成 Excel，并预留 PDF OCR 接口。"
    )
    parser.add_argument("--pdf", help="参考图纸 PDF。")
    parser.add_argument("--manual-csv", help="已录入或人工校核后的材料表 CSV。")
    parser.add_argument("--out", required=True, help="输出 xlsx 路径。")
    parser.add_argument("--support-type", required=True, help="支架类型，例如 单桩单立柱。")
    parser.add_argument("--angle", required=True, help="角度，例如 20 或 ANG20。")
    parser.add_argument("--layout", default="", help="阵列布置，仅写入 Excel，不进入 Part 名称。")
    parser.add_argument("--render-dir", default=str(PROJECT_ROOT / "outputs" / "pdf_pages"))
    parser.add_argument("--manual-template", default=str(PROJECT_ROOT / "outputs" / "manual_material_table_template.csv"))
    parser.add_argument("--template-rows", type=int, default=14)
    args = parser.parse_args()

    if args.manual_csv:
        raw_rows = read_raw_material_csv(args.manual_csv)
        output = create_material_workbook(raw_rows, args.support_type, args.angle, args.layout, args.out)
        print(f"已根据人工材料表生成 Excel 审核表: {output}")
        return 0

    if not args.pdf:
        parser.error("必须提供 --manual-csv 或 --pdf。")

    pdf_path = Path(args.pdf)
    selectable = pdf_has_selectable_text(pdf_path)
    if selectable:
        texts = extract_selectable_text(pdf_path)
        chars = sum(len(text) for text in texts)
        print(f"PDF 有可选文本，共 {chars} 字符；当前版本仍建议人工复核材料表。")
    else:
        print("PDF 未检测到可选文本；当前版本不会猜测 OCR 结果。")

    try:
        rendered = render_pdf_pages(pdf_path, args.render_dir)
        print("已渲染页面供人工/OCR复核:")
        for path in rendered:
            print(f"  {path}")
    except Exception as exc:
        print(f"页面渲染未完成: {exc}")

    template = create_manual_table_template(args.manual_template, rows=args.template_rows)
    print(f"已生成手工录入模板: {template}")
    print("填写模板后，使用 --manual-csv 重新运行即可生成中文 Excel 审核表。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
