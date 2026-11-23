"""Real-case discovery and validation. Never open generated Python scripts.

Uses the existing workbook exporter for component normalization; its temporary
JSON stays outside the case folder and is removed after reading.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .analysis_geometry import inverse_point, placement_candidates, patch_limits, vector, norm, sub, dot, cross, matvec
from .analysis_rules import build_analysis_plan
from .analysis_setup import write_analysis_setup
from .main_frame_assembly import read_excel_inputs, solve_points_from_inputs, _read_named_points, _length_m
from .workbook import export_abaqus_json


@dataclass(frozen=True)
class ProjectFiles:
    components: Path
    coordinate: Path
    assembly_summary: Path
    part_script: Path | None = None
    assembly_script: Path | None = None

    def paths(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__ if getattr(self, name) is not None}


def _one(paths, label):
    paths = sorted(paths, key=lambda p: str(p).lower())
    if not paths:
        raise ValueError("missing real input: " + label)
    if len(paths) != 1:
        raise ValueError("ambiguous project files (%s):\n%s" % (label, "\n".join(str(p) for p in paths)))
    return paths[0]


def _summary(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    for key in ("project_id", "model_name", "structure_type"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError("missing real input: assembly_summary." + key)
    if value["model_name"] != value["project_id"]:
        raise ValueError("project_id/model_name mismatch")
    return value


def _coordinate_name(name, project):
    return name == project + "_coordinate.xlsx" or (
        name.startswith(project + "_coordinate_formula_simple_fixed") and name.endswith(".xlsx"))


def validate_project_files(files):
    for name, path in files.paths().items():
        if not path.is_file():
            raise ValueError("missing real input (%s): %s" % (name, path))
    summary = _summary(files.assembly_summary)
    project = summary["project_id"]
    expected = {"components": project+"_components.xlsx", "assembly_summary": project+"_assembly_summary.json",
                "part_script": project+"_create_parts_in_cae.py", "assembly_script": project+"_assembly_frame.py"}
    for field, name in expected.items():
        if field in ('part_script', 'assembly_script') and getattr(files, field) is None:
            continue
        if getattr(files, field).name != name:
            raise ValueError("project_id/file prefix mismatch (%s): expected %s, got %s" % (field, name, getattr(files, field).name))
    if not _coordinate_name(files.coordinate.name, project):
        raise ValueError("project_id/file prefix mismatch (coordinate): " + str(files.coordinate))
    return summary


def discover_project_folder(folder):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError("Project folder does not exist: " + str(folder))
    paths = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith("~$")]
    summary_path = _one([p for p in paths if p.name.endswith("_assembly_summary.json")], "assembly_summary")
    _summary(summary_path)  # establish project identity before matching other files
    files = ProjectFiles(
        _one([p for p in paths if p.name.endswith("_components.xlsx")], "components"),
        _one([p for p in paths if p.name.endswith(".xlsx") and (p.name.endswith("_coordinate.xlsx") or
               "_coordinate_formula_simple_fixed" in p.name)], "coordinate"),
        summary_path,
        _one([p for p in paths if p.name.endswith("_create_parts_in_cae.py")], "part_script"),
        _one([p for p in paths if p.name.endswith("_assembly_frame.py")], "assembly_script"))
    validate_project_files(files)
    return files


def explicit_project_files(components, coordinate, assembly_summary, part_script=None, assembly_script=None):
    summary_path = Path(assembly_summary).resolve()
    if not summary_path.is_file():
        raise ValueError("missing real input: " + str(summary_path))
    project = _summary(summary_path)["project_id"]
    files = ProjectFiles(Path(components).resolve(), Path(coordinate).resolve(), summary_path,
                         Path(part_script).resolve() if part_script else summary_path.parent/(project+"_create_parts_in_cae.py"),
                         Path(assembly_script).resolve() if assembly_script else summary_path.parent/(project+"_assembly_frame.py"))
    validate_project_files(files)
    return files


def _positive(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("missing/invalid real component geometry: " + field)
    return float(value)


def _components(path, instances, tolerance):
    with tempfile.TemporaryDirectory(prefix="step05_components_") as tmp:
        exported = export_abaqus_json(path, Path(tmp)/"normalized.json", selection="complete")
        components = json.loads(exported.read_text(encoding="utf-8"))["components"]
    result = {}
    for instance in instances:
        code, part = instance["component_code"], instance["part_name"]
        matches = [item for item in components if item.get("component_code") == code and item.get("part_name") == part]
        if len(matches) != 1:
            raise ValueError("missing/ambiguous real normalized component: %s / %s" % (code, part))
        component = matches[0]
        if component.get("section_kind") != "C_CHANNEL" or component.get("model_policy") != "SHELL":
            raise ValueError("Unsupported real component type: " + part)
        params = component.get("section_params_m") or {}
        for key in ("h_m", "b_m", "lip_m", "t_m"):
            _positive(params.get(key), part+"."+key)
        thickness = _positive(component.get("thickness_m"), part+".thickness_m")
        length = _positive(component.get("length_m"), part+".length_m")
        if abs(thickness-params["t_m"]) > tolerance or params["lip_m"] >= params["h_m"]/2:
            raise ValueError("Inconsistent real section dimensions: " + part)
        if abs(length-instance["geometry_info"]["length"]) > tolerance:
            raise ValueError("Workbook/summary Part length mismatch: " + part)
        result[part] = {key: component[key] for key in ("component_code", "part_name", "section_kind", "section_params_m",
                                                      "thickness_m", "model_policy", "length_m", "element_type")}
        result[part]["source"] = "workbook.export_abaqus_json(selection=complete)"
    return result


def _coordinate_reference(path, summary, beam, tolerance):
    """Reuse Step04 parameter solver, or its numeric named-point reader.

    Neither path uses formulas without data nor invents a missing C station.
    """
    summary_c = vector(summary["assembly_points"]["C"])
    try:
        inputs, cached, _checks = read_excel_inputs(path)
    except ValueError as exc:
        if not str(exc).startswith(("Cannot find parameter table headers:", "Cannot find table headers:")):
            raise ValueError("Invalid real coordinate workbook: " + str(exc)) from exc
        points, _statuses = _read_named_points(path)
        if "C" not in points:
            raise ValueError("missing real input: coordinate C")
        coordinate_c = vector(points["C"])
        origin = points.get("G_global")
        if origin is None:
            origin = summary.get("assembly_points", {}).get("G_global")
        if origin is None:
            raise ValueError("missing real input: GC_mm or G_global for C local station")
        offset = sub(coordinate_c, vector(origin))
        direction = matvec(placement_candidates(beam["placement"])[0]["rotation"], (0., 0., 1.))
        if norm(cross(offset, direction)) > tolerance or dot(offset, direction) <= 0:
            raise ValueError("C/G_global is inconsistent with beam local axis")
        station = norm(offset)
        source = "coordinate C and verified G_global along beam axis"
    else:
        solved = solve_points_from_inputs(inputs)
        coordinate_c = vector(solved["C"]["coords"])
        station = _length_m(inputs, "GC_mm")
        source = "Step04 read_excel_inputs + solve_points_from_inputs; GC_mm"
        cached_c = (cached.get("C") or {}).get("coords")
        if cached_c and all(isinstance(x, (int, float)) and math.isfinite(x) for x in cached_c):
            if norm(sub(vector(cached_c), coordinate_c)) > tolerance:
                raise ValueError("Coordinate cached C disagrees with dimension-derived C")
    if norm(sub(coordinate_c, summary_c)) > tolerance:
        raise ValueError("Coordinate/assembly_summary C mismatch")
    low, high = patch_limits(station, .080, beam["geometry_info"]["length"], tolerance)
    candidates = [pose for pose in placement_candidates(beam["placement"])
                  if abs(inverse_point(pose, summary_c)[2]-station) <= tolerance]
    if not candidates:
        raise ValueError("C local station inconsistent with summary placement candidates")
    return {"C_global": list(summary_c), "C_beam_local_station_m": station,
            "patch_half_length_m": .080, "patch_range_m": [low, high], "source": source,
            "pose_status": "RUNTIME_VERIFICATION_REQUIRED"}


def build_real_analysis_plan(files):
    summary = validate_project_files(files)
    inputs = {"Project_Info": {"project_id": summary["project_id"], "schema_version": 1, "length_unit": "m"},
              "Partition_Region": [{"region_id": "REGION_BEAM_BRACE_FRONT", "connection_id": "BEAM_BRACE_FRONT",
                                    "target_role": "INCLINED_BEAM", "reference_station": "C", "half_length_m": .080,
                                    "partition_rule": "BEAM_LOCAL_PATCH", "enabled": True}]}
    plan = build_analysis_plan(summary, inputs)
    payload = plan.to_dict()
    tolerance = payload["project"]["geometry_tolerance_m"]
    geometry = _components(files.components, payload["instances"], tolerance)
    station = _coordinate_reference(files.coordinate, summary, payload["instances"][0], tolerance)
    for instance in payload["instances"]:
        instance["component_geometry"] = geometry[instance["part_name"]]
    payload["project"].update({"mode": "REAL_CASE", "model_name": summary["model_name"], "structure_type": summary["structure_type"]})
    payload["real_case"] = dict(station,
        beam_instance=payload["instances"][0]["instance_name"], brace_instance=payload["instances"][1]["instance_name"],
        beam_part=payload["instances"][0]["part_name"], brace_part=payload["instances"][1]["part_name"],
        beam_physical_side={"contact_semantic": "LOWER_FLANGE_PHYSICAL_OUTER_SURFACE", "abaqus_side": "RUNTIME_REQUIRED",
                            "reason": "actual positive face normal and SectionAssignment offset are verified in CAE"},
        brace_region_rule="INTERSECT_REFERENCE_SHELL_WITH_BEAM_PHYSICAL_OUTER_PLANE_NO_TRIMMING",
        mesh_action="DELETE_ONLY_AFFECTED_NATIVE_MESH_IF_PARTITION_PENDING_NO_REMESH",
        inputs={key: str(value) for key, value in files.paths().items()},
        source_hashes={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in files.paths().items()
                       if key in ("components", "coordinate", "assembly_summary")},
        execution_order=[str(files.part_script), str(files.assembly_script)])
    for item in payload["partitions"] + payload["regions"]:
        item["parameters"].update(station_local_m=station["C_beam_local_station_m"], patch_range_m=station["patch_range_m"])
    return payload


def generate_real_analysis_setup(files, output_dir=None):
    payload = build_real_analysis_plan(files)
    output = Path(output_dir).resolve() if output_dir else files.assembly_summary.parent/"step05_validation"
    return write_analysis_setup(payload, output)
