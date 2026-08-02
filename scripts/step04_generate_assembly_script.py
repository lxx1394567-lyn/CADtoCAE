from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cadtocae.main_frame_assembly import export_main_frame_assembly
from cadtocae.runs import create_run_paths, update_manifest
from cadtocae.standards import project_prefix


def _prefix_from_latest(outputs_root: str | Path) -> str | None:
    latest = Path(outputs_root) / "latest_run_manifest.json"
    if not latest.exists():
        return None
    payload = json.loads(latest.read_text(encoding="utf-8"))
    return payload.get("project_prefix") or payload.get("project_code")


def _default_components_json(run_dir: Path, prefix: str, coordinate_xlsx: Path | None = None) -> Path:
    candidates: list[Path] = []
    if coordinate_xlsx:
        candidates.append(coordinate_xlsx.parent / ("%s_components.json" % prefix))
    candidates.extend(
        [
            run_dir / ("%s_components.json" % prefix),
            run_dir / "json" / "components.json",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _default_coordinate_xlsx(run_dir: Path, prefix: str) -> Path:
    return run_dir / "workbooks" / ("%s_coordinate_formula_simple_fixed.xlsx" % prefix)


def _copy_input_workbook(source: Path, run_workbooks_dir: Path) -> Path:
    target = run_workbooks_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step04: generate Abaqus Assembly scripts from the simple coordinate workbook.")
    parser.add_argument("--coordinate-xlsx", default=None, help="Simple coordinate workbook. Defaults to latest run.")
    parser.add_argument("--components-json", default=None, help="Components JSON. Defaults to latest run.")
    parser.add_argument("--support-type", default="单桩单立柱")
    parser.add_argument("--angle", default="20")
    parser.add_argument("--project-prefix", "--project-code", dest="project_prefix", default=None)
    parser.add_argument("--model-name", default=None, help="Abaqus model name. Defaults to <project_prefix>.")
    parser.add_argument("--outputs-root", default="outputs")
    parser.add_argument("--run-dir", default="latest", help="Run directory. Defaults to latest.")
    parser.add_argument("--assembly-json", default=None, help="Optional Assembly JSON path.")
    parser.add_argument("--scripts-dir", default=None, help="Optional Abaqus scripts directory.")
    parser.add_argument("--reports-dir", default=None, help="Optional reports directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prefix = args.project_prefix or _prefix_from_latest(args.outputs_root) or project_prefix(args.support_type, args.angle)
    run_paths = create_run_paths(prefix, args.outputs_root, args.run_dir)

    coordinate_xlsx = Path(args.coordinate_xlsx) if args.coordinate_xlsx else _default_coordinate_xlsx(run_paths.root, prefix)
    if not coordinate_xlsx.exists():
        raise FileNotFoundError("Coordinate workbook not found: %s" % coordinate_xlsx)
    copied_coordinate = _copy_input_workbook(coordinate_xlsx, run_paths.workbooks)

    components_json = Path(args.components_json) if args.components_json else _default_components_json(run_paths.root, prefix, coordinate_xlsx)
    if not components_json.exists():
        raise FileNotFoundError("Components JSON not found: %s" % components_json)

    assembly_json = Path(args.assembly_json) if args.assembly_json else run_paths.json / "assembly_inputs.json"
    scripts_dir = Path(args.scripts_dir) if args.scripts_dir else run_paths.abaqus_scripts
    reports_dir = Path(args.reports_dir) if args.reports_dir else run_paths.reports

    model_name = args.model_name or prefix
    json_file, scripts, payload = export_main_frame_assembly(
        copied_coordinate,
        components_json,
        assembly_json,
        scripts_dir,
        reports_dir=reports_dir,
        project_code=prefix,
        model_name=model_name,
    )

    report_outputs = {
        "assembly_frame_report": str((reports_dir / ("%s_full_main_frame_report.json" % prefix)).resolve())
    }
    update_manifest(
        run_paths,
        prefix,
        "step04_assembly_script",
        inputs={
            "coordinate_excel": str(copied_coordinate.resolve()),
            "components_json": str(components_json.resolve()),
            "model_name": model_name,
        },
        outputs={
            "workbooks": {"coordinate_formula_simple": str(copied_coordinate.resolve())},
            "json": {"assembly_inputs": str(Path(json_file).resolve())},
            "abaqus_scripts": {script.stem: str(script.resolve()) for script in scripts},
            "reports": report_outputs,
        },
        warnings=list(payload.get("warnings", [])),
        errors=list(payload.get("errors", [])),
        metadata={"model_name": model_name},
    )

    print("Run directory: %s" % run_paths.root.resolve())
    print("Wrote Assembly JSON: %s" % Path(json_file).resolve())
    for script in scripts:
        print("Wrote Assembly Abaqus script: %s" % script.resolve())
    print("Manifest: %s" % run_paths.manifest.resolve())
    if payload.get("warnings"):
        print("Warnings: %d" % len(payload["warnings"]))
    if payload.get("errors"):
        print("Errors: %d" % len(payload["errors"]))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
