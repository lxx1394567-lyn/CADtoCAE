from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.assembly import annotate_coordinates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate an elevation drawing with coordinate control points.")
    parser.add_argument(
        "--layout",
        default="examples/sp_sc_ang20_coordinate_layout.json",
        help="Coordinate layout JSON.",
    )
    parser.add_argument("--image", required=True, help="Source drawing image.")
    parser.add_argument(
        "--out-png",
        default="outputs/SP_SC_ANG20_annotated_coordinates.png",
        help="Output annotated PNG.",
    )
    parser.add_argument(
        "--out-pdf",
        default="outputs/SP_SC_ANG20_annotated_coordinates.pdf",
        help="Output annotated PDF.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = annotate_coordinates(args.layout, args.image, args.out_png, args.out_pdf)
    print("Wrote annotated drawing: %s" % Path(output).resolve())
    if args.out_pdf:
        print("Wrote annotated PDF: %s" % Path(args.out_pdf).resolve())


if __name__ == "__main__":
    main()
