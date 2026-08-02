from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.workbook import export_abaqus_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Chinese Excel component rows to Abaqus-readable JSON.")
    parser.add_argument("--xlsx", required=True, help="Chinese Excel review workbook.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    parser.add_argument(
        "--selection",
        choices=["approved", "complete"],
        default="approved",
        help="approved: only rows marked 已确认; complete: rows with complete model dimensions.",
    )
    parser.add_argument("--standards", default=str(PROJECT_ROOT / "config" / "standards.json"))
    args = parser.parse_args()

    output = export_abaqus_json(args.xlsx, args.out, args.standards, selection=args.selection)
    print(f"Exported Abaqus input JSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
