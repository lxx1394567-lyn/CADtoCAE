from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.material_pdf import (  # noqa: E402
    DEFAULT_ANGLE,
    DEFAULT_LAYOUT,
    DEFAULT_SUPPORT_TYPE,
    SUPPORTED_DOCUMENT_SUFFIXES,
    batch_extract_material_workbooks,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Step01: extract material tables from PNG/JPG screenshots and write Excel workbooks.")
    parser.add_argument("inputs", nargs="*", help="PNG/JPG material table screenshots. If omitted, use --input-dir.")
    parser.add_argument("--input-dir", default=None, help="Folder containing PNG/JPG material table screenshots.")
    parser.add_argument("--pdf-dir", default=None, help="Deprecated alias of --input-dir.")
    parser.add_argument("--recursive", action="store_true", help="Search input folder recursively.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "step01_material_excels"))
    parser.add_argument("--support-type", default=DEFAULT_SUPPORT_TYPE, help="Default support type when auto-detection fails.")
    parser.add_argument("--angle", default=DEFAULT_ANGLE, help="Default angle when auto-detection fails.")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT)
    parser.add_argument("--standards", default=str(PROJECT_ROOT / "config" / "standards.json"))
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR. This normally prevents image recognition.")
    parser.add_argument("--no-auto-project", action="store_true", help="Do not detect support type/angle from image filename/OCR text.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output folders when possible.")
    parser.add_argument("--summary-json", default=None, help="Optional path for batch summary JSON.")
    return parser.parse_args()


def _collect_pdfs(args: argparse.Namespace) -> list[Path]:
    pdfs = [Path(path) for path in args.inputs]
    input_dir = args.input_dir or args.pdf_dir
    if input_dir:
        root = Path(input_dir)
        pattern = "**/*" if args.recursive else "*"
        pdfs.extend(
            path
            for path in sorted(root.glob(pattern))
            if path.is_file() and path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for pdf in pdfs:
        resolved = str(pdf.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(pdf)
    return unique


def main() -> int:
    args = parse_args()
    pdfs = _collect_pdfs(args)
    if not pdfs:
        print("No PNG/JPG material table screenshots selected.")
        return 2

    outputs = batch_extract_material_workbooks(
        pdfs,
        args.output_dir,
        fallback_support_type=args.support_type,
        fallback_angle=args.angle,
        layout=args.layout,
        standards_path=args.standards,
        prefer_detected_project=not args.no_auto_project,
        enable_ocr=not args.no_ocr,
        overwrite=args.overwrite,
    )

    for item in outputs:
        if item.workbook_path:
            print("[%s] %s -> %s" % (item.status, Path(item.pdf_path).name, item.workbook_path))
        else:
            print("[%s] %s -> no workbook" % (item.status, Path(item.pdf_path).name))
            if item.manual_template_path:
                print("      manual template: %s" % item.manual_template_path)
            for message in item.messages:
                print("      %s" % message)

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump([item.to_dict() for item in outputs], handle, ensure_ascii=False, indent=2)
        print("Summary: %s" % summary_path.resolve())

    return 0 if all(item.status == "ok" for item in outputs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
