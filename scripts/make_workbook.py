from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.workbook import create_material_workbook, read_raw_material_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="从材料表 CSV 生成中文 Excel 审核表。")
    parser.add_argument("--csv", required=True, help="原始材料表 CSV，字段使用中文表头。")
    parser.add_argument("--out", required=True, help="输出 xlsx 路径。")
    parser.add_argument("--support-type", required=True, help="支架类型，例如 单桩单立柱。")
    parser.add_argument("--angle", required=True, help="角度，例如 20 或 ANG20。")
    parser.add_argument("--layout", default="", help="阵列布置，仅写入 Excel，不进入 Part 名称。")
    parser.add_argument("--standards", default=str(PROJECT_ROOT / "config" / "standards.json"))
    args = parser.parse_args()

    raw_rows = read_raw_material_csv(args.csv)
    output = create_material_workbook(
        raw_rows=raw_rows,
        support_type=args.support_type,
        angle=args.angle,
        array_layout=args.layout,
        output_path=args.out,
        standards_path=args.standards,
    )
    print(f"已生成 Excel 审核表: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
