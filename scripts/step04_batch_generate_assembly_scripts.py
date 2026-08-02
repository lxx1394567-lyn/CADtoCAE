from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.assembly_script import batch_generate_assembly_scripts  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Step04: generate Abaqus Assembly scripts from Step03 coordinate workbooks.")
    parser.add_argument("workbooks", nargs="*", help="Coordinate workbooks, usually *_coordinate_formula_simple_fixed.xlsx.")
    parser.add_argument("--folder", "--input-dir", dest="input_dir", default=None, help="Folder containing coordinate workbooks. Outputs are written here by default.")
    parser.add_argument("--recursive", action="store_true", help="Search input folder recursively.")
    parser.add_argument("--components-json", default=None, help="Optional Step02 components json or create_parts_in_cae.py. If omitted, auto-search near each workbook.")
    parser.add_argument("--output-dir", default=None, help="Optional script output folder. Defaults to the selected folder or each workbook folder.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite files with the same name.")
    parser.add_argument("--summary-json", default=None, help="Optional path for batch summary JSON.")
    return parser.parse_args()


def _collect_workbooks(args: argparse.Namespace) -> list[Path]:
    paths = [Path(path) for path in args.workbooks]
    if args.input_dir:
        root = Path(args.input_dir)
        pattern = "**/*_coordinate_formula_simple_fixed.xlsx" if args.recursive else "*_coordinate_formula_simple_fixed.xlsx"
        paths.extend(path for path in sorted(root.glob(pattern)) if path.is_file() and not path.name.startswith("~$"))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
            continue
        resolved = str(path.resolve()).lower()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def main() -> int:
    args = parse_args()
    workbooks = _collect_workbooks(args)
    if not workbooks:
        print("No coordinate workbooks selected.")
        return 2

    outputs = []
    if args.output_dir or args.input_dir:
        output_dir = args.output_dir or args.input_dir
        outputs = batch_generate_assembly_scripts(
            workbooks,
            output_dir,
            components_json=args.components_json,
            overwrite=args.overwrite,
        )
    else:
        for workbook in workbooks:
            outputs.extend(
                batch_generate_assembly_scripts(
                    [workbook],
                    workbook.parent,
                    components_json=args.components_json,
                    overwrite=args.overwrite,
                )
            )

    for item in outputs:
        if item.script_paths:
            print("[%s] %s -> %s" % (item.status, Path(item.coordinate_workbook_path).name, item.project_dir))
            if item.assembly_json_path:
                print("      Assembly JSON: %s" % item.assembly_json_path)
            else:
                print("      Assembly data: embedded in generated .py")
            for script in item.script_paths:
                print("      Abaqus script: %s" % script)
            print("      Debug report: %s" % item.report_path)
        else:
            print("[%s] %s -> no assembly script; report: %s" % (item.status, Path(item.coordinate_workbook_path).name, item.report_path))
        for message in item.messages:
            print("      %s" % message)

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps([item.to_dict() for item in outputs], ensure_ascii=False, indent=2), encoding="utf-8")
        print("Summary: %s" % summary_path.resolve())

    return 0 if all(item.status == "ok" for item in outputs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
