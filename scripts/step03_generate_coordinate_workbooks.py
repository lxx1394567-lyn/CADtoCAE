from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.coordinate_workbooks import create_coordinate_formula_workbooks, write_coordinate_layout_template
from cadtocae.runs import create_run_paths, update_manifest
from cadtocae.standards import project_prefix


def _prefix_from_latest(outputs_root: str | Path) -> str | None:
    latest = Path(outputs_root) / "latest_run_manifest.json"
    if not latest.exists():
        return None
    payload = json.loads(latest.read_text(encoding="utf-8"))
    return payload.get("project_prefix") or payload.get("project_code")


def _copy_input_file(source: Path, target_dir: Path) -> Path:
    target = target_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step03: generate coordinate formula workbooks for Assembly modeling.")
    parser.add_argument("--coordinate-layout", "--layout", dest="coordinate_layout", default=None, help="Coordinate layout JSON.")
    parser.add_argument("--ocr-json", default=None, help="Reserved structured OCR JSON for future coordinate extraction.")
    parser.add_argument("--pdf", default=None, help="Reference drawing PDF. Used for preview/rendering when layout is provided.")
    parser.add_argument("--figure-image", default=None, help="Optional drawing image inserted into the workbooks.")
    parser.add_argument("--support-type", default="单桩单立柱")
    parser.add_argument("--angle", default="20")
    parser.add_argument("--project-prefix", "--project-code", dest="project_prefix", default=None)
    parser.add_argument("--outputs-root", default="outputs")
    parser.add_argument("--run-dir", default="latest", help="Run directory. Defaults to latest.")
    parser.add_argument("--full-out", default=None, help="Optional full workbook path.")
    parser.add_argument("--simple-out", default=None, help="Optional simple workbook path.")
    parser.add_argument("--control-tolerance-m", type=float, default=0.001)
    parser.add_argument("--angle-tolerance-deg", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prefix = args.project_prefix or _prefix_from_latest(args.outputs_root) or project_prefix(args.support_type, args.angle)
    run_paths = create_run_paths(prefix, args.outputs_root, args.run_dir)
    warnings: list[str] = []
    errors: list[str] = []
    rendered_pages: list[str] = []
    figure_image = Path(args.figure_image) if args.figure_image else None

    if args.pdf and not figure_image:
        try:
            from cadtocae.pdf_tables import render_pdf_pages

            pages = render_pdf_pages(args.pdf, run_paths.previews / "pdf_pages")
            rendered_pages = [str(path.resolve()) for path in pages]
            if pages:
                figure_image = pages[0]
        except Exception as exc:
            warnings.append("PDF rendering failed: %s" % exc)

    if not args.coordinate_layout:
        template = run_paths.workbooks / ("%s_coordinate_layout_template.json" % prefix)
        write_coordinate_layout_template(template, prefix)
        errors.append("Coordinate layout/OCR is required for Step03; scanned PDFs are not parsed without an OCR provider.")
        update_manifest(
            run_paths,
            prefix,
            "step03_coordinate_workbooks",
            inputs={
                "coordinate_layout": None,
                "ocr_json": str(Path(args.ocr_json).resolve()) if args.ocr_json else None,
                "pdf": str(Path(args.pdf).resolve()) if args.pdf else None,
            },
            outputs={
                "workbooks": {"coordinate_layout_template": str(template.resolve())},
                "previews": {"pdf_pages": rendered_pages},
            },
            warnings=warnings,
            errors=errors,
            metadata={"support_type": args.support_type, "angle": args.angle, "status": "partial"},
        )
        print("Run directory: %s" % run_paths.root.resolve())
        print("Wrote coordinate layout template: %s" % template.resolve())
        for warning in warnings:
            print("Warning: %s" % warning)
        for error in errors:
            print("Error: %s" % error)
        return 2

    layout_path = _copy_input_file(Path(args.coordinate_layout), run_paths.workbooks)
    full_out = Path(args.full_out) if args.full_out else run_paths.workbooks / ("%s_coordinate_formula_full_fixed.xlsx" % prefix)
    simple_out = Path(args.simple_out) if args.simple_out else run_paths.workbooks / ("%s_coordinate_formula_simple_fixed.xlsx" % prefix)
    full, simple = create_coordinate_formula_workbooks(
        layout_path,
        full_out,
        simple_out,
        project_prefix=prefix,
        figure_image=figure_image,
        control_tolerance_m=args.control_tolerance_m,
        angle_tolerance_deg=args.angle_tolerance_deg,
    )

    update_manifest(
        run_paths,
        prefix,
        "step03_coordinate_workbooks",
        inputs={
            "coordinate_layout": str(layout_path.resolve()),
            "ocr_json": str(Path(args.ocr_json).resolve()) if args.ocr_json else None,
            "pdf": str(Path(args.pdf).resolve()) if args.pdf else None,
            "figure_image": str(Path(figure_image).resolve()) if figure_image else None,
            "control_tolerance_m": args.control_tolerance_m,
            "angle_tolerance_deg": args.angle_tolerance_deg,
        },
        outputs={
            "workbooks": {
                "coordinate_formula_full": str(full.resolve()),
                "coordinate_formula_simple": str(simple.resolve()),
            },
            "previews": {"pdf_pages": rendered_pages},
        },
        warnings=warnings,
        metadata={"support_type": args.support_type, "angle": args.angle},
    )

    print("Run directory: %s" % run_paths.root.resolve())
    print("Wrote full coordinate workbook: %s" % full.resolve())
    print("Wrote simple coordinate workbook: %s" % simple.resolve())
    print("Manifest: %s" % run_paths.manifest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
