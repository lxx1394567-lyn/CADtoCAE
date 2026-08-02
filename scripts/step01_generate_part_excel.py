from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.runs import create_run_paths, update_manifest
from cadtocae.standards import project_prefix
from cadtocae.workbook import create_material_workbook, read_raw_material_csv
from cadtocae.material_pdf import extract_material_table_from_pdf


def _read_ocr_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    rows = payload.get("rows") or payload.get("materials") or payload.get("raw_rows")
    if isinstance(rows, list):
        return rows
    raise ValueError("OCR JSON must be a list, or contain rows/materials/raw_rows.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step01: generate Abaqus Part modeling Excel from the support material table.")
    parser.add_argument("--manual-csv", default=None, help="Manual or OCR-checked material table CSV.")
    parser.add_argument("--ocr-json", default=None, help="Structured OCR result JSON containing material rows.")
    parser.add_argument("--pdf", default=None, help="Reference drawing PDF path. Scanned PDFs need OCR/CSV for material rows.")
    parser.add_argument("--support-type", default="单桩单立柱")
    parser.add_argument("--angle", default="20")
    parser.add_argument("--layout", default="2行7列竖向")
    parser.add_argument("--project-prefix", "--project-code", dest="project_prefix", default=None)
    parser.add_argument("--standards", default=str(PROJECT_ROOT / "config" / "standards.json"))
    parser.add_argument("--outputs-root", default="outputs")
    parser.add_argument("--run-dir", default=None, help="Run directory. Use 'latest' to reuse the latest run.")
    parser.add_argument("--out", default=None, help="Optional workbook path. Defaults to run_dir/workbooks/<project_prefix>_components.xlsx.")
    parser.add_argument("--render-dir", default=None, help="Optional PDF render output directory for manual/OCR review.")
    parser.add_argument("--manual-template", default=None, help="Optional manual material table CSV template path.")
    parser.add_argument("--no-ocr", action="store_true", help="Do not try external OCR when PDF table text is not directly readable.")
    parser.add_argument("--no-auto-project", action="store_true", help="Do not auto-detect support type and angle from PDF name/text.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prefix = args.project_prefix or project_prefix(args.support_type, args.angle, args.standards)

    warnings: list[str] = []
    errors: list[str] = []
    template_path = None
    rendered_pages: list[str] = []
    input_kind = ""
    raw_rows: list[dict[str, Any]] = []
    support_type = args.support_type
    angle = args.angle

    if args.manual_csv:
        raw_rows = read_raw_material_csv(args.manual_csv)
        input_kind = "manual_csv"
    elif args.ocr_json:
        raw_rows = _read_ocr_rows(args.ocr_json)
        input_kind = "ocr_json"
    elif args.pdf:
        pdf_result = extract_material_table_from_pdf(
            args.pdf,
            fallback_support_type=args.support_type,
            fallback_angle=args.angle,
            layout=args.layout,
            standards_path=args.standards,
            prefer_detected_project=not args.no_auto_project,
            enable_ocr=not args.no_ocr,
        )
        warnings.extend(pdf_result.messages)
        raw_rows = pdf_result.rows
        input_kind = pdf_result.extraction_method
        support_type = pdf_result.support_type
        angle = pdf_result.angle
        if not args.project_prefix:
            prefix = pdf_result.project_prefix

    run_paths = create_run_paths(prefix, args.outputs_root, args.run_dir)
    output = Path(args.out) if args.out else run_paths.workbooks / ("%s_components.xlsx" % prefix)

    if not raw_rows:
        if args.pdf:
            try:
                from cadtocae.pdf_tables import create_manual_table_template, pdf_has_selectable_text, render_pdf_pages

                render_dir = Path(args.render_dir) if args.render_dir else run_paths.previews / "pdf_pages"
                try:
                    rendered_pages = [str(path.resolve()) for path in render_pdf_pages(args.pdf, render_dir)]
                except Exception as exc:
                    warnings.append("PDF page rendering failed: %s" % exc)
                if pdf_has_selectable_text(args.pdf):
                    warnings.append("PDF has selectable text, but no material table rows matched the supported rules.")
                else:
                    warnings.append("PDF has no selectable text rows; OCR or manual CSV is required.")
                manual_template = Path(args.manual_template) if args.manual_template else run_paths.workbooks / "manual_material_table_template.csv"
                template_path = create_manual_table_template(manual_template)
            except Exception as exc:
                errors.append("PDF inspection/template generation failed: %s" % exc)
        else:
            errors.append("Provide --manual-csv, --ocr-json, or --pdf.")

        update_manifest(
            run_paths,
            prefix,
            "step01_part_excel",
            inputs={
                "manual_csv": str(Path(args.manual_csv).resolve()) if args.manual_csv else None,
                "ocr_json": str(Path(args.ocr_json).resolve()) if args.ocr_json else None,
                "pdf": str(Path(args.pdf).resolve()) if args.pdf else None,
                "input_kind": input_kind,
                "support_type": support_type,
                "angle": angle,
                "layout": args.layout,
                "standards": str(Path(args.standards).resolve()),
            },
            outputs={
                "workbooks": {"manual_template": str(Path(template_path).resolve()) if template_path else None},
                "previews": {"pdf_pages": rendered_pages},
            },
            warnings=warnings,
            errors=errors,
            metadata={"support_type": support_type, "angle": angle, "status": "partial"},
        )
        print("Run directory: %s" % run_paths.root.resolve())
        if template_path:
            print("Wrote manual material table template: %s" % Path(template_path).resolve())
        for warning in warnings:
            print("Warning: %s" % warning)
        for error in errors:
            print("Error: %s" % error)
        return 2

    workbook = create_material_workbook(
        raw_rows=raw_rows,
        support_type=support_type,
        angle=angle,
        array_layout=args.layout,
        output_path=output,
        standards_path=args.standards,
    )

    update_manifest(
        run_paths,
        prefix,
        "step01_part_excel",
        inputs={
            "manual_csv": str(Path(args.manual_csv).resolve()) if args.manual_csv else None,
            "ocr_json": str(Path(args.ocr_json).resolve()) if args.ocr_json else None,
            "pdf": str(Path(args.pdf).resolve()) if args.pdf else None,
            "input_kind": input_kind,
            "support_type": support_type,
            "angle": angle,
            "layout": args.layout,
            "standards": str(Path(args.standards).resolve()),
        },
        outputs={"workbooks": {"components": str(Path(workbook).resolve())}},
        metadata={"support_type": support_type, "angle": angle},
    )

    print("Run directory: %s" % run_paths.root.resolve())
    print("Wrote Part modeling Excel: %s" % Path(workbook).resolve())
    print("Manifest: %s" % run_paths.manifest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
