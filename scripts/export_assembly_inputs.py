from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.assembly import export_assembly_inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export checked members for the future Abaqus Assembly script.")
    parser.add_argument(
        "--layout",
        default="examples/sp_sc_ang20_coordinate_layout.json",
        help="Coordinate layout JSON.",
    )
    parser.add_argument(
        "--out",
        default="outputs/SP_SC_ANG20_assembly_inputs.json",
        help="Output Assembly JSON.",
    )
    parser.add_argument("--include-draft", action="store_true", help="Include draft member checks in the JSON.")
    parser.add_argument("--tolerance-m", type=float, default=0.001, help="Member axis length tolerance in meters.")
    parser.add_argument("--control-tolerance-m", type=float, default=0.001, help="BC/DE control length tolerance in meters.")
    parser.add_argument("--angle-tolerance-deg", type=float, default=0.05, help="CE angle tolerance in degrees.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = export_assembly_inputs(
        args.layout,
        args.out,
        include_draft=args.include_draft,
        tolerance_m=args.tolerance_m,
        control_tolerance_m=args.control_tolerance_m,
        angle_tolerance_deg=args.angle_tolerance_deg,
    )
    print("Wrote Assembly inputs: %s" % Path(output).resolve())


if __name__ == "__main__":
    main()
