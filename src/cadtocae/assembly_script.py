from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from .main_frame_assembly import export_main_frame_assembly, is_hoop_component_code, project_id_from_path, read_step02_model_name
from .part_script import PROJECT_PREFIX_RE, project_prefix_from_path


DEBUG_REPORT_SUBDIR = Path("过程文件") / "调试文件"


@dataclass
class AssemblyScriptOutput:
    coordinate_workbook_path: str
    status: str
    project_prefix: str
    project_dir: str
    copied_coordinate_workbook_path: str | None
    copied_components_json_path: str | None
    assembly_json_path: str | None
    script_paths: list[str]
    summary_path: str | None
    report_path: str
    warning_count: int
    error_count: int
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _write_report(path: str | Path, payload: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def step04_debug_report_path(output_root: str | Path, project_prefix_value: str) -> Path:
    return Path(output_root) / DEBUG_REPORT_SUBDIR / ("%s_step04_assembly_script_report.json" % project_prefix_value)


def assembly_summary_path(output_root: str | Path, project_id: str) -> Path:
    return Path(output_root) / ("%s_assembly_summary.json" % project_id)


def _instance_category(component_code: str) -> str:
    if component_code.startswith("COLUMN") or component_code.startswith("BRACE") or component_code == "INCLINED_BEAM":
        return "main_frame"
    if is_hoop_component_code(component_code):
        return "hoop"
    if component_code in {"PURLIN_SUPPORT", "PURLIN_LOCAL"}:
        return "purlin_connection"
    return "auxiliary"


def _connection_group(instance: dict[str, Any]) -> str | None:
    component_code = str(instance.get("component_code") or "")
    if component_code in {"PURLIN_SUPPORT", "PURLIN_LOCAL"}:
        match = re.search(r"_(\d+)$", str(instance.get("instance_id") or instance.get("instance_name") or ""))
        return "P%02d" % int(match.group(1)) if match else None
    if str(instance.get("canonical_role") or "") == "HOOP" or is_hoop_component_code(component_code):
        return str(instance.get("hoop_group_id") or "") or None
    return None


def _axis_direction(axis: str) -> list[float]:
    return {
        "X": [1.0, 0.0, 0.0],
        "Y": [0.0, 1.0, 0.0],
        "Z": [0.0, 0.0, 1.0],
    }[axis.upper()]


def _rotation_steps(instance: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    sequence = instance.get("rotation_sequence") or []
    if sequence:
        for rotation in sequence:
            axis = str(rotation.get("axis") or "").upper()
            angle = float(rotation.get("angle_deg") or 0.0)
            if abs(angle) > 1.0e-12:
                steps.append({"axis_point": [0.0, 0.0, 0.0], "axis_direction": _axis_direction(axis), "angle_deg": angle})
    else:
        rotate_y = float(instance.get("rotate_y_deg") or 0.0)
        if abs(rotate_y) > 1.0e-12:
            steps.append({"axis_point": [0.0, 0.0, 0.0], "axis_direction": [0.0, 1.0, 0.0], "angle_deg": rotate_y})
        roll = float(instance.get("roll_about_axis_deg") or 0.0)
        if abs(roll) > 1.0e-12:
            steps.append(
                {
                    "axis_point": list(instance.get("global_anchor") or [0.0, 0.0, 0.0]),
                    "axis_direction": list(instance.get("axis_direction") or [0.0, 0.0, 1.0]),
                    "angle_deg": roll,
                }
            )
    post_rotation = instance.get("post_rotation") or {}
    post_angle = float(post_rotation.get("angle_deg") or 0.0)
    if abs(post_angle) > 1.0e-12:
        steps.append(
            {
                "axis_point": list(post_rotation.get("axis_point") or [0.0, 0.0, 0.0]),
                "axis_direction": list(post_rotation.get("axis_direction") or [0.0, 0.0, 1.0]),
                "angle_deg": post_angle,
            }
        )
    return steps


def build_assembly_summary(payload: dict[str, Any]) -> dict[str, Any]:
    instances = []
    for instance in payload.get("instance_plan", []):
        steps = _rotation_steps(instance)
        single_rotation = steps[0] if len(steps) == 1 else None
        instances.append(
            {
                "instance_name": instance.get("instance_id") or instance.get("instance_name"),
                "component_code": instance.get("component_code"),
                "canonical_role": instance.get("canonical_role") or ("HOOP" if is_hoop_component_code(str(instance.get("component_code") or "")) else instance.get("component_code")),
                "part_name": instance.get("part_name"),
                "category": _instance_category(str(instance.get("component_code") or "")),
                "required": bool(instance.get("required", True)),
                "connection_group": _connection_group(instance),
                "placement": {
                    "mode": instance.get("placement_mode"),
                    "translation": list(instance.get("translation") or [0.0, 0.0, 0.0]),
                    "rotation_axis": single_rotation["axis_direction"] if single_rotation else None,
                    "rotation_angle": single_rotation["angle_deg"] if single_rotation else None,
                    "rotation_steps": steps,
                },
                "geometry_info": {
                    "length": instance.get("part_length_m"),
                    "section_kind": instance.get("section_kind"),
                },
            }
        )

    points = {}
    for name, point in payload.get("points", {}).items():
        coords = point.get("coords") if isinstance(point, dict) else point
        if isinstance(coords, (list, tuple)) and len(coords) == 3:
            points[str(name)] = [float(value) for value in coords]

    meta = payload.get("meta", {})
    return {
        "project_id": meta.get("project_id") or meta.get("project_code"),
        "model_name": meta.get("model_name"),
        "structure_type": meta.get("structure_type"),
        "source_files": {
            "coordinate_excel": meta.get("source_excel"),
            "part_script": meta.get("source_components"),
        },
        "assembly_info": {
            "created_time": datetime.now(timezone.utc).isoformat(),
            "executor_version": "step04-instance-plan-v1",
        },
        "instances": instances,
        "assembly_points": points,
    }


def export_assembly_summary(payload: dict[str, Any], output_path: str | Path) -> Path:
    return _write_report(output_path, build_assembly_summary(payload))


def _prefix_from_components_json(components_json: str | Path | None) -> str | None:
    if not components_json:
        return None
    path = Path(components_json)
    if not path.exists():
        return None
    model_name = read_step02_model_name(path)
    if model_name:
        return model_name
    filename_id = project_id_from_path(path)
    if filename_id != path.stem:
        return filename_id
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = PROJECT_PREFIX_RE.search(text)
    return match.group(0).upper() if match else None


def _prefix_from_workbook_text(xlsx: str | Path) -> str | None:
    workbook = load_workbook(xlsx, read_only=True, data_only=False)
    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 8), max_col=min(sheet.max_column, 6), values_only=True):
                for value in row:
                    if value is None:
                        continue
                    match = PROJECT_PREFIX_RE.search(str(value))
                    if match:
                        return match.group(0).upper()
    finally:
        workbook.close()
    return None


def infer_project_prefix_from_coordinate_workbook(xlsx: str | Path, components_json: str | Path | None = None) -> str:
    filename_id = project_id_from_path(xlsx)
    if filename_id != Path(xlsx).stem:
        return filename_id
    prefix = project_prefix_from_path(xlsx)
    if prefix:
        return prefix
    prefix = _prefix_from_workbook_text(xlsx)
    if prefix:
        return prefix
    prefix = _prefix_from_components_json(components_json)
    if prefix:
        return prefix
    raise ValueError("无法从坐标表或 Step02 组件数据推断完整 project_id，请将坐标表命名为 <project_id>_coordinate.xlsx。")


def locate_components_source(coordinate_workbook: str | Path, project_prefix: str | None = None) -> Path | None:
    workbook = Path(coordinate_workbook)
    inferred = project_id_from_path(workbook)
    prefix = project_prefix or (inferred if inferred != workbook.stem else None) or project_prefix_from_path(workbook) or _prefix_from_workbook_text(workbook)
    candidates: list[Path] = []
    for parent in [workbook.parent, *list(workbook.parents)[:4]]:
        if prefix:
            candidates.append(parent / ("%s_create_parts_in_cae.py" % prefix))
            candidates.append(parent / ("%s_components.json" % prefix))
        candidates.extend(
            [
                parent / "components.json",
                parent / "json" / "components.json",
            ]
        )
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def locate_components_json(coordinate_workbook: str | Path, project_prefix: str | None = None) -> Path | None:
    return locate_components_source(coordinate_workbook, project_prefix)


def generate_assembly_scripts_from_workbook(
    coordinate_workbook: str | Path,
    output_root: str | Path,
    components_json: str | Path | None = None,
    project_prefix_value: str | None = None,
    model_name: str | None = None,
    overwrite: bool = False,
) -> AssemblyScriptOutput:
    workbook = Path(coordinate_workbook)
    messages: list[str] = []
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        prefix = project_prefix_value or infer_project_prefix_from_coordinate_workbook(workbook, components_json)
        components = Path(components_json) if components_json else locate_components_source(workbook, prefix)
        if not components or not components.exists():
            raise FileNotFoundError("Step02 component data not found. Put <project_prefix>_create_parts_in_cae.py or <project_prefix>_components.json in the coordinate workbook folder.")

        components_prefix = _prefix_from_components_json(components)
        if components_prefix and components_prefix != prefix:
            raise ValueError("Step02 component data prefix %s does not match coordinate workbook prefix %s." % (components_prefix, prefix))

        if model_name and model_name != prefix:
            raise ValueError("Step04 model name must match project prefix %s." % prefix)

        actual_model_name = prefix
        scripts_dir = output_dir
        reports_dir = output_dir / DEBUG_REPORT_SUBDIR

        json_file, scripts, payload = export_main_frame_assembly(
            workbook,
            components,
            None,
            scripts_dir,
            reports_dir=reports_dir,
            project_code=prefix,
            model_name=actual_model_name,
        )

        warnings = list(payload.get("warnings", []))
        errors = list(payload.get("errors", []))
        if errors:
            raise ValueError("Step04 preflight failed: %s" % "; ".join(str(item) for item in errors))
        status = "needs_review" if warnings else "ok"
        messages.append("Generated %s Abaqus assembly script(s) with embedded data. Abaqus model name: %s." % (len(scripts), actual_model_name))
        messages.append(
            "structure_type=%s; project_id=%s; control_points=%s; planned_instances=%s; skipped_instances=%s."
            % (
                payload.get("meta", {}).get("structure_type"),
                prefix,
                len(payload.get("points", {})),
                len(payload.get("instance_plan", [])),
                len(payload.get("skipped_instances", [])),
            )
        )
        summary = export_assembly_summary(payload, assembly_summary_path(output_dir, prefix))
        if warnings:
            messages.append("%s warnings found; please review the coordinate workbook." % len(warnings))
        if errors:
            messages.append("%s errors found; fix the coordinate workbook and generate again." % len(errors))

        report = _write_report(
            step04_debug_report_path(output_dir, prefix),
            {
                "status": status,
                "project_prefix": prefix,
                "source_coordinate_workbook": str(workbook.resolve()),
                "source_components": str(components.resolve()),
                "assembly_json": None,
                "data_mode": "embedded_in_py",
                "abaqus_scripts": [str(path.resolve()) for path in scripts],
                "assembly_summary": str(summary.resolve()),
                "model_name": actual_model_name,
                "structure_type": payload.get("meta", {}).get("structure_type"),
                "control_point_count": len(payload.get("points", {})),
                "planned_instances": [item.get("instance_id") for item in payload.get("instance_plan", [])],
                "skipped_instances": payload.get("skipped_instances", []),
                "warnings": warnings,
                "errors": errors,
                "messages": messages,
            },
        )
        return AssemblyScriptOutput(
            coordinate_workbook_path=str(workbook.resolve()),
            status=status,
            project_prefix=prefix,
            project_dir=str(output_dir.resolve()),
            copied_coordinate_workbook_path=str(workbook.resolve()),
            copied_components_json_path=str(components.resolve()),
            assembly_json_path=None,
            script_paths=[str(path.resolve()) for path in scripts],
            summary_path=str(summary.resolve()),
            report_path=str(report.resolve()),
            warning_count=len(warnings),
            error_count=len(errors),
            messages=messages,
        )
    except Exception as exc:
        inferred = project_id_from_path(workbook)
        prefix = project_prefix_value or (inferred if inferred != workbook.stem else None) or project_prefix_from_path(workbook) or "UNKNOWN_PROJECT"
        report = _write_report(
            step04_debug_report_path(output_dir, prefix),
            {
                "status": "failed",
                "source_coordinate_workbook": str(workbook.resolve()),
                "components_json": str(Path(components_json).resolve()) if components_json else None,
                "messages": [str(exc)],
            },
        )
        return AssemblyScriptOutput(
            coordinate_workbook_path=str(workbook.resolve()),
            status="failed",
            project_prefix=prefix,
            project_dir=str(output_dir.resolve()),
            copied_coordinate_workbook_path=None,
            copied_components_json_path=None,
            assembly_json_path=None,
            script_paths=[],
            summary_path=None,
            report_path=str(report.resolve()),
            warning_count=0,
            error_count=1,
            messages=[str(exc)],
        )


def batch_generate_assembly_scripts(
    coordinate_workbooks: Iterable[str | Path],
    output_root: str | Path,
    components_json: str | Path | None = None,
    model_name: str | None = None,
    overwrite: bool = False,
) -> list[AssemblyScriptOutput]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    outputs: list[AssemblyScriptOutput] = []
    for workbook in coordinate_workbooks:
        outputs.append(
            generate_assembly_scripts_from_workbook(
                workbook,
                root,
                components_json=components_json,
                model_name=model_name,
                overwrite=overwrite,
            )
        )
    return outputs
