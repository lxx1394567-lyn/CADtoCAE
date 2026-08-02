from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from cadtocae.part_script import batch_generate_part_scripts  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Step02: generate Abaqus Part scripts from standardized Step01 Excel workbooks.")
    parser.add_argument("workbooks", nargs="*", help="Step01 Excel workbooks, usually *_components.xlsx.")
    parser.add_argument("--input-dir", default=None, help="Folder containing Step01 Excel workbooks.")
    parser.add_argument("--recursive", action="store_true", help="Search input folder recursively.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "step02_part_scripts"))
    parser.add_argument("--selection", choices=["complete", "approved"], default="complete")
    parser.add_argument("--standards", default=str(PROJECT_ROOT / "config" / "standards.json"))
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output folders when possible.")
    parser.add_argument("--summary-json", default=None, help="Optional path for batch summary JSON.")
    return parser.parse_args()


def _collect_workbooks(args: argparse.Namespace) -> list[Path]:
    paths = [Path(path) for path in args.workbooks]
    if args.input_dir:
        root = Path(args.input_dir)
        pattern = "**/*.xlsx" if args.recursive else "*.xlsx"
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
        print("No Step01 Excel workbooks selected.")
        return 2

    outputs = batch_generate_part_scripts(
        workbooks,
        args.output_dir,
        selection=args.selection,
        standards_path=args.standards,
        overwrite=args.overwrite,
    )

    for item in outputs:
        if item.part_script_path:
            print("[%s] %s -> %s" % (item.status, Path(item.workbook_path).name, item.part_script_path))
        else:
            print("[%s] %s -> no part script; report: %s" % (item.status, Path(item.workbook_path).name, item.report_path))
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
