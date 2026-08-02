from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.assembly import create_coordinate_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the pre-assembly coordinate check workbook.")
    parser.add_argument(
        "--layout",
        default="examples/sp_sc_ang20_coordinate_layout.json",
        help="Coordinate layout JSON.",
    )
    parser.add_argument(
        "--out",
        default="outputs/SP_SC_ANG20_coordinate_check.xlsx",
        help="Output workbook path.",
    )
    parser.add_argument("--tolerance-m", type=float, default=0.001, help="BC/DE length tolerance in meters.")
    parser.add_argument("--angle-tolerance-deg", type=float, default=0.05, help="CE angle tolerance in degrees.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = create_coordinate_workbook(
        args.layout,
        args.out,
        tolerance_m=args.tolerance_m,
        angle_tolerance_deg=args.angle_tolerance_deg,
    )
    print("Wrote coordinate workbook: %s" % Path(output).resolve())


if __name__ == "__main__":
    main()
