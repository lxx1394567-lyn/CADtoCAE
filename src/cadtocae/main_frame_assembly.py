from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template
from typing import Any

from openpyxl import load_workbook

from .runs import create_run_paths, update_manifest


CONFIRMED = "\u5df2\u786e\u8ba4"
MANUAL_CHECK = "\u9700\u4eba\u5de5\u786e\u8ba4"
PASSED = "\u901a\u8fc7"
FAILED = "\u4e0d\u901a\u8fc7"

DEFAULT_PROJECT_CODE = "PV_SUPPORT"
POINT_COMPARE_TOLERANCE_M = 1.0e-6
VALUE_COMPARE_TOLERANCE = 1.0e-6

MAIN_COMPONENT_CODES = {
    "INCLINED_BEAM": "INCLINED_BEAM",
    "BRACE_FRONT": "BRACE_FRONT",
    "BRACE_REAR": "BRACE_REAR",
}
PURLIN_AXIS_INPUT_NAMES = ("HF_mm", "HS_mm", "HP_mm", "HQ_mm", "HR_mm")
PURLIN_AXIS_POINT_NAMES = ("S", "P", "Q", "R")
PURLIN_SHORT_LENGTH_M = 0.05
PURLIN_GROUP_Y_OFFSET_M = 0.025
PURLIN_BEAM_GAP_M = 0.010
PURLIN_STATION_POINT_NAMES = ("P1", "P2", "P3", "P4")
SPQR_COLLINEAR_TOLERANCE_M = 1.0e-6


@dataclass(frozen=True)
class ExcelInput:
    name: str
    meaning: str
    value: Any
    unit: str
    status: str
    note: str
    row: int


@dataclass(frozen=True)
class InstanceSpec:
    instance_id: str
    component_code: str
    part_name: str
    placement_mode: str
    start_point: list[float] | None = None
    end_point: list[float] | None = None
    origin: list[float] | None = None
    axis_direction: list[float] | None = None
    roll_deg: float = 0.0
    required: bool = True
    source: str = ""


STRUCTURE_TYPES = ("SP_SC", "SP_DC")
PROJECT_ID_SUFFIXES = (
    "_coordinate_formula_simple_fixed",
    "_coordinate_formula_full_fixed",
    "_coordinate",
    "_create_parts_in_cae",
    "_components",
)


def _float(value: Any, name: str) -> float:
    if value is None or value == "":
        raise ValueError("Missing numeric input: %s" % name)
    return float(value)


def _length_m(inputs: dict[str, ExcelInput], name: str) -> float:
    row = inputs[name]
    value = _float(row.value, name)
    unit = (row.unit or "").strip().lower()
    if unit == "mm":
        return value / 1000.0
    if unit == "m":
        return value
    raise ValueError("Input %s must use mm or m, got %r" % (name, row.unit))


def _value(inputs: dict[str, ExcelInput], name: str) -> float:
    return _float(inputs[name].value, name)


def _point(x: float, y: float, z: float, status: str = CONFIRMED, note: str = "") -> dict[str, Any]:
    return {
        "coords": [x, y, z],
        "x_m": x,
        "y_m": y,
        "z_m": z,
        "status": status,
        "note": note,
    }


def _coords(point: dict[str, Any]) -> list[float]:
    return [float(point["x_m"]), float(point["y_m"]), float(point["z_m"])]


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a: list[float], b: list[float]) -> list[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _scale(a: list[float], factor: float) -> list[float]:
    return [a[0] * factor, a[1] * factor, a[2] * factor]


def _dot(a: list[float], b: list[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _norm(a: list[float]) -> float:
    return math.sqrt(_dot(a, a))


def _point_line_distance(point: list[float], start: list[float], end: list[float]) -> float:
    line = _sub(end, start)
    line_length = _norm(line)
    if line_length <= 1.0e-15:
        return distance(point, start)
    return _norm(_cross(_sub(point, start), line)) / line_length


def distance(a: list[float], b: list[float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def rotate_x(point: list[float], angle_deg: float) -> list[float]:
    angle = math.radians(angle_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return [x, y * c - z * s, y * s + z * c]


def rotate_y(point: list[float], angle_deg: float) -> list[float]:
    angle = math.radians(angle_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return [x * c + z * s, y, -x * s + z * c]


def rotate_z(point: list[float], angle_deg: float) -> list[float]:
    angle = math.radians(angle_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return [x * c - y * s, x * s + y * c, z]


def transform_local(point: list[float], rotate_y_deg: float, roll_about_axis_deg: float = 0.0) -> list[float]:
    return rotate_y(rotate_z(point, roll_about_axis_deg), rotate_y_deg)


def transform_rotation_sequence(point: list[float], rotation_sequence: list[dict[str, Any]]) -> list[float]:
    result = [float(point[0]), float(point[1]), float(point[2])]
    for rotation in rotation_sequence:
        axis = str(rotation.get("axis") or "").upper()
        angle_deg = float(rotation.get("angle_deg") or 0.0)
        if axis == "X":
            result = rotate_x(result, angle_deg)
        elif axis == "Y":
            result = rotate_y(result, angle_deg)
        elif axis == "Z":
            result = rotate_z(result, angle_deg)
        else:
            raise ValueError("Unsupported rotation axis: %s" % axis)
    return result


def vector_angle_from_x(vector: list[float]) -> float:
    return math.degrees(math.atan2(vector[2], vector[0]))


def rotate_y_for_local_z_to_vector(start: list[float], end: list[float]) -> float:
    dx = end[0] - start[0]
    dz = end[2] - start[2]
    return math.degrees(math.atan2(dx, dz))


def _angle_error_deg(calc: float, reference: float) -> float:
    return (calc - reference + 180.0) % 360.0 - 180.0


def _pass_fail(error: float, tolerance: float) -> str:
    return PASSED if abs(error) <= tolerance else FAILED


def _find_header_row(ws, required: tuple[str, ...]) -> int:
    for row in range(1, ws.max_row + 1):
        values = [ws.cell(row, column).value for column in range(1, len(required) + 1)]
        if tuple(values) == required:
            return row
    raise ValueError("Cannot find header row: %s" % (required,))


def _find_table_header(wb, required_headers: tuple[str, ...], preferred_sheets: tuple[str, ...] = ()):
    sheet_names = list(preferred_sheets) + [name for name in wb.sheetnames if name not in preferred_sheets]
    for sheet_name in sheet_names:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        for row in range(1, ws.max_row + 1):
            headers = [ws.cell(row, column).value for column in range(1, ws.max_column + 1)]
            header_map = {str(value): index + 1 for index, value in enumerate(headers) if value is not None}
            if all(header in header_map for header in required_headers):
                return ws, row, header_map
    raise ValueError("Cannot find table headers: %s" % (required_headers,))


def read_excel_inputs(excel_path: str | Path) -> tuple[dict[str, ExcelInput], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    path = Path(excel_path)
    wb_values = load_workbook(path, data_only=True)

    input_headers = ("参数名", "参数含义", "数值", "单位", "校核状态", "备注")
    inputs: dict[str, ExcelInput] = {}
    for ws_values in wb_values.worksheets:
        for input_header in range(1, ws_values.max_row + 1):
            values = [ws_values.cell(input_header, column).value for column in range(1, ws_values.max_column + 1)]
            input_cols = {str(value): index + 1 for index, value in enumerate(values) if value is not None}
            if not all(header in input_cols for header in input_headers):
                continue
            row = input_header + 1
            while row <= ws_values.max_row:
                name = ws_values.cell(row, input_cols["参数名"]).value
                if not name:
                    break
                key = str(name)
                inputs[key] = ExcelInput(
                    name=key,
                    meaning=str(ws_values.cell(row, input_cols["参数含义"]).value or ""),
                    value=ws_values.cell(row, input_cols["数值"]).value,
                    unit=str(ws_values.cell(row, input_cols["单位"]).value or ""),
                    status=str(ws_values.cell(row, input_cols["校核状态"]).value or ""),
                    note=str(ws_values.cell(row, input_cols["备注"]).value or ""),
                    row=row,
                )
                row += 1
    if not inputs:
        raise ValueError("Cannot find parameter table headers: %s" % (input_headers,))

    point_ws, output_header, point_cols = _find_table_header(
        wb_values,
        ("点名", "X_m", "Y_m", "Z_m", "校核状态"),
        preferred_sheets=("控制点坐标",),
    )
    cached_points: dict[str, dict[str, Any]] = {}
    row = output_header + 1
    point_note_col = point_cols.get("说明") or point_cols.get("标注说明")
    while row <= point_ws.max_row:
        name = point_ws.cell(row, point_cols["点名"]).value
        if not name:
            break
        cached_points[str(name)] = {
            "coords": [
                point_ws.cell(row, point_cols["X_m"]).value,
                point_ws.cell(row, point_cols["Y_m"]).value,
                point_ws.cell(row, point_cols["Z_m"]).value,
            ],
            "status": str(point_ws.cell(row, point_cols["校核状态"]).value or ""),
            "note": str(point_ws.cell(row, point_note_col).value or "") if point_note_col else "",
            "row": row,
        }
        row += 1

    check_ws, check_header, check_cols = _find_table_header(
        wb_values,
        ("校核项", "计算值", "图纸/输入值", "误差", "允许误差", "是否通过", "校核状态"),
        preferred_sheets=("长度与角度校核",),
    )
    cached_checks: dict[str, dict[str, Any]] = {}
    row = check_header + 1
    while row <= check_ws.max_row:
        name = check_ws.cell(row, check_cols["校核项"]).value
        if not name:
            break
        cached_checks[str(name)] = {
            "calc_value": check_ws.cell(row, check_cols["计算值"]).value,
            "reference_value": check_ws.cell(row, check_cols["图纸/输入值"]).value,
            "error": check_ws.cell(row, check_cols["误差"]).value,
            "tolerance": check_ws.cell(row, check_cols["允许误差"]).value,
            "passed": str(check_ws.cell(row, check_cols["是否通过"]).value or ""),
            "status": str(check_ws.cell(row, check_cols["校核状态"]).value or ""),
            "row": row,
        }
        row += 1

    return inputs, cached_points, cached_checks


def input_status(inputs: dict[str, ExcelInput], names: list[str]) -> str:
    for name in names:
        if inputs.get(name) is None or inputs[name].status != CONFIRMED:
            return MANUAL_CHECK
    return CONFIRMED


def _has_numeric_inputs(inputs: dict[str, ExcelInput], names: tuple[str, ...]) -> bool:
    for name in names:
        row = inputs.get(name)
        if row is None or row.value in (None, ""):
            return False
        try:
            _float(row.value, name)
        except (TypeError, ValueError):
            return False
    return True


def solve_points_from_inputs(inputs: dict[str, ExcelInput]) -> dict[str, dict[str, Any]]:
    theta_deg = _value(inputs, "theta_deg")
    theta = math.radians(theta_deg)
    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)

    z_a = _length_m(inputs, "Z_A_mm")
    x_f = _length_m(inputs, "X_F_mm")
    z_f = _length_m(inputs, "Z_F_mm")
    z_bd = _length_m(inputs, "Z_BD_mm")
    r_hoop = _length_m(inputs, "R_hoop_mm")
    gc = _length_m(inputs, "GC_mm")
    gf = _length_m(inputs, "GF_mm")
    ge = _length_m(inputs, "GE_mm")

    points = {
        "O": _point(0.0, 0.0, 0.0, CONFIRMED, "Origin"),
        "A": _point(0.0, 0.0, z_a, input_status(inputs, ["Z_A_mm"]), "Upper column top"),
        "F": _point(x_f, 0.0, z_f, input_status(inputs, ["X_F_mm", "Z_F_mm"]), "Beam-column reference section"),
        "B": _point(-r_hoop, 0.0, z_bd, input_status(inputs, ["Z_BD_mm", "R_hoop_mm"]), "Front brace hoop point"),
        "D": _point(r_hoop, 0.0, z_bd, input_status(inputs, ["Z_BD_mm", "R_hoop_mm"]), "Rear brace hoop point"),
    }

    f = _coords(points["F"])
    u = [cos_theta, 0.0, sin_theta]
    c = _add(f, _scale(u, gc - gf))
    e = _add(f, _scale(u, ge - gf))
    g_global = _add(f, _scale(u, -gf))

    points["C"] = _point(
        c[0],
        c[1],
        c[2],
        input_status(inputs, ["theta_deg", "X_F_mm", "Z_F_mm", "GC_mm", "GF_mm"]),
        "Beam-front brace section",
    )
    points["E"] = _point(
        e[0],
        e[1],
        e[2],
        input_status(inputs, ["theta_deg", "X_F_mm", "Z_F_mm", "GE_mm", "GF_mm"]),
        "Beam-rear brace section",
    )
    points["G_global"] = _point(
        g_global[0],
        g_global[1],
        g_global[2],
        input_status(inputs, ["theta_deg", "X_F_mm", "Z_F_mm", "GF_mm"]),
        "Derived global position of beam local origin G",
    )
    if _has_numeric_inputs(inputs, PURLIN_AXIS_INPUT_NAMES):
        hf = _length_m(inputs, "HF_mm")
        hs = _length_m(inputs, "HS_mm")
        hp = _length_m(inputs, "HP_mm")
        hq = _length_m(inputs, "HQ_mm")
        hr = _length_m(inputs, "HR_mm")
        n = [-sin_theta, 0.0, cos_theta]
        h = _add(f, _scale(n, hf))
        purlin_status_names = ["theta_deg", "X_F_mm", "Z_F_mm", "HF_mm"]
        points["H"] = _point(h[0], h[1], h[2], input_status(inputs, purlin_status_names), "PV/purlin axis reference point")
        points["S"] = _point(
            h[0] - hs * cos_theta,
            h[1],
            h[2] - hs * sin_theta,
            input_status(inputs, [*purlin_status_names, "HS_mm"]),
            "Purlin axis point S, negative beam-axis side from H",
        )
        points["P"] = _point(
            h[0] - hp * cos_theta,
            h[1],
            h[2] - hp * sin_theta,
            input_status(inputs, [*purlin_status_names, "HP_mm"]),
            "Purlin axis point P, negative beam-axis side from H",
        )
        points["Q"] = _point(
            h[0] + hq * cos_theta,
            h[1],
            h[2] + hq * sin_theta,
            input_status(inputs, [*purlin_status_names, "HQ_mm"]),
            "Purlin axis point Q, positive beam-axis side from H",
        )
        points["R"] = _point(
            h[0] + hr * cos_theta,
            h[1],
            h[2] + hr * sin_theta,
            input_status(inputs, [*purlin_status_names, "HR_mm"]),
            "Purlin axis point R, positive beam-axis side from H",
        )
    return points


def build_checks(inputs: dict[str, ExcelInput], points: dict[str, dict[str, Any]], beam_length_m: float | None) -> dict[str, dict[str, Any]]:
    theta_deg = _value(inputs, "theta_deg")
    gc = _length_m(inputs, "GC_mm")
    gf = _length_m(inputs, "GF_mm")
    ge = _length_m(inputs, "GE_mm")
    l_bc = _length_m(inputs, "L_BC_draw_mm")
    l_de = _length_m(inputs, "L_DE_draw_mm")
    control_tol = _length_m(inputs, "control_tolerance_m")
    angle_tol = _value(inputs, "angle_tolerance_deg")

    c = _coords(points["C"])
    e = _coords(points["E"])
    b = _coords(points["B"])
    d = _coords(points["D"])
    ce_angle = vector_angle_from_x(_sub(e, c))
    ce_error = _angle_error_deg(ce_angle, theta_deg)
    bc_calc = distance(b, c)
    de_calc = distance(d, e)
    beam_length_ok = True
    if beam_length_m is not None:
        beam_length_ok = ge < beam_length_m

    checks = {
        "GC_GF_GE_ORDER": {
            "calc_value": "GC=%.6f, GF=%.6f, GE=%.6f" % (gc, gf, ge),
            "reference_value": "0 < GC < GF < GE < beam_length",
            "error": None,
            "tolerance": None,
            "passed": PASSED if 0.0 < gc < gf < ge and beam_length_ok else FAILED,
            "status": input_status(inputs, ["GC_mm", "GF_mm", "GE_mm"]),
        },
        "CF_LOCAL": {
            "calc_value": gf - gc,
            "reference_value": "GF-GC",
            "error": None,
            "tolerance": None,
            "passed": PASSED if gf - gc > 0.0 else FAILED,
            "status": input_status(inputs, ["GC_mm", "GF_mm"]),
        },
        "FE_LOCAL": {
            "calc_value": ge - gf,
            "reference_value": "GE-GF",
            "error": None,
            "tolerance": None,
            "passed": PASSED if ge - gf > 0.0 else FAILED,
            "status": input_status(inputs, ["GF_mm", "GE_mm"]),
        },
        "CE_ANGLE": {
            "calc_value": ce_angle,
            "reference_value": theta_deg,
            "error": ce_error,
            "tolerance": angle_tol,
            "passed": _pass_fail(ce_error, angle_tol),
            "status": input_status(inputs, ["theta_deg", "X_F_mm", "Z_F_mm", "GC_mm", "GF_mm", "GE_mm"]),
        },
        "BC": {
            "calc_value": bc_calc,
            "reference_value": l_bc,
            "error": bc_calc - l_bc,
            "tolerance": control_tol,
            "passed": _pass_fail(bc_calc - l_bc, control_tol),
            "status": input_status(
                inputs,
                ["theta_deg", "X_F_mm", "Z_F_mm", "Z_BD_mm", "R_hoop_mm", "GC_mm", "GF_mm", "L_BC_draw_mm"],
            ),
        },
        "DE": {
            "calc_value": de_calc,
            "reference_value": l_de,
            "error": de_calc - l_de,
            "tolerance": control_tol,
            "passed": _pass_fail(de_calc - l_de, control_tol),
            "status": input_status(
                inputs,
                ["theta_deg", "X_F_mm", "Z_F_mm", "Z_BD_mm", "R_hoop_mm", "GE_mm", "GF_mm", "L_DE_draw_mm"],
            ),
        },
    }
    if all(name in points for name in PURLIN_AXIS_POINT_NAMES) and inputs.get("pv_axis_angle_tolerance_deg") is not None:
        s = _coords(points["S"])
        p = _coords(points["P"])
        q = _coords(points["Q"])
        r = _coords(points["R"])
        max_offset = max(_point_line_distance(p, s, r), _point_line_distance(q, s, r))
        spqr_angle = vector_angle_from_x(_sub(r, s))
        spqr_angle_error = _angle_error_deg(spqr_angle, theta_deg)
        spqr_angle_tol = _value(inputs, "pv_axis_angle_tolerance_deg")
        purlin_status = input_status(inputs, ["theta_deg", "X_F_mm", "Z_F_mm", *PURLIN_AXIS_INPUT_NAMES, "pv_axis_angle_tolerance_deg"])
        checks["SPQR_COLLINEAR"] = {
            "calc_value": max_offset,
            "reference_value": 0.0,
            "error": max_offset,
            "tolerance": SPQR_COLLINEAR_TOLERANCE_M,
            "passed": PASSED if max_offset <= SPQR_COLLINEAR_TOLERANCE_M else FAILED,
            "status": purlin_status,
        }
        checks["SPQR_ANGLE"] = {
            "calc_value": spqr_angle,
            "reference_value": theta_deg,
            "error": spqr_angle_error,
            "tolerance": spqr_angle_tol,
            "passed": _pass_fail(spqr_angle_error, spqr_angle_tol),
            "status": purlin_status,
        }
    return checks


def read_components_payload(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".py" or "COMPONENTS_JSON" in text:
        match = re.search(r"COMPONENTS_JSON\s*=\s*r?'''(?P<payload>.*?)'''", text, re.DOTALL)
        if not match:
            match = re.search(r'COMPONENTS_JSON\s*=\s*r?"""(?P<payload>.*?)"""', text, re.DOTALL)
        if not match:
            raise ValueError("Cannot find embedded COMPONENTS_JSON in %s" % source)
        return json.loads(match.group("payload"))
    return json.loads(text)


def project_id_from_path(path: str | Path) -> str:
    stem = Path(path).stem
    lowered = stem.lower()
    for suffix in PROJECT_ID_SUFFIXES:
        if lowered.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def detect_structure_type(project_id: str) -> str:
    upper = str(project_id).upper()
    for structure_type in STRUCTURE_TYPES:
        if upper.startswith(structure_type + "_"):
            return structure_type
    raise ValueError("Unsupported structure_type for project_id %s. Expected SP_SC or SP_DC." % project_id)


def read_step02_model_name(path: str | Path) -> str | None:
    source = Path(path)
    if source.suffix.lower() != ".py":
        return None
    text = source.read_text(encoding="utf-8")
    match = re.search(r'^MODEL_NAME\s*=\s*[\"\'](?P<name>[^\"\']+)[\"\']', text, re.MULTILINE)
    return match.group("name") if match else None


def load_components(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = read_components_payload(path)
    by_code: dict[str, dict[str, Any]] = {}
    for row in payload.get("components", []):
        code = row.get("component_code")
        if code:
            by_code[str(code)] = row
    return by_code


def _component(by_code: dict[str, dict[str, Any]], code: str) -> dict[str, Any]:
    if code not in by_code:
        raise ValueError("Missing component_code in components JSON: %s" % code)
    return by_code[code]


def _optional_component(by_code: dict[str, dict[str, Any]], code: str) -> dict[str, Any] | None:
    return by_code.get(code)


HOOP_ASSEMBLY_CODE_RE = re.compile(r"^HOOP_ASSEMBLY_(\d+)$")


def resolve_hoop_component_code(code: str) -> tuple[str, int | None] | None:
    normalized = str(code or "").strip().upper()
    if normalized == "HOOP":
        return "HOOP", None
    match = HOOP_ASSEMBLY_CODE_RE.fullmatch(normalized)
    if match:
        return "HOOP", int(match.group(1))
    return None


def is_hoop_component_code(code: str) -> bool:
    return resolve_hoop_component_code(code) is not None


def _resolve_hoop_component(
    components: dict[str, dict[str, Any]], group_index: int
) -> dict[str, Any] | None:
    numbered = components.get("HOOP_ASSEMBLY_%d" % group_index)
    if numbered is not None:
        return numbered
    return components.get("HOOP")


def compare_cached_points(points: dict[str, dict[str, Any]], cached_points: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for name, point in points.items():
        if name == "O":
            continue
        cached = cached_points.get(name)
        if not cached:
            warnings.append("Excel cached point %s is missing." % name)
            continue
        cached_coords = cached.get("coords") or []
        if len(cached_coords) != 3 or any(value is None for value in cached_coords):
            warnings.append("Excel cached point %s has empty coordinate cache." % name)
            continue
        err = distance(_coords(point), [float(cached_coords[0]), float(cached_coords[1]), float(cached_coords[2])])
        if err > POINT_COMPARE_TOLERANCE_M:
            warnings.append("Excel cached point %s differs from Python recompute by %.9g m." % (name, err))
    return warnings


def compare_cached_checks(checks: dict[str, dict[str, Any]], cached_checks: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for name, check in checks.items():
        cached = cached_checks.get(name)
        if not cached:
            warnings.append("Excel cached check %s is missing." % name)
            continue
        for key in ("calc_value", "reference_value", "error", "tolerance"):
            calc = check.get(key)
            cached_value = cached.get(key)
            if calc is None or cached_value in (None, ""):
                continue
            if isinstance(calc, (int, float)) and isinstance(cached_value, (int, float)):
                if abs(float(calc) - float(cached_value)) > VALUE_COMPARE_TOLERANCE:
                    warnings.append(
                        "Excel cached check %s.%s differs from Python recompute by %.9g."
                        % (name, key, float(calc) - float(cached_value))
                    )
        if cached.get("passed") and check.get("passed") != cached.get("passed"):
            warnings.append("Excel cached check %s pass state is %r, Python recompute is %r." % (name, cached.get("passed"), check.get("passed")))
    return warnings


def member_length_check(points: dict[str, dict[str, Any]], start: str, end: str, part_length_m: float | None, tolerance_m: float) -> dict[str, Any]:
    axis_length = distance(_coords(points[start]), _coords(points[end]))
    error = None if part_length_m is None else axis_length - float(part_length_m)
    passed = MANUAL_CHECK if error is None else _pass_fail(error, tolerance_m)
    return {
        "start": start,
        "end": end,
        "axis_length_m": axis_length,
        "part_length_m": part_length_m,
        "error_m": error,
        "tolerance_m": tolerance_m,
        "passed": passed,
    }


def _section_reference_xy(component: dict[str, Any]) -> dict[str, Any]:
    kind = component.get("section_kind")
    params = component.get("section_params_m") or {}
    if kind == "C_CHANNEL":
        h = float(params.get("h_m") or 0.0)
        if h > 0.0:
            return {
                "x_m": 0.0,
                "y_m": h / 2.0,
                "rule": "C_CHANNEL_WEB_MIDPOINT",
                "open_side_local": "+X",
                "open_side_target_global": "-Y",
            }
    if kind == "ANGLE":
        a = float(params.get("leg_a_m") or 0.0)
        b = float(params.get("leg_b_m") or 0.0)
        t = float(params.get("t_m") or 0.0)
        area = a * t + t * b - t * t
        if area > 0.0:
            x = (a * t * (a / 2.0) + t * b * (t / 2.0) - t * t * (t / 2.0)) / area
            y = (a * t * (t / 2.0) + t * b * (b / 2.0) - t * t * (t / 2.0)) / area
            return {
                "x_m": x,
                "y_m": y,
                "rule": "ANGLE_SOLID_SECTION_CENTROID",
                "open_side_local": "+X,+Y",
                "open_side_target_global": "",
            }
    return {
        "x_m": 0.0,
        "y_m": 0.0,
        "rule": "SECTION_ORIGIN",
        "open_side_local": "",
        "open_side_target_global": "",
    }


def _default_roll_about_axis_deg(name: str, component: dict[str, Any]) -> float:
    roll = 0.0
    if component.get("section_kind") == "C_CHANNEL":
        roll = -90.0
    if name == "INCLINED_BEAM":
        roll += 180.0
    return roll


def _local_reference_point(component: dict[str, Any], station_m: float) -> list[float]:
    ref = _section_reference_xy(component)
    return [float(ref["x_m"]), float(ref["y_m"]), float(station_m)]


def _clean_vector(vector: list[float], tolerance: float = 1.0e-12) -> list[float]:
    return [0.0 if abs(float(value)) <= tolerance else float(value) for value in vector]


def _translation_for_anchor(
    local_anchor: list[float],
    global_anchor: list[float],
    rotate_y_deg: float,
    roll_about_axis_deg: float = 0.0,
) -> list[float]:
    rotated = rotate_y(local_anchor, rotate_y_deg)
    return [global_anchor[0] - rotated[0], global_anchor[1] - rotated[1], global_anchor[2] - rotated[2]]


def _translation_for_rotation_sequence(local_anchor: list[float], global_anchor: list[float], rotation_sequence: list[dict[str, Any]]) -> list[float]:
    rotated = transform_rotation_sequence(local_anchor, rotation_sequence)
    return [global_anchor[0] - rotated[0], global_anchor[1] - rotated[1], global_anchor[2] - rotated[2]]


def _instance_name(component: dict[str, Any], suffix: str | None = None) -> str:
    part_name = str(component["part_name"])
    base = part_name[2:] if part_name.startswith("P_") else part_name
    return "I_%s_%s" % (base, suffix) if suffix else "I_%s" % base


def _short_purlin_part_name(component: dict[str, Any]) -> str:
    return "%s_50MM" % component["part_name"]


def _purlin_rotation_sequence(theta_deg: float) -> list[dict[str, Any]]:
    return [
        {"axis": "X", "angle_deg": 90.0},
        {"axis": "Y", "angle_deg": -theta_deg},
    ]


def _purlin_support_rotation_sequence(theta_deg: float) -> list[dict[str, Any]]:
    return [
        {"axis": "Z", "angle_deg": 90.0},
        {"axis": "X", "angle_deg": 90.0},
        {"axis": "Y", "angle_deg": -theta_deg},
    ]


def _purlin_upper_flange_anchor(component: dict[str, Any]) -> list[float]:
    params = component.get("section_params_m") or {}
    return [float(params["b_m"]) / 2.0, float(params["h_m"]), PURLIN_SHORT_LENGTH_M / 2.0]


def _purlin_support_inside_corner_anchor(component: dict[str, Any]) -> list[float]:
    length = float(component.get("length_m") or PURLIN_SHORT_LENGTH_M)
    return [0.0, 0.0, length / 2.0]


def _copy_component_for_payload(component: dict[str, Any], part_name: str, length_m: float) -> dict[str, Any]:
    copied = json.loads(json.dumps(component, ensure_ascii=False))
    copied["part_name"] = part_name
    copied["length_m"] = length_m
    return copied


def _member_with_rotation_sequence(
    name: str,
    phase: str,
    component: dict[str, Any],
    part_name: str,
    instance_name: str,
    local_anchor: list[float],
    global_anchor_name: str,
    global_anchor: list[float],
    rotation_sequence: list[dict[str, Any]],
    part_length_m: float | None = None,
    source_part_name: str | None = None,
    part_component: dict[str, Any] | None = None,
    section_reference: dict[str, Any] | None = None,
    axis_checks: list[dict[str, Any]] | None = None,
    placement_note: str = "",
) -> dict[str, Any]:
    member = {
        "name": name,
        "phase": phase,
        "part_name": part_name,
        "source_part_name": source_part_name or component["part_name"],
        "component_code": component.get("component_code"),
        "instance_name": instance_name,
        "local_anchor": local_anchor,
        "global_anchor_name": global_anchor_name,
        "global_anchor": global_anchor,
        "rotation_sequence": rotation_sequence,
        "translation": _translation_for_rotation_sequence(local_anchor, global_anchor, rotation_sequence),
        "part_length_m": part_length_m if part_length_m is not None else component.get("length_m"),
        "section_kind": component.get("section_kind"),
        "section_params_m": component.get("section_params_m") or {},
        "section_reference": section_reference or _section_reference_xy(component),
        "model_policy": component.get("model_policy"),
        "placement_note": placement_note,
    }
    if part_component is not None:
        member["part_component"] = part_component
    if axis_checks is not None:
        member["axis_checks"] = axis_checks
    return member


def _build_purlin_members(
    purlin_component: dict[str, Any],
    purlin_support_component: dict[str, Any],
    points: dict[str, dict[str, Any]],
    theta_deg: float,
    u: list[float],
    n: list[float],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if purlin_component.get("section_kind") != "C_CHANNEL":
        return [], {"enabled": False, "reason": "PURLIN section_kind is not C_CHANNEL."}, {}, ["PURLIN section_kind is not C_CHANNEL; purlin assembly skipped."]
    if purlin_support_component.get("section_kind") != "ANGLE":
        return [], {"enabled": False, "reason": "PURLIN_SUPPORT section_kind is not ANGLE."}, {}, ["PURLIN_SUPPORT section_kind is not ANGLE; purlin assembly skipped."]

    purlin_params = purlin_component.get("section_params_m") or {}
    purlin_b = float(purlin_params["b_m"])
    purlin_h = float(purlin_params["h_m"])
    derived_part_name = _short_purlin_part_name(purlin_component)
    purlin_part_component = _copy_component_for_payload(purlin_component, derived_part_name, PURLIN_SHORT_LENGTH_M)
    purlin_rotation = _purlin_rotation_sequence(theta_deg)
    support_rotation = _purlin_support_rotation_sequence(theta_deg)
    purlin_local_anchor = _purlin_upper_flange_anchor(purlin_component)
    support_local_anchor = _purlin_support_inside_corner_anchor(purlin_support_component)
    support_length = float(purlin_support_component.get("length_m") or PURLIN_SHORT_LENGTH_M)
    if abs(support_length - PURLIN_SHORT_LENGTH_M) > 1.0e-9:
        warnings.append("PURLIN_SUPPORT length is %.6f m; expected 0.050000 m for the XZ simplified slice." % support_length)

    members: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}
    for point_name in PURLIN_AXIS_POINT_NAMES:
        control_anchor = _coords(points[point_name])
        global_anchor = _add(control_anchor, [0.0, PURLIN_GROUP_Y_OFFSET_M, 0.0])
        web_top = _add(global_anchor, _scale(u, -purlin_b / 2.0))
        web_bottom = _add(web_top, _scale(n, -purlin_h))
        purlin_member = _member_with_rotation_sequence(
            "PURLIN_%s" % point_name,
            "step04_purlins",
            purlin_component,
            derived_part_name,
            _instance_name(purlin_component, point_name),
            purlin_local_anchor,
            point_name,
            global_anchor,
            purlin_rotation,
            part_length_m=PURLIN_SHORT_LENGTH_M,
            source_part_name=purlin_component["part_name"],
            part_component=purlin_part_component,
            section_reference={
                "x_m": purlin_local_anchor[0],
                "y_m": purlin_local_anchor[1],
                "z_m": purlin_local_anchor[2],
                "rule": "C_CHANNEL_UPPER_FLANGE_CENTER",
                "open_side_local": "+X",
                "open_side_target_global": "PV_AXIS_POSITIVE",
            },
            axis_checks=[
                {"name": "flange_axis", "local_vector": [1.0, 0.0, 0.0], "expected_global": u, "tolerance": 1.0e-6},
                {"name": "web_axis", "local_vector": [0.0, 1.0, 0.0], "expected_global": n, "tolerance": 1.0e-6},
                {"name": "length_axis_parallel_y", "local_vector": [0.0, 0.0, 1.0], "expected_global": [0.0, -1.0, 0.0], "tolerance": 1.0e-6},
            ],
            placement_note="50mm purlin slice; upper flange center maps to %s; length axis is parallel to global Y." % point_name,
        )
        support_member = _member_with_rotation_sequence(
            "PURLIN_SUPPORT_%s" % point_name,
            "step04_purlins",
            purlin_support_component,
            purlin_support_component["part_name"],
            _instance_name(purlin_support_component, point_name),
            support_local_anchor,
            "%s_WEB_BOTTOM" % point_name,
            web_bottom,
            support_rotation,
            part_length_m=support_length,
            source_part_name=purlin_support_component["part_name"],
            section_reference={
                "x_m": support_local_anchor[0],
                "y_m": support_local_anchor[1],
                "z_m": support_local_anchor[2],
                "rule": "ANGLE_INSIDE_CORNER_AT_PURLIN_WEB_BOTTOM",
                "open_side_local": "+Y",
                "open_side_target_global": "PV_AXIS_NEGATIVE",
            },
            axis_checks=[
                {"name": "long_leg_axis", "local_vector": [1.0, 0.0, 0.0], "expected_global": n, "tolerance": 1.0e-6},
                {"name": "short_leg_axis", "local_vector": [0.0, 1.0, 0.0], "expected_global": _scale(u, -1.0), "tolerance": 1.0e-6},
                {"name": "length_axis_parallel_y", "local_vector": [0.0, 0.0, 1.0], "expected_global": [0.0, -1.0, 0.0], "tolerance": 1.0e-6},
            ],
            placement_note="Angle support inside corner contacts purlin web-bottom corner; long leg follows the web and short leg is flush with the lower flange line.",
        )
        members.extend([purlin_member, support_member])
        checks["PURLIN_%s_PLACEMENT" % point_name] = {
            "anchor": point_name,
            "control_point": control_anchor,
            "y_offset_m": PURLIN_GROUP_Y_OFFSET_M,
            "upper_flange_center": global_anchor,
            "web_top": web_top,
            "web_bottom": web_bottom,
            "lower_flange_center": _add(global_anchor, _scale(n, -purlin_h)),
            "flange_axis_global": u,
            "web_axis_global": n,
            "length_axis_global": [0.0, -1.0, 0.0],
            "passed": PASSED,
        }
        checks["PURLIN_SUPPORT_%s_PLACEMENT" % point_name] = {
            "anchor": "%s_WEB_BOTTOM" % point_name,
            "y_offset_m": PURLIN_GROUP_Y_OFFSET_M,
            "inside_corner": web_bottom,
            "long_leg_axis_global": n,
            "short_leg_axis_global": _scale(u, -1.0),
            "length_axis_global": [0.0, -1.0, 0.0],
            "passed": PASSED,
        }

    metadata = {
        "enabled": True,
        "point_names": list(PURLIN_AXIS_POINT_NAMES),
        "short_length_m": PURLIN_SHORT_LENGTH_M,
        "purlin_source_part_name": purlin_component["part_name"],
        "purlin_derived_part_name": derived_part_name,
        "purlin_support_part_name": purlin_support_component["part_name"],
        "axis_unit": u,
        "normal_unit": n,
        "purlin_height_m": purlin_h,
        "purlin_width_m": purlin_b,
        "group_y_offset_m": PURLIN_GROUP_Y_OFFSET_M,
        "placement": "C-channel upper flange center at S/P/Q/R; member length axes parallel global Y.",
    }
    return members, metadata, checks, warnings


def _member(
    name: str,
    phase: str,
    component: dict[str, Any],
    local_anchor: list[float],
    global_anchor_name: str,
    points: dict[str, dict[str, Any]],
    rotate_y_deg: float,
    target_point_name: str | None = None,
    roll_about_axis_deg: float = 0.0,
) -> dict[str, Any]:
    global_anchor = _coords(points[global_anchor_name])
    section_reference = _section_reference_xy(component)
    open_side_local = [1.0, 0.0, 0.0] if component.get("section_kind") == "C_CHANNEL" else [0.0, 0.0, 0.0]
    open_side_global = _clean_vector(transform_local(open_side_local, rotate_y_deg, roll_about_axis_deg)) if open_side_local != [0.0, 0.0, 0.0] else [0.0, 0.0, 0.0]
    member = {
        "name": name,
        "phase": phase,
        "part_name": component["part_name"],
        "component_code": component.get("component_code"),
        "instance_name": _instance_name(component),
        "local_anchor": local_anchor,
        "global_anchor_name": global_anchor_name,
        "global_anchor": global_anchor,
        "rotate_y_deg": rotate_y_deg,
        "roll_about_axis_deg": roll_about_axis_deg,
        "translation": _translation_for_anchor(local_anchor, global_anchor, rotate_y_deg, roll_about_axis_deg),
        "part_length_m": component.get("length_m"),
        "section_kind": component.get("section_kind"),
        "section_params_m": component.get("section_params_m") or {},
        "section_reference": section_reference,
        "open_side_global": open_side_global,
        "model_policy": component.get("model_policy"),
    }
    if target_point_name:
        member["target_point_name"] = target_point_name
        member["target_point"] = _coords(points[target_point_name])
    return member


def _add_sp_sc_station_points(
    points: dict[str, dict[str, Any]],
    inputs: dict[str, ExcelInput],
    cached_points: dict[str, dict[str, Any]],
    beam_tangent: list[float],
) -> None:
    beam_origin = _coords(points["G_global"])
    for index, point_name in enumerate(PURLIN_STATION_POINT_NAMES, start=1):
        cached = cached_points.get(point_name) or {}
        cached_coords = cached.get("coords")
        if isinstance(cached_coords, list) and len(cached_coords) == 3 and all(value not in (None, "") for value in cached_coords):
            try:
                coords = _finite_point(cached_coords, point_name)
            except (TypeError, ValueError):
                coords = []
            if coords:
                points[point_name] = _point(*coords, status=str(cached.get("status") or ""), note="Excel final purlin station point")
                continue
        input_name = "GP%d_mm" % index
        row = inputs.get(input_name)
        if row is None or row.value in (None, ""):
            continue
        station = _add(beam_origin, _scale(beam_tangent, _float(row.value, input_name) / 1000.0))
        points[point_name] = _point(*station, status=row.status, note="Derived from G + %s * beam_tangent" % input_name)


def _build_sp_sc_payload(
    excel_path: str | Path,
    components_path: str | Path,
    project_code: str = DEFAULT_PROJECT_CODE,
    model_name: str | None = None,
) -> dict[str, Any]:
    model_name = model_name or project_code
    inputs, cached_points, cached_checks = read_excel_inputs(excel_path)
    components = load_components(components_path)
    main_components = {code: _component(components, code) for code in MAIN_COMPONENT_CODES}
    column_down_component = _optional_component(components, "COLUMN_DOWN")
    column_up_component = _optional_component(components, "COLUMN_UP")
    single_column_component = _optional_component(components, "COLUMN")
    if not (column_down_component and column_up_component) and not single_column_component and not column_up_component:
        raise ValueError("Missing column components. Expected COLUMN_DOWN+COLUMN_UP, COLUMN, or COLUMN_UP in components JSON.")
    beam_component = main_components["INCLINED_BEAM"]
    beam_length = beam_component.get("length_m")

    points = solve_points_from_inputs(inputs)
    checks = build_checks(inputs, points, beam_length)
    warnings = compare_cached_points(points, cached_points) + compare_cached_checks(checks, cached_checks)
    errors: list[str] = []

    theta_deg = _value(inputs, "theta_deg")
    theta_rad = math.radians(theta_deg)
    gc = _length_m(inputs, "GC_mm")
    gf = _length_m(inputs, "GF_mm")
    ge = _length_m(inputs, "GE_mm")
    control_tolerance = _length_m(inputs, "control_tolerance_m")
    angle_tolerance = _value(inputs, "angle_tolerance_deg")
    rotate_beam_y = 90.0 - theta_deg
    u = [math.cos(theta_rad), 0.0, math.sin(theta_rad)]
    n = [-math.sin(theta_rad), 0.0, math.cos(theta_rad)]
    _add_sp_sc_station_points(points, inputs, cached_points, u)
    beam_roll = _default_roll_about_axis_deg("INCLINED_BEAM", beam_component)
    front_brace_roll = _default_roll_about_axis_deg("BRACE_FRONT", main_components["BRACE_FRONT"])
    rear_brace_roll = _default_roll_about_axis_deg("BRACE_REAR", main_components["BRACE_REAR"])

    for name, row in inputs.items():
        if row.status != CONFIRMED:
            warnings.append("Input %s status is %s." % (name, row.status or "empty"))
    if control_tolerance > 0.001 + 1.0e-12:
        warnings.append("control_tolerance_m is %.6f m; this is wider than +/-1 mm." % control_tolerance)
    if checks["GC_GF_GE_ORDER"]["passed"] != PASSED:
        errors.append("Beam stations must satisfy 0 < GC < GF < GE < beam length.")

    column_members: list[dict[str, Any]] = []
    member_checks: dict[str, dict[str, Any]] = {}
    if column_down_component and column_up_component:
        column_members.extend(
            [
                _member(
                    "COLUMN_DOWN",
                    "step01_columns",
                    column_down_component,
                    _local_reference_point(column_down_component, 0.0),
                    "O",
                    points,
                    0.0,
                ),
                _member(
                    "COLUMN_UP",
                    "step01_columns",
                    column_up_component,
                    _local_reference_point(column_up_component, float(column_up_component.get("length_m") or 0.0)),
                    "A",
                    points,
                    0.0,
                ),
            ]
        )
        column_up_bottom = _add(_coords(points["A"]), [0.0, 0.0, -float(column_up_component.get("length_m") or 0.0)])
        column_down_top = _add(_coords(points["O"]), [0.0, 0.0, float(column_down_component.get("length_m") or 0.0)])
        member_checks.update(
            {
                "COLUMN_DOWN_PLACEMENT": {
                    "anchor": "O",
                    "part_length_m": column_down_component.get("length_m"),
                    "derived_top": column_down_top,
                    "passed": PASSED,
                    "note": "Only the bottom point O is controlled in step01.",
                },
                "COLUMN_UP_PLACEMENT": {
                    "anchor": "A",
                    "part_length_m": column_up_component.get("length_m"),
                    "derived_bottom": column_up_bottom,
                    "passed": PASSED,
                    "note": "Only the top point A is controlled in step01.",
                },
            }
        )
    elif single_column_component is not None:
        assert single_column_component is not None
        column_members.append(
            _member(
                "COLUMN",
                "step01_columns",
                single_column_component,
                _local_reference_point(single_column_component, float(single_column_component.get("length_m") or 0.0)),
                "A",
                points,
                0.0,
            )
        )
        column_bottom = _add(_coords(points["A"]), [0.0, 0.0, -float(single_column_component.get("length_m") or 0.0)])
        member_checks["COLUMN_PLACEMENT"] = {
            "anchor": "A",
            "part_length_m": single_column_component.get("length_m"),
            "derived_bottom": column_bottom,
            "passed": PASSED,
            "note": "Single COLUMN component is controlled by its top point A.",
        }
    else:
        assert column_up_component is not None
        column_members.append(
            _member(
                "COLUMN_UP",
                "step01_columns",
                column_up_component,
                _local_reference_point(column_up_component, float(column_up_component.get("length_m") or 0.0)),
                "A",
                points,
                0.0,
            )
        )
        column_up_bottom = _add(_coords(points["A"]), [0.0, 0.0, -float(column_up_component.get("length_m") or 0.0)])
        member_checks["COLUMN_UP_PLACEMENT"] = {
            "anchor": "A",
            "part_length_m": column_up_component.get("length_m"),
            "derived_bottom": column_up_bottom,
            "passed": PASSED,
            "note": "Only COLUMN_UP is available; it is controlled as a single upper column by top point A.",
        }

    members = [
        *column_members,
        _member(
            "INCLINED_BEAM",
            "step02_beam",
            beam_component,
            _local_reference_point(beam_component, gf),
            "F",
            points,
            rotate_beam_y,
            target_point_name="E",
            roll_about_axis_deg=beam_roll,
        ),
        _member(
            "BRACE_FRONT",
            "step03_main_frame",
            main_components["BRACE_FRONT"],
            _local_reference_point(main_components["BRACE_FRONT"], 0.0),
            "B",
            points,
            rotate_y_for_local_z_to_vector(_coords(points["B"]), _coords(points["C"])),
            target_point_name="C",
            roll_about_axis_deg=front_brace_roll,
        ),
        _member(
            "BRACE_REAR",
            "step03_main_frame",
            main_components["BRACE_REAR"],
            _local_reference_point(main_components["BRACE_REAR"], 0.0),
            "D",
            points,
            rotate_y_for_local_z_to_vector(_coords(points["D"]), _coords(points["E"])),
            target_point_name="E",
            roll_about_axis_deg=rear_brace_roll,
        ),
    ]

    member_checks.update(
        {
            "INCLINED_BEAM_CE": {
                "start": "C",
                "end": "E",
                "axis_length_m": distance(_coords(points["C"]), _coords(points["E"])),
                "part_length_m": beam_length,
                "error_m": None,
                "tolerance_m": control_tolerance,
                "passed": PASSED,
            },
            "BRACE_FRONT_BC": {
                **member_length_check(points, "B", "C", main_components["BRACE_FRONT"].get("length_m"), control_tolerance),
                "passed": checks["BC"]["passed"],
                "drawing_length_check": checks["BC"],
                "note": "Abaqus placement uses B-C axis; material length can include connection offsets.",
            },
            "BRACE_REAR_DE": {
                **member_length_check(points, "D", "E", main_components["BRACE_REAR"].get("length_m"), control_tolerance),
                "passed": checks["DE"]["passed"],
                "drawing_length_check": checks["DE"],
                "note": "Abaqus placement uses D-E axis; material length can include connection offsets.",
            },
        }
    )
    skipped_instances: list[dict[str, str]] = []
    purlin_nodes, purlin_checks = _add_purlin_nodes(
        members,
        components,
        {name: _coords(point) for name, point in points.items()},
        u,
        "SP_SC adapter: P1/P2/P3/P4 purlin station points",
        warnings,
        skipped_instances,
        beam_origin=_coords(points["G_global"]),
    )
    member_checks.update(purlin_checks)
    purlin_axis_metadata: dict[str, Any] = {
        "enabled": bool(purlin_nodes),
        "point_names": [node["station"] for node in purlin_nodes],
        "purlin_support_part_name": components.get("PURLIN_SUPPORT", {}).get("part_name"),
        "purlin_local_part_name": components.get("PURLIN_LOCAL", {}).get("part_name"),
        "axis_unit": u,
        "normal_unit": n,
        "beam_to_purlin_gap_m": PURLIN_BEAM_GAP_M,
        "placement": "One PURLIN_SUPPORT and one PURLIN_LOCAL per P1/P2/P3/P4 station.",
    }

    beam_reference = _section_reference_xy(beam_component)
    beam_local_point = _local_reference_point(beam_component, gf)
    beam_local_origin = _local_reference_point(beam_component, 0.0)
    required_part_names = sorted({member.get("source_part_name") or member["part_name"] for member in members})
    payload = {
        "meta": {
            "project_code": project_code,
            "model_name": model_name,
            "source_excel": str(Path(excel_path).as_posix()),
            "source_components": str(Path(components_path).as_posix()),
            "coordinate_system": "X right, Y out of elevation plane, Z up; units m-kg-N-Pa",
        },
        "units": {
            "length": "m",
            "mass": "kg",
            "force": "N",
            "stress": "Pa",
            "density": "kg/m^3",
        },
        "inputs": {
            "theta_deg": theta_deg,
            "theta_rad": theta_rad,
            "GC_m": gc,
            "GF_m": gf,
            "GE_m": ge,
            "control_tolerance_m": control_tolerance,
            "angle_tolerance_deg": angle_tolerance,
            "beam_length_m": beam_length,
            "pv_axis_angle_tolerance_deg": _value(inputs, "pv_axis_angle_tolerance_deg") if inputs.get("pv_axis_angle_tolerance_deg") is not None else None,
            "purlin_short_length_m": PURLIN_SHORT_LENGTH_M,
        },
        "input_rows": {
            name: {
                "meaning": row.meaning,
                "value": row.value,
                "unit": row.unit,
                "status": row.status,
                "note": row.note,
                "excel_row": row.row,
            }
            for name, row in inputs.items()
        },
        "points": points,
        "beam_anchor": {
            "part_name": beam_component["part_name"],
            "local_point_name": "F",
            "local_point": beam_local_point,
            "axis_local_point": [0.0, 0.0, gf],
            "reference_local_origin": beam_local_origin,
            "global_point_name": "F",
            "global_point": _coords(points["F"]),
            "stations": {"C": gc, "F": gf, "E": ge},
            "direction_u": u,
            "rotate_y_deg": rotate_beam_y,
            "roll_about_axis_deg": beam_roll,
            "translation": _translation_for_anchor(beam_local_point, _coords(points["F"]), rotate_beam_y, beam_roll),
            "section_reference": beam_reference,
            "section_sets": {"C": "SET_BEAM_SEC_C", "F": "SET_BEAM_SEC_F", "E": "SET_BEAM_SEC_E"},
        },
        "purlin_axis": purlin_axis_metadata,
        "members": members,
        "required_part_names": required_part_names,
        "checks": checks,
        "member_checks": member_checks,
        "warnings": warnings,
        "errors": errors,
        "skipped_instances": skipped_instances,
        "purlin_nodes": purlin_nodes,
    }
    return payload


def _finite_point(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Control point %s must contain X/Y/Z coordinates." % name)
    point = [float(item) for item in value]
    if not all(math.isfinite(item) for item in point):
        raise ValueError("Control point %s contains NaN or infinite values." % name)
    return point


def _read_named_points(workbook_path: str | Path) -> tuple[dict[str, list[float]], dict[str, str]]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    points: dict[str, list[float]] = {}
    statuses: dict[str, str] = {}
    try:
        for sheet in workbook.worksheets:
            for row in range(1, sheet.max_row + 1):
                headers = [sheet.cell(row, column).value for column in range(1, sheet.max_column + 1)]
                header_map = {str(value).strip(): index + 1 for index, value in enumerate(headers) if value not in (None, "")}
                if not all(name in header_map for name in ("X_m", "Y_m", "Z_m")):
                    continue
                name_col = header_map.get("点名") or header_map.get("名称")
                if not name_col:
                    continue
                status_col = header_map.get("校核状态") or header_map.get("状态")
                current = row + 1
                while current <= sheet.max_row:
                    name = sheet.cell(current, name_col).value
                    if name in (None, ""):
                        current += 1
                        continue
                    values = [
                        sheet.cell(current, header_map["X_m"]).value,
                        sheet.cell(current, header_map["Y_m"]).value,
                        sheet.cell(current, header_map["Z_m"]).value,
                    ]
                    try:
                        points[str(name).strip()] = _finite_point(values, str(name))
                    except (TypeError, ValueError):
                        current += 1
                        continue
                    statuses[str(name).strip()] = str(sheet.cell(current, status_col).value or "") if status_col else ""
                    current += 1
                if points:
                    return points, statuses
    finally:
        workbook.close()
    raise ValueError("Cannot find a control-point table with 点名/X_m/Y_m/Z_m in %s." % workbook_path)


def _read_named_value(workbook_path: str | Path, name: str) -> float | None:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            for row in range(1, sheet.max_row + 1):
                if str(sheet.cell(row, 1).value or "").strip() != name:
                    continue
                value = sheet.cell(row, 3).value
                if value not in (None, ""):
                    return float(value)
    finally:
        workbook.close()
    return None


def _instance_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value).upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        raise ValueError("Instance id cannot be empty.")
    if cleaned[0].isdigit():
        cleaned = "I_" + cleaned
    return cleaned


def _normalize_instance_member(
    member: dict[str, Any],
    instance_id: str,
    placement_mode: str,
    required: bool,
    source: str,
    start_point: list[float] | None = None,
    end_point: list[float] | None = None,
    origin: list[float] | None = None,
    axis_direction: list[float] | None = None,
) -> dict[str, Any]:
    normalized = dict(member)
    spec = InstanceSpec(
        instance_id=_instance_id(instance_id),
        component_code=str(member.get("component_code") or member.get("name") or ""),
        part_name=str(member["part_name"]),
        placement_mode=placement_mode,
        start_point=start_point,
        end_point=end_point,
        origin=origin,
        axis_direction=axis_direction,
        roll_deg=float(member.get("roll_about_axis_deg") or 0.0),
        required=required,
        source=source,
    )
    normalized.update(asdict(spec))
    normalized["instance_name"] = spec.instance_id
    return normalized


def _point_orient_member(
    name: str,
    component: dict[str, Any],
    origin: list[float],
    instance_id: str,
    rotation_sequence: list[dict[str, Any]] | None = None,
    local_anchor: list[float] | None = None,
    source: str = "",
) -> dict[str, Any]:
    sequence = list(rotation_sequence or [])
    anchor = list(local_anchor or [0.0, 0.0, 0.0])
    member = _member_with_rotation_sequence(
        name=name,
        phase="step04_initial_assembly",
        component=component,
        part_name=str(component["part_name"]),
        instance_name=instance_id,
        local_anchor=anchor,
        global_anchor_name=name,
        global_anchor=origin,
        rotation_sequence=sequence,
        part_length_m=component.get("length_m"),
        section_reference=_section_reference_xy(component),
    )
    return _normalize_instance_member(
        member,
        instance_id,
        "POINT_ORIENT",
        False,
        source,
        origin=origin,
        axis_direction=[0.0, 0.0, 1.0],
    )


def _create_hoop_pair(
    primary_component: dict[str, Any],
    center: list[float],
    group_index: int,
    source: str,
    secondary_component: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    center = _finite_point(center, "H%d" % group_index)
    column_axis = [0.0, 0.0, 1.0]
    if _norm(column_axis) <= 1.0e-12:
        raise ValueError("HOOP group %02d has an invalid column axis." % group_index)
    components = (primary_component, secondary_component or primary_component)
    pair: list[dict[str, Any]] = []
    for half_index, component in enumerate(components):
        half_name = "A" if half_index == 0 else "B"
        width = float((component.get("section_params_m") or {}).get("width_m") or component.get("length_m") or 0.0)
        instance_id = "HOOP_%02d_%s" % (group_index, half_name)
        member = _point_orient_member(
            instance_id,
            component,
            center,
            instance_id,
            local_anchor=[0.0, 0.0, width / 2.0],
            source=source,
        )
        source_code = str(component.get("component_code") or "HOOP")
        resolved = resolve_hoop_component_code(source_code)
        member["component_code"] = source_code if resolved else "HOOP"
        member["source_component_code"] = source_code
        member["canonical_role"] = "HOOP"
        member["assembly_index"] = resolved[1] if resolved else None
        member["hoop_group_id"] = "HOOP_%02d" % group_index
        member["hoop_half"] = half_name
        if half_name == "B":
            member["post_rotation"] = {
                "axis_point": list(center),
                "axis_direction": column_axis,
                "angle_deg": 180.0,
            }
        pair.append(member)
    group = {
        "group_id": "HOOP_%02d" % group_index,
        "source_component_code": pair[0]["component_code"],
        "canonical_role": "HOOP",
        "assembly_index": pair[0].get("assembly_index"),
        "center": list(center),
        "part_a": pair[0]["part_name"],
        "part_b": pair[1]["part_name"],
        "instance_a": pair[0]["instance_id"],
        "instance_b": pair[1]["instance_id"],
        "pair_rotation": {"axis_point": list(center), "axis_direction": column_axis, "angle_deg": 180.0},
    }
    return pair, group


def _create_purlin_node_pair(
    support_component: dict[str, Any],
    local_purlin_component: dict[str, Any],
    station_name: str,
    station_point: list[float],
    node_index: int,
    beam_tangent: list[float],
    beam_surface_offset: float,
    beam_center_offset: float,
    source: str,
    beam_origin: list[float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    station = _finite_point(station_point, station_name)
    if support_component.get("component_code") != "PURLIN_SUPPORT":
        raise ValueError("Purlin node %s requires component_code PURLIN_SUPPORT." % station_name)
    if local_purlin_component.get("component_code") != "PURLIN_LOCAL":
        raise ValueError("Purlin node %s requires component_code PURLIN_LOCAL; ordinary PURLIN is not allowed." % station_name)
    if support_component.get("section_kind") != "ANGLE":
        raise ValueError("PURLIN_SUPPORT at %s must use an ANGLE section." % station_name)
    if local_purlin_component.get("section_kind") != "C_CHANNEL":
        raise ValueError("PURLIN_LOCAL at %s must use a C_CHANNEL section." % station_name)

    tangent_norm = _norm(beam_tangent)
    if tangent_norm <= 1.0e-12:
        raise ValueError("Purlin node %s has an invalid beam tangent." % station_name)
    e_s = _scale(beam_tangent, 1.0 / tangent_norm)
    e_y = [0.0, 1.0, 0.0]
    e_n = _cross(e_s, e_y)
    normal_norm = _norm(e_n)
    if normal_norm <= 1.0e-12:
        raise ValueError("Purlin node %s has an invalid beam local frame." % station_name)
    e_n = _scale(e_n, 1.0 / normal_norm)
    if e_n[2] < 0.0:
        e_n = _scale(e_n, -1.0)

    theta_deg = math.degrees(math.atan2(e_s[2], e_s[0]))
    support_rotation = _purlin_support_rotation_sequence(theta_deg)
    purlin_rotation = _purlin_rotation_sequence(theta_deg)
    support_length = float(support_component.get("length_m") or 0.0)
    purlin_length = float(local_purlin_component.get("length_m") or 0.0)
    if support_length <= 0.0 or purlin_length <= 0.0:
        raise ValueError("Purlin node %s requires positive Part lengths." % station_name)

    support_anchor = [0.0, 0.0, support_length / 2.0]
    purlin_anchor = [0.0, 0.0, purlin_length / 2.0]
    purlin_thickness = float(local_purlin_component.get("thickness_m") or (local_purlin_component.get("section_params_m") or {}).get("t_m") or 0.0)
    purlin_midplane_offset = PURLIN_BEAM_GAP_M + purlin_thickness / 2.0
    beam_section_center = _add(station, _scale(e_y, beam_center_offset))
    support_global_anchor = _add(beam_section_center, _scale(e_n, beam_surface_offset))
    purlin_global_anchor = _add(beam_section_center, _scale(e_n, beam_surface_offset + purlin_midplane_offset))

    support = _member_with_rotation_sequence(
        "PURLIN_SUPPORT_%02d" % node_index,
        "step04_purlins",
        support_component,
        support_component["part_name"],
        "PURLIN_SUPPORT_%02d" % node_index,
        support_anchor,
        station_name,
        support_global_anchor,
        support_rotation,
        part_length_m=support_length,
        source_part_name=support_component["part_name"],
        section_reference={
            "x_m": 0.0,
            "y_m": 0.0,
            "z_m": support_length / 2.0,
            "rule": "ANGLE_OUTER_ROOT_SURFACE",
            "local_origin": [0.0, 0.0, 0.0],
            "local_anchor_offset": [0.0, 0.0, support_length / 2.0],
        },
        axis_checks=[
            {"name": "long_leg_axis", "local_vector": [1.0, 0.0, 0.0], "expected_global": e_n, "tolerance": 1.0e-6},
            {"name": "short_leg_axis", "local_vector": [0.0, 1.0, 0.0], "expected_global": _scale(e_s, -1.0), "tolerance": 1.0e-6},
            {"name": "length_axis_parallel_y", "local_vector": [0.0, 0.0, 1.0], "expected_global": [0.0, -1.0, 0.0], "tolerance": 1.0e-6},
        ],
        placement_note="ANGLE lower outer surface maps to the beam top-flange outer surface at %s; its long-leg outer face contacts the PURLIN_LOCAL web." % station_name,
    )
    local_purlin = _member_with_rotation_sequence(
        "PURLIN_LOCAL_%02d" % node_index,
        "step04_purlins",
        local_purlin_component,
        local_purlin_component["part_name"],
        "PURLIN_LOCAL_%02d" % node_index,
        purlin_anchor,
        station_name + "_PURLIN_LOWER_FLANGE_MIDPLANE",
        purlin_global_anchor,
        purlin_rotation,
        part_length_m=purlin_length,
        source_part_name=local_purlin_component["part_name"],
        section_reference={"x_m": 0.0, "y_m": 0.0, "z_m": purlin_length / 2.0, "rule": "C_CHANNEL_LOWER_FLANGE_AT_CENTER_Y"},
        axis_checks=[
            {"name": "flange_axis", "local_vector": [1.0, 0.0, 0.0], "expected_global": e_s, "tolerance": 1.0e-6},
            {"name": "web_axis", "local_vector": [0.0, 1.0, 0.0], "expected_global": e_n, "tolerance": 1.0e-6},
            {"name": "length_axis_parallel_y", "local_vector": [0.0, 0.0, 1.0], "expected_global": [0.0, -1.0, 0.0], "tolerance": 1.0e-6},
        ],
        placement_note="PURLIN_LOCAL length midpoint aligns with the INCLINED_BEAM section center plane; its lower-flange physical surface is 0.010 m above the beam upper flange.",
    )
    for member, code in ((support, "PURLIN_SUPPORT"), (local_purlin, "PURLIN_LOCAL")):
        member["component_code"] = code
        member["instance_id"] = "%s_%02d" % (code, node_index)
        member["placement_mode"] = "POINT_ORIENT"
        member["required"] = True
        member["placement_source"] = source
        member["origin"] = list(member["global_anchor"])

    gp_m = _dot(_sub(station, beam_origin), e_s) if beam_origin is not None else None
    support_matrix = [e_n, _scale(e_s, -1.0), [0.0, -1.0, 0.0]]
    purlin_matrix = [e_s, e_n, [0.0, -1.0, 0.0]]
    alignment_error = max(
        abs(_dot(_sub(support_global_anchor, beam_section_center), e_y)),
        abs(_dot(_sub(purlin_global_anchor, beam_section_center), e_y)),
    )
    node = {
        "node_id": "PURLIN_NODE_%02d" % node_index,
        "station": station_name,
        "gp_m": gp_m,
        "station_xyz": station,
        "beam_tangent": e_s,
        "beam_normal": e_n,
        "beam_surface_offset_m": beam_surface_offset,
        "beam_section_center_offset_m": beam_center_offset,
        "beam_section_center": beam_section_center,
        "support_part": support["part_name"],
        "support_instance": support["instance_id"],
        "local_purlin_part": local_purlin["part_name"],
        "local_purlin_instance": local_purlin["instance_id"],
        "beam_to_purlin_gap_m": PURLIN_BEAM_GAP_M,
        "purlin_shell_midplane_offset_m": purlin_midplane_offset,
        "support_local_origin": [0.0, 0.0, 0.0],
        "support_local_anchor": support_anchor,
        "support_anchor_xyz": support_global_anchor,
        "support_length_midpoint": support_global_anchor,
        "local_purlin_local_anchor": purlin_anchor,
        "local_purlin_center": purlin_global_anchor,
        "local_purlin_length_midpoint": purlin_global_anchor,
        "support_rotation_matrix_columns": support_matrix,
        "local_purlin_rotation_matrix_columns": purlin_matrix,
        "support_translation": list(support["translation"]),
        "local_purlin_translation": list(local_purlin["translation"]),
        "web_contact_side": "outer",
        "y_offset_support_m": _dot(_sub(support_global_anchor, station), e_y),
        "y_offset_local_m": _dot(_sub(purlin_global_anchor, station), e_y),
        "alignment_error_m": alignment_error,
    }
    checks = {
        "%s_SUPPORT_SURFACE" % station_name: {
            "station": station,
            "beam_surface_offset_m": beam_surface_offset,
            "expected": support_global_anchor,
            "actual": list(support["global_anchor"]),
            "passed": PASSED,
        },
        "%s_PURLIN_GAP" % station_name: {
            "gap_m": PURLIN_BEAM_GAP_M,
            "beam_surface_offset_m": beam_surface_offset,
            "shell_midplane_offset_m": purlin_midplane_offset,
            "passed": PASSED,
        },
        "%s_TRANSVERSE_ALIGNMENT" % station_name: {
            "beam_section_center": beam_section_center,
            "support_length_midpoint": support_global_anchor,
            "local_purlin_length_midpoint": purlin_global_anchor,
            "alignment_error_m": alignment_error,
            "passed": PASSED,
        },
    }
    return [support, local_purlin], node, checks


def _beam_top_surface_offset(component: dict[str, Any]) -> float:
    params = component.get("section_params_m") or {}
    section_height = component.get("section_height_m") or params.get("section_height_m") or params.get("h_m")
    if section_height in (None, ""):
        raise ValueError("INCLINED_BEAM metadata does not define section height.")
    height = float(section_height)
    thickness = float(component.get("thickness_m") or params.get("t_m") or 0.0)
    reference_y = float(_section_reference_xy(component)["y_m"])
    offset = height + thickness / 2.0 - reference_y
    if not math.isfinite(offset) or offset <= 0.0:
        raise ValueError("INCLINED_BEAM top-flange surface offset is invalid.")
    return offset


def _beam_section_center_offset(component: dict[str, Any]) -> float:
    params = component.get("section_params_m") or {}
    section_width = component.get("section_width_m") or params.get("section_width_m") or params.get("b_m")
    if section_width in (None, ""):
        raise ValueError("INCLINED_BEAM metadata does not define section width.")
    width = float(section_width)
    reference_x = float(_section_reference_xy(component)["x_m"])
    offset = width / 2.0 - reference_x
    if not math.isfinite(offset):
        raise ValueError("INCLINED_BEAM section-center offset is invalid.")
    return offset


def _add_purlin_nodes(
    plan: list[dict[str, Any]],
    components: dict[str, dict[str, Any]],
    points: dict[str, list[float]],
    beam_tangent: list[float],
    source: str,
    warnings: list[str],
    skipped: list[dict[str, str]],
    beam_origin: list[float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    support = components.get("PURLIN_SUPPORT")
    local_purlin = components.get("PURLIN_LOCAL")
    beam = components.get("INCLINED_BEAM")
    if not support or not local_purlin:
        for code, component in (("PURLIN_SUPPORT", support), ("PURLIN_LOCAL", local_purlin)):
            if not component:
                warnings.append("%s skipped: PART_MISSING." % code)
                skipped.append({"component_code": code, "reason": "PART_MISSING"})
        return [], {}
    if not beam:
        raise ValueError("Purlin placement requires INCLINED_BEAM component metadata.")
    beam_surface_offset = _beam_top_surface_offset(beam)
    beam_center_offset = _beam_section_center_offset(beam)

    nodes: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}
    for index, point_name in enumerate(PURLIN_STATION_POINT_NAMES, start=1):
        if point_name not in points:
            warnings.append("Purlin node %02d skipped: PLACEMENT_DATA_MISSING (%s)." % (index, point_name))
            skipped.extend([
                {"component_code": "PURLIN_SUPPORT", "reason": "PLACEMENT_DATA_MISSING", "station": point_name},
                {"component_code": "PURLIN_LOCAL", "reason": "PLACEMENT_DATA_MISSING", "station": point_name},
            ])
            continue
        pair, node, node_checks = _create_purlin_node_pair(
            support,
            local_purlin,
            point_name,
            points[point_name],
            index,
            beam_tangent,
            beam_surface_offset,
            beam_center_offset,
            source,
            beam_origin=beam_origin,
        )
        plan.extend(pair)
        nodes.append(node)
        checks.update(node_checks)
    return nodes, checks


def _line_member_from_points(
    name: str,
    component: dict[str, Any],
    start: list[float],
    end: list[float],
    instance_id: str,
    source: str,
    required: bool = True,
) -> dict[str, Any]:
    if distance(start, end) <= 1.0e-12:
        raise ValueError("LINE placement %s has identical start and end points." % instance_id)
    rotation = rotate_y_for_local_z_to_vector(start, end)
    member = _member(
        name,
        "step04_initial_assembly",
        component,
        _local_reference_point(component, 0.0),
        name + "_START",
        {name + "_START": _point(*start)},
        rotation,
        roll_about_axis_deg=_default_roll_about_axis_deg(name, component),
    )
    member["target_point_name"] = name + "_END"
    member["target_point"] = list(end)
    axis = _scale(_sub(end, start), 1.0 / distance(start, end))
    return _normalize_instance_member(member, instance_id, "LINE", required, source, start, end, start, axis)


def _finalize_instance_plan(payload: dict[str, Any], source: str) -> dict[str, Any]:
    plan: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    point_names = ("S", "P", "Q", "R")
    for member in payload.get("members", []):
        name = str(member.get("name") or member.get("component_code") or "INSTANCE")
        code = str(member.get("component_code") or name)
        if name.startswith("PURLIN_SUPPORT_"):
            code = "PURLIN_SUPPORT"
        elif name.startswith("PURLIN_"):
            code = "PURLIN_LOCAL"
            member["component_code"] = code
        counters[code] = counters.get(code, 0) + 1
        instance_id = "%s_%02d" % (code, counters[code])
        start = list(member.get("global_anchor") or []) or None
        end = list(member.get("target_point") or []) or None
        if code == "INCLINED_BEAM" and "G_global" in payload.get("points", {}):
            start = _coords(payload["points"]["G_global"])
            theta = math.radians(float(payload.get("inputs", {}).get("theta_deg") or 0.0))
            beam_length = float(member.get("part_length_m") or 0.0)
            end = _add(start, _scale([math.cos(theta), 0.0, math.sin(theta)], beam_length))
        elif code == "COLUMN_DOWN" and start:
            end = _add(start, [0.0, 0.0, float(member.get("part_length_m") or 0.0)])
        elif code in ("COLUMN_UP", "COLUMN") and start:
            end = list(start)
            start = _add(end, [0.0, 0.0, -float(member.get("part_length_m") or 0.0)])
        placement = "LINE" if end is not None else "POINT_ORIENT"
        axis = _scale(_sub(end, start), 1.0 / distance(start, end)) if start and end and distance(start, end) > 1.0e-12 else None
        plan.append(_normalize_instance_member(member, instance_id, placement, True, source, start, end, start, axis))

    components = payload.get("_components_by_code") or {}
    hoop = _resolve_hoop_component(components, 1)
    if hoop and not any(item.get("canonical_role") == "HOOP" or is_hoop_component_code(item.get("component_code", "")) for item in plan):
        points = payload.get("points", {})
        if "H1" in points or ("B" in points and "D" in points):
            center = _coords(points["H1"]) if "H1" in points else _scale(_add(_coords(points["B"]), _coords(points["D"])), 0.5)
            pair, group = _create_hoop_pair(hoop, center, 1, source)
            plan.extend(pair)
            payload.setdefault("hoop_groups", []).append(group)

    payload.pop("_components_by_code", None)
    payload["instance_plan"] = plan
    payload["members"] = plan
    payload["required_part_names"] = sorted({item["part_name"] for item in plan})
    payload["skipped_instances"] = payload.get("skipped_instances", [])
    ids = [item["instance_id"] for item in plan]
    if len(ids) != len(set(ids)):
        payload.setdefault("errors", []).append("Instance ids are not unique.")
    return payload


def _build_sp_dc_payload(
    excel_path: str | Path,
    components_path: str | Path,
    project_code: str,
    model_name: str,
) -> dict[str, Any]:
    points_raw, statuses = _read_named_points(excel_path)
    components = load_components(components_path)
    required_points = ("O", "L_TOP", "F", "G", "UF0", "UF1", "UR0", "UR1", "B", "C", "D", "E")
    missing_points = [name for name in required_points if name not in points_raw]
    if missing_points:
        raise ValueError("SP_DC missing required control points: %s" % ", ".join(missing_points))
    required_codes = ("COLUMN_DOWN", "COLUMN_FRONT", "COLUMN_REAR", "BRACE_FRONT", "BRACE_REAR", "INCLINED_BEAM")
    missing_codes = [code for code in required_codes if code not in components]
    if missing_codes:
        raise ValueError("SP_DC Step02 missing required component_code: %s" % ", ".join(missing_codes))

    points = {name: _point(*coords, status=statuses.get(name, ""), note="Excel final control point") for name, coords in points_raw.items()}
    points["G_global"] = dict(points["G"])
    source = "SP_DC adapter: Excel final control points"
    plan = [
        _line_member_from_points("COLUMN_DOWN", components["COLUMN_DOWN"], points_raw["O"], points_raw["L_TOP"], "COLUMN_DOWN_01", source),
        _line_member_from_points("COLUMN_FRONT", components["COLUMN_FRONT"], points_raw["UF0"], points_raw["UF1"], "COLUMN_FRONT_01", source),
        _line_member_from_points("COLUMN_REAR", components["COLUMN_REAR"], points_raw["UR0"], points_raw["UR1"], "COLUMN_REAR_01", source),
        _line_member_from_points("BRACE_FRONT", components["BRACE_FRONT"], points_raw["B"], points_raw["C"], "BRACE_FRONT_01", source),
        _line_member_from_points("BRACE_REAR", components["BRACE_REAR"], points_raw["D"], points_raw["E"], "BRACE_REAR_01", source),
        _line_member_from_points("INCLINED_BEAM", components["INCLINED_BEAM"], points_raw["G"], points_raw["F"], "INCLINED_BEAM_01", source),
    ]
    warnings: list[str] = []
    skipped: list[dict[str, str]] = []

    hoop_points = [name for name in ("H1", "H2", "H3") if name in points_raw]
    legacy_hoop_components = [components[code] for code in ("HOOP_1", "HOOP_2") if code in components]
    has_canonical_hoop = any(is_hoop_component_code(code) for code in components)
    hoop_groups = []
    if hoop_points and (has_canonical_hoop or legacy_hoop_components):
        for index, point_name in enumerate(hoop_points, start=1):
            primary = _resolve_hoop_component(components, index) if has_canonical_hoop else legacy_hoop_components[0]
            if primary is None:
                continue
            secondary = None if has_canonical_hoop else (legacy_hoop_components[1] if len(legacy_hoop_components) > 1 else None)
            pair, group = _create_hoop_pair(primary, points_raw[point_name], index, source, secondary)
            plan.extend(pair)
            hoop_groups.append(group)
    elif has_canonical_hoop or legacy_hoop_components:
        warnings.append("HOOP skipped: PLACEMENT_DATA_MISSING (H1/H2/H3).")
        skipped.append({"component_code": "HOOP", "reason": "PLACEMENT_DATA_MISSING"})

    checks: dict[str, Any] = {}
    tolerance = (_read_named_value(excel_path, "length_tolerance_mm") or 10.0) / 1000.0
    for code, start_name, end_name in (
        ("COLUMN_DOWN", "O", "L_TOP"),
        ("COLUMN_FRONT", "UF0", "UF1"),
        ("COLUMN_REAR", "UR0", "UR1"),
        ("BRACE_FRONT", "B", "C"),
        ("BRACE_REAR", "D", "E"),
    ):
        component = components[code]
        checks[code + "_LENGTH"] = member_length_check(points, start_name, end_name, component.get("length_m"), tolerance)
        if checks[code + "_LENGTH"]["passed"] == FAILED:
            warnings.append("%s control-point length differs from Step02 Part length; Part will not be scaled." % code)

    beam_direction = _scale(_sub(points_raw["F"], points_raw["G"]), 1.0 / distance(points_raw["F"], points_raw["G"]))
    purlin_nodes, purlin_checks = _add_purlin_nodes(
        plan,
        components,
        points_raw,
        beam_direction,
        source,
        warnings,
        skipped,
        beam_origin=points_raw["G"],
    )
    checks.update(purlin_checks)
    theta_deg = _read_named_value(excel_path, "theta_deg")
    payload = {
        "meta": {
            "project_code": project_code,
            "project_id": project_code,
            "structure_type": "SP_DC",
            "model_name": model_name,
            "source_excel": str(Path(excel_path).as_posix()),
            "source_components": str(Path(components_path).as_posix()),
            "coordinate_system": "X right, Y out of elevation plane, Z up; units m-kg-N-Pa",
            "adapter": "SP_DC",
        },
        "units": {"length": "m", "mass": "kg", "force": "N", "stress": "Pa"},
        "inputs": {"theta_deg": theta_deg},
        "points": points,
        "beam_anchor": {
            "part_name": components["INCLINED_BEAM"]["part_name"],
            "stations": {
                "C": distance(points_raw["G"], points_raw["C"]),
                "F": distance(points_raw["G"], points_raw["F"]),
                "E": distance(points_raw["G"], points_raw["E"]),
            },
            "section_sets": {"C": "SET_BEAM_SEC_C", "F": "SET_BEAM_SEC_F", "E": "SET_BEAM_SEC_E"},
            "reference_local_origin": _local_reference_point(components["INCLINED_BEAM"], 0.0),
            "direction_u": beam_direction,
        },
        "instance_plan": plan,
        "members": plan,
        "required_part_names": sorted({item["part_name"] for item in plan}),
        "checks": checks,
        "member_checks": checks,
        "warnings": warnings,
        "errors": [],
        "skipped_instances": skipped,
        "hoop_groups": hoop_groups,
        "purlin_nodes": purlin_nodes,
    }
    ids = [item["instance_id"] for item in plan]
    if len(ids) != len(set(ids)):
        payload["errors"].append("Instance ids are not unique.")
    return payload


def build_payload(
    excel_path: str | Path,
    components_path: str | Path,
    project_code: str = DEFAULT_PROJECT_CODE,
    model_name: str | None = None,
) -> dict[str, Any]:
    coordinate_project_id = project_id_from_path(excel_path)
    effective_project_id = coordinate_project_id if project_code == DEFAULT_PROJECT_CODE else project_code
    step02_filename_id = project_id_from_path(components_path)
    step02_has_project_filename = step02_filename_id != Path(components_path).stem
    step02_model_name = read_step02_model_name(components_path)
    actual_model_name = step02_model_name or model_name or effective_project_id
    expected_model_name = model_name or effective_project_id
    if coordinate_project_id != effective_project_id:
        raise ValueError("Coordinate project_id %s does not match requested project_id %s." % (coordinate_project_id, effective_project_id))
    if Path(components_path).suffix.lower() == ".py" and step02_has_project_filename and step02_filename_id != effective_project_id:
        raise ValueError("Step02 project_id %s does not match coordinate project_id %s." % (step02_filename_id, effective_project_id))
    if actual_model_name != effective_project_id or expected_model_name != effective_project_id:
        raise ValueError("Step02 MODEL_NAME %s must exactly match coordinate project_id %s." % (actual_model_name, effective_project_id))

    structure_type = detect_structure_type(effective_project_id)
    if structure_type == "SP_DC":
        return _build_sp_dc_payload(excel_path, components_path, effective_project_id, effective_project_id)

    payload = _build_sp_sc_payload(excel_path, components_path, project_code=effective_project_id, model_name=effective_project_id)
    payload["meta"].update({"project_id": effective_project_id, "structure_type": "SP_SC", "adapter": "SP_SC"})
    payload["_components_by_code"] = load_components(components_path)
    return _finalize_instance_plan(payload, "SP_SC adapter: existing A/B/C/D/E/F/G control-point logic")


def write_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def generate_abaqus_scripts(
    payload: dict[str, Any],
    output_dir: str | Path,
    json_path: str | Path | None,
    reports_dir: str | Path | None = None,
) -> list[Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir = Path(reports_dir) if reports_dir else out_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    project = payload["meta"]["project_code"]
    scripts = [
        ("full_main_frame", "%s_assembly_frame.py" % project),
    ]
    paths: list[Path] = []
    for phase, filename in scripts:
        script = build_abaqus_script(
            phase=phase,
            payload=payload,
            report_path=report_dir / ("%s_%s_report.json" % (project, phase)),
            cae_path=report_dir / ("%s_%s.cae" % (project, phase)),
        )
        path = out_dir / filename
        path.write_text(script, encoding="utf-8")
        paths.append(path)
    return paths


def build_abaqus_script(
    phase: str,
    payload: dict[str, Any],
    report_path: Path,
    cae_path: Path,
) -> str:
    return Template(ABAQUS_SCRIPT_TEMPLATE).substitute(
        phase=phase,
        assembly_payload_json=json.dumps(payload, ensure_ascii=False, indent=2),
        report_filename=Path(report_path).name,
        cae_filename=Path(cae_path).name,
        script_name="%s.py" % phase,
    )


ABAQUS_SCRIPT_TEMPLATE = r'''# -*- coding: utf-8 -*-
"""Abaqus Assembly stage script generated from coordinate Excel.

Run inside Abaqus/CAE after the five main Parts already exist in the model.
For example:
    abaqus cae noGUI=$script_name
"""
from __future__ import print_function

import codecs
import json
import math
import os

from abaqus import mdb
from abaqusConstants import *
import mesh
import regionToolset


PHASE = "$phase"
ASSEMBLY_DATA = json.loads(r"""$assembly_payload_json""")


def _resolve_report_path(filename):
    candidates = []
    try:
        script_folder = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_folder, "..", "reports"))
        candidates.append(script_folder)
    except Exception:
        pass
    candidates.append(os.path.join(os.getcwd(), "reports"))
    candidates.append(os.getcwd())
    for candidate in candidates:
        if candidate:
            try:
                if os.path.exists(candidate):
                    return os.path.join(candidate, filename)
            except Exception:
                pass
    return os.path.join(os.getcwd(), filename)


REPORT_PATH = _resolve_report_path("$report_filename")
SAVE_AS_PATH = r""
SUGGESTED_SAVE_AS_PATH = _resolve_report_path("$cae_filename")
DEFAULT_BEAM_SECTION_SET_NAMES = ("SET_BEAM_SEC_C", "SET_BEAM_SEC_F", "SET_BEAM_SEC_E")


try:
    unicode
except NameError:
    unicode = str


def _ascii(value):
    if value is None:
        return ""
    if isinstance(value, unicode):
        return value.encode("ascii")
    return str(value)


def _float_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _ensure_parent(path):
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.exists(folder):
        os.makedirs(folder)


def _model(data):
    project_code = _ascii(data.get("meta", {}).get("project_code") or "")
    model_name = _ascii(data.get("meta", {}).get("model_name") or project_code)
    if project_code and model_name != project_code:
        raise RuntimeError("Assembly model name %s does not match project prefix %s." % (model_name, project_code))
    if model_name not in mdb.models:
        raise RuntimeError("Project model %s not found. Run %s_create_parts_in_cae.py first." % (model_name, project_code or model_name))
    return mdb.models[model_name]


def _point(data, name):
    return tuple(float(v) for v in data["points"][name]["coords"])


def _distance(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _rotate_x(point, angle_deg):
    angle = math.radians(float(angle_deg))
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return (x, y * c - z * s, y * s + z * c)


def _rotate_y(point, angle_deg):
    angle = math.radians(float(angle_deg))
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return (x * c + z * s, y, -x * s + z * c)


def _rotate_z(point, angle_deg):
    angle = math.radians(float(angle_deg))
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = point
    return (x * c - y * s, x * s + y * c, z)


def _apply_rotation_sequence(point, rotation_sequence):
    result = tuple(float(v) for v in point)
    for rotation in rotation_sequence or ():
        axis = str(rotation.get("axis") or "").upper()
        angle = float(rotation.get("angle_deg") or 0.0)
        if axis == "X":
            result = _rotate_x(result, angle)
        elif axis == "Y":
            result = _rotate_y(result, angle)
        elif axis == "Z":
            result = _rotate_z(result, angle)
        else:
            raise RuntimeError("Unsupported rotation axis for %s: %s" % (rotation, axis))
    return result


def _rotation_axis_direction(axis):
    axis = str(axis or "").upper()
    if axis == "X":
        return (1.0, 0.0, 0.0)
    if axis == "Y":
        return (0.0, 1.0, 0.0)
    if axis == "Z":
        return (0.0, 0.0, 1.0)
    raise RuntimeError("Unsupported rotation axis: %s" % axis)


def _add3(a, b):
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]), float(a[2]) + float(b[2]))


def _sub3(a, b):
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


def _dot(a, b):
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def _cross(a, b):
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _unit(vector):
    length = math.sqrt(_dot(vector, vector))
    if length <= 1.0e-15:
        return (0.0, 0.0, 1.0)
    return (float(vector[0]) / length, float(vector[1]) / length, float(vector[2]) / length)


def _rotate_about_axis(point, axis_point, axis_direction, angle_deg):
    axis = _unit(axis_direction)
    rel = _sub3(point, axis_point)
    angle = math.radians(float(angle_deg))
    c = math.cos(angle)
    s = math.sin(angle)
    cross = _cross(axis, rel)
    along = _dot(axis, rel)
    rotated = (
        rel[0] * c + cross[0] * s + axis[0] * along * (1.0 - c),
        rel[1] * c + cross[1] * s + axis[1] * along * (1.0 - c),
        rel[2] * c + cross[2] * s + axis[2] * along * (1.0 - c),
    )
    return _add3(axis_point, rotated)


def _member_axis_direction(member):
    if member.get("rotation_sequence"):
        return _unit(_apply_rotation_sequence((0.0, 0.0, 1.0), member.get("rotation_sequence")))
    return _unit(_rotate_y((0.0, 0.0, 1.0), float(member.get("rotate_y_deg") or 0.0)))


def _transform_member(local_point, member):
    if member.get("rotation_sequence"):
        rotated = _apply_rotation_sequence(tuple(float(v) for v in local_point), member.get("rotation_sequence"))
        transformed = _add3(rotated, tuple(float(v) for v in member.get("translation", (0.0, 0.0, 0.0))))
    else:
        rotated = _rotate_y(tuple(float(v) for v in local_point), float(member.get("rotate_y_deg") or 0.0))
        transformed = _add3(rotated, tuple(float(v) for v in member.get("translation", (0.0, 0.0, 0.0))))
        roll_about_axis_deg = float(member.get("roll_about_axis_deg") or 0.0)
        if abs(roll_about_axis_deg) > 1.0e-12:
            axis_point = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
            transformed = _rotate_about_axis(transformed, axis_point, _member_axis_direction(member), roll_about_axis_deg)
    post_rotation = member.get("post_rotation") or {}
    if abs(float(post_rotation.get("angle_deg") or 0.0)) > 1.0e-12:
        transformed = _rotate_about_axis(
            transformed,
            tuple(float(v) for v in post_rotation.get("axis_point", (0.0, 0.0, 0.0))),
            tuple(float(v) for v in post_rotation.get("axis_direction", (0.0, 0.0, 1.0))),
            float(post_rotation["angle_deg"]),
        )
    return transformed


def _ensure_material(model, material):
    mat_name = _ascii((material or {}).get("abaqus_name") or "MAT_MANUAL_CHECK")
    if mat_name in model.materials:
        return mat_name
    mat = model.Material(name=mat_name)
    elastic_modulus = (material or {}).get("elastic_modulus_pa")
    poisson_ratio = (material or {}).get("poisson_ratio")
    if elastic_modulus is not None and poisson_ratio is not None:
        mat.Elastic(table=((float(elastic_modulus), float(poisson_ratio)),))
    density = (material or {}).get("density_kg_per_m3")
    if density is not None:
        mat.Density(table=((float(density),),))
    return mat_name


def _profile_points(component):
    params = component.get("section_params_m") or {}
    kind = component.get("section_kind")
    if kind == "C_CHANNEL":
        h = float(params["h_m"])
        b = float(params["b_m"])
        lip = float(params["lip_m"])
        return [(b, lip), (b, 0.0), (0.0, 0.0), (0.0, h), (b, h), (b, h - lip)]
    raise RuntimeError("Can only derive 50mm purlin from C_CHANNEL, got %s." % kind)


def _create_shell_part(model, component):
    part_name = _ascii(component["part_name"])
    if part_name in model.parts:
        return model.parts[part_name]

    length = _float_or_none(component.get("length_m")) or 0.05
    thickness = _float_or_none(component.get("thickness_m"))
    if thickness is None:
        raise RuntimeError("Shell Part %s requires thickness_m." % part_name)

    sketch = model.ConstrainedSketch(name=_ascii("SK_" + str(component["part_name"])), sheetSize=max(length, 1.0) * 2.0)
    points = _profile_points(component)
    for start, end in zip(points[:-1], points[1:]):
        sketch.Line(point1=start, point2=end)

    part = model.Part(name=part_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShellExtrude(sketch=sketch, depth=length)

    material_name = _ensure_material(model, component.get("material", {}))
    section_name = _ascii("SEC_" + str(component["part_name"]))
    if section_name not in model.sections:
        model.HomogeneousShellSection(
            name=section_name,
            preIntegrate=OFF,
            material=material_name,
            thicknessType=UNIFORM,
            thickness=thickness,
        )
    region = regionToolset.Region(faces=part.faces[:])
    part.SectionAssignment(region=region, sectionName=section_name)
    elem_type = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD)
    part.seedPart(size=0.02, deviationFactor=0.1, minSizeFactor=0.1)
    part.setElementType(regions=(part.faces[:],), elemTypes=(elem_type,))
    part.generateMesh()
    return part


def _effective_part(model, member):
    part_component = member.get("part_component")
    if part_component:
        source_name = member.get("source_part_name")
        if source_name:
            _part(model, source_name)
        component = dict(part_component)
        component["part_name"] = member["part_name"]
        component["length_m"] = float(member.get("part_length_m") or component.get("length_m") or 0.05)
        return _create_shell_part(model, component)
    return _part(model, member["part_name"])


def _part(model, name):
    key = _ascii(name)
    if key not in model.parts:
        raise RuntimeError("Missing Part %s. Run the generated Part creation script first." % name)
    return model.parts[key]


def _delete_instance(assembly, name):
    key = _ascii(name)
    if key in assembly.instances:
        try:
            del assembly.features[key]
        except Exception:
            try:
                del assembly.instances[key]
            except Exception:
                pass


def _delete_set(container, name):
    key = _ascii(name)
    try:
        if key in container.sets:
            del container.sets[key]
    except Exception:
        pass


def _edges_at_station(part, station):
    # Prefer Abaqus EdgeArray selection. Creating a Set from a plain Python
    # list of Edge objects is less reliable in Abaqus/CAE 2020.
    for tol in (1.0e-7, 1.0e-6, 1.0e-5, 1.0e-4, 1.0e-3):
        try:
            edges = part.edges.getByBoundingBox(
                xMin=-1000.0,
                yMin=-1000.0,
                zMin=station - tol,
                xMax=1000.0,
                yMax=1000.0,
                zMax=station + tol,
            )
            if len(edges):
                return edges, tol, "bounding_box"
        except Exception:
            pass

    found = []
    for edge in part.edges:
        try:
            point = edge.pointOn[0]
            if abs(float(point[2]) - station) <= 1.0e-5:
                found.append(edge)
        except Exception:
            pass
    return tuple(found), 1.0e-5, "point_on"


def _instance(model, member):
    assembly = model.rootAssembly
    inst_name = _ascii(member["instance_name"])
    _delete_instance(assembly, inst_name)
    part = _effective_part(model, member)
    assembly.Instance(name=inst_name, part=part, dependent=ON)
    rotation_sequence = member.get("rotation_sequence") or []
    rotate_y_deg = float(member.get("rotate_y_deg") or 0.0)
    if rotation_sequence:
        for rotation in rotation_sequence:
            angle = float(rotation.get("angle_deg") or 0.0)
            if abs(angle) <= 1.0e-12:
                continue
            assembly.rotate(
                instanceList=(inst_name,),
                axisPoint=(0.0, 0.0, 0.0),
                axisDirection=_rotation_axis_direction(rotation.get("axis")),
                angle=angle,
            )
    elif abs(rotate_y_deg) > 1.0e-12:
        assembly.rotate(
            instanceList=(inst_name,),
            axisPoint=(0.0, 0.0, 0.0),
            axisDirection=(0.0, 1.0, 0.0),
            angle=rotate_y_deg,
        )
    translation = tuple(float(v) for v in member.get("translation", (0.0, 0.0, 0.0)))
    if max(abs(translation[0]), abs(translation[1]), abs(translation[2])) > 1.0e-12:
        assembly.translate(instanceList=(inst_name,), vector=translation)
    roll_about_axis_deg = float(member.get("roll_about_axis_deg") or 0.0)
    if not rotation_sequence and abs(roll_about_axis_deg) > 1.0e-12:
        axis_point = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
        assembly.rotate(
            instanceList=(inst_name,),
            axisPoint=axis_point,
            axisDirection=_member_axis_direction(member),
            angle=roll_about_axis_deg,
        )
    post_rotation = member.get("post_rotation") or {}
    post_angle = float(post_rotation.get("angle_deg") or 0.0)
    if abs(post_angle) > 1.0e-12:
        assembly.rotate(
            instanceList=(inst_name,),
            axisPoint=tuple(float(v) for v in post_rotation.get("axis_point", (0.0, 0.0, 0.0))),
            axisDirection=tuple(float(v) for v in post_rotation.get("axis_direction", (0.0, 0.0, 1.0))),
            angle=post_angle,
        )
    return {
        "instance_name": member["instance_name"],
        "part_name": member["part_name"],
        "source_part_name": member.get("source_part_name"),
        "rotate_y_deg": rotate_y_deg,
        "rotation_sequence": rotation_sequence,
        "roll_about_axis_deg": roll_about_axis_deg,
        "translation": list(translation),
        "section_reference": member.get("section_reference"),
        "open_side_global": member.get("open_side_global"),
        "placement_note": member.get("placement_note"),
        "post_rotation": post_rotation or None,
    }


def _partition_beam(model, data):
    beam = data["beam_anchor"]
    part = _part(model, beam["part_name"])
    report = {"part_name": beam["part_name"], "stations": {}, "sets": [], "warnings": []}
    stations = beam.get("stations", {})
    for label in ("C", "F", "E"):
        if label not in stations:
            continue
        station = float(stations[label])
        datum = part.DatumPlaneByPrincipalPlane(principalPlane=XYPLANE, offset=station)
        try:
            part.PartitionFaceByDatumPlane(datumPlane=part.datums[datum.id], faces=part.faces[:])
        except Exception as exc:
            report["warnings"].append("Partition at %s=%.6f failed or already exists: %s" % (label, station, exc))

        set_name = _ascii(beam.get("section_sets", {}).get(label) or ("SET_BEAM_SEC_" + label))
        if set_name in part.sets:
            report["sets"].append(set_name)
            report["warnings"].append("Set %s already exists; reused it." % set_name)
            report["stations"][label] = station
            continue

        edges, edge_tol, edge_method = _edges_at_station(part, station)
        if edges:
            try:
                part.Set(edges=edges, name=set_name)
                report["sets"].append(set_name)
                report["warnings"].append("Created %s using %s tolerance %.1e." % (set_name, edge_method, edge_tol))
            except Exception as exc:
                report["warnings"].append("Could not create edge set %s at station %.6f: %s" % (set_name, station, exc))
        else:
            report["warnings"].append("No partition edge found for %s at station %.6f." % (set_name, station))
        report["stations"][label] = station

    return report


def _members_for_phase(data):
    all_members = data.get("instance_plan") or data.get("members", [])
    if PHASE == "step01_columns":
        names = set(["COLUMN_DOWN", "COLUMN_UP", "COLUMN"])
    elif PHASE == "step02_beam":
        names = set(["INCLINED_BEAM"])
    elif PHASE == "step03_main_frame":
        names = set(["COLUMN_DOWN", "COLUMN_UP", "COLUMN", "INCLINED_BEAM", "BRACE_FRONT", "BRACE_REAR"])
    elif PHASE == "step04_purlins":
        names = set(member.get("name") for member in all_members if member.get("phase") == "step04_purlins")
    else:
        return list(all_members)
    return [member for member in all_members if member.get("name") in names]


def _transform_member_vector(local_vector, member):
    if member.get("rotation_sequence"):
        rotated = _unit(_apply_rotation_sequence(tuple(float(v) for v in local_vector), member.get("rotation_sequence")))
    else:
        rotated = _rotate_y(_rotate_z(tuple(float(v) for v in local_vector), float(member.get("roll_about_axis_deg") or 0.0)), float(member.get("rotate_y_deg") or 0.0))
    post_rotation = member.get("post_rotation") or {}
    if abs(float(post_rotation.get("angle_deg") or 0.0)) > 1.0e-12:
        rotated = _rotate_about_axis(
            rotated,
            (0.0, 0.0, 0.0),
            tuple(float(v) for v in post_rotation.get("axis_direction", (0.0, 0.0, 1.0))),
            float(post_rotation["angle_deg"]),
        )
    return _unit(rotated)


def _validate_member(member, data):
    errors = []
    anchor = _transform_member(member.get("local_anchor", (0.0, 0.0, 0.0)), member)
    target_anchor = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
    anchor_error = _distance(anchor, target_anchor)
    if anchor_error > 1.0e-6:
        errors.append("%s anchor error %.9g m" % (member["name"], anchor_error))
    axis_validation = {}
    for check in member.get("axis_checks", []):
        actual = _transform_member_vector(check.get("local_vector", (0.0, 0.0, 1.0)), member)
        expected = _unit(tuple(float(v) for v in check.get("expected_global", (0.0, 0.0, 1.0))))
        error = _distance(actual, expected)
        tolerance = float(check.get("tolerance") or 1.0e-6)
        if error > tolerance:
            errors.append("%s %s axis error %.9g" % (member["name"], check.get("name"), error))
        axis_validation[str(check.get("name"))] = {
            "actual": list(actual),
            "expected": list(expected),
            "error": error,
            "tolerance": tolerance,
        }

    if member.get("target_point_name"):
        part_length = float(member.get("part_length_m") or 0.0)
        local_anchor = member.get("local_anchor", (0.0, 0.0, 0.0))
        local_end = (float(local_anchor[0]), float(local_anchor[1]), part_length)
        transformed_end = _transform_member(local_end, member)
        target = tuple(float(v) for v in member.get("target_point", (0.0, 0.0, 0.0)))
        # Braces may include connection offsets, so report this value rather than failing hard.
        end_error = _distance(transformed_end, target)
        return {"anchor_error_m": anchor_error, "end_error_m": end_error, "axis_validation": axis_validation, "errors": errors}
    return {"anchor_error_m": anchor_error, "axis_validation": axis_validation, "errors": errors}


def _validate_beam(data):
    beam_member = None
    for member in data.get("instance_plan") or data.get("members", []):
        if member.get("name") == "INCLINED_BEAM":
            beam_member = member
            break
    if not beam_member:
        return {}
    stations = data["beam_anchor"]["stations"]
    beam_local_origin = data["beam_anchor"].get("reference_local_origin") or [0.0, 0.0, 0.0]
    ref_x = float(beam_local_origin[0])
    ref_y = float(beam_local_origin[1])
    validation = {}
    for label in ("C", "F", "E"):
        actual = _transform_member((ref_x, ref_y, float(stations[label])), beam_member)
        expected = _point(data, label)
        validation[label] = {"actual": list(actual), "expected": list(expected), "error_m": _distance(actual, expected)}
    actual_g = _transform_member((ref_x, ref_y, 0.0), beam_member)
    expected_g = _point(data, "G_global")
    validation["G_global"] = {"actual": list(actual_g), "expected": list(expected_g), "error_m": _distance(actual_g, expected_g)}
    return validation


def main():
    data = ASSEMBLY_DATA
    if data.get("errors"):
        raise RuntimeError("Step04 preflight failed: %s" % "; ".join(str(item) for item in data.get("errors", [])))
    model = _model(data)
    assembly = model.rootAssembly
    report = {"phase": PHASE, "warnings": list(data.get("warnings", [])), "instances": [], "partition": None, "validation": {}, "hoop_groups": list(data.get("hoop_groups", [])), "purlin_nodes": list(data.get("purlin_nodes", []))}
    phase_members = _members_for_phase(data)

    instance_names = [_ascii(member.get("instance_id") or member.get("instance_name")) for member in phase_members]
    if len(instance_names) != len(set(instance_names)):
        raise RuntimeError("Step04 preflight failed: instance_id values are not unique.")

    missing = []
    for name in sorted(set(member.get("source_part_name") or member["part_name"] for member in phase_members)):
        if _ascii(name) not in model.parts:
            missing.append(name)
    if missing:
        project = data.get("meta", {}).get("project_code") or "project"
        raise RuntimeError("Missing required Parts for %s: %s. Run %s_create_parts_in_cae.py first." % (PHASE, ", ".join(missing), project))

    for group in data.get("hoop_groups", []):
        center = tuple(float(value) for value in group.get("center", ()))
        rotation = group.get("pair_rotation") or {}
        axis = tuple(float(value) for value in rotation.get("axis_direction", ()))
        if len(center) != 3 or len(axis) != 3 or math.sqrt(_dot(axis, axis)) <= 1.0e-12:
            raise RuntimeError("Step04 preflight failed: invalid HOOP center or rotation axis for %s." % group.get("group_id"))
        print("HOOP group %s:" % str(group.get("group_id") or "").replace("HOOP_", ""))
        print("  center = %s" % (center,))
        print("  part = %s" % group.get("part_a"))
        print("  instance A = %s" % group.get("instance_a"))
        print("  instance B = %s" % group.get("instance_b"))
        print("  pair rotation = 180 deg about column axis")

    for node in data.get("purlin_nodes", []):
        station = tuple(float(value) for value in node.get("station_xyz", ()))
        tangent = tuple(float(value) for value in node.get("beam_tangent", ()))
        normal = tuple(float(value) for value in node.get("beam_normal", ()))
        if len(station) != 3 or len(tangent) != 3 or len(normal) != 3 or math.sqrt(_dot(tangent, tangent)) <= 1.0e-12 or math.sqrt(_dot(normal, normal)) <= 1.0e-12:
            raise RuntimeError("Step04 preflight failed: invalid station or beam frame for %s." % node.get("node_id"))
        print("PURLIN NODE %s" % str(node.get("node_id") or "").replace("PURLIN_NODE_", ""))
        print("  GP = %s m" % node.get("gp_m"))
        print("  station = %s" % node.get("station"))
        print("  P = %s" % (station,))
        print("  beam_tangent = %s" % (tangent,))
        print("  beam_normal = %s" % (normal,))
        print("  beam_surface_offset = %s m" % node.get("beam_surface_offset_m"))
        print("  support_part = %s" % node.get("support_part"))
        print("  support_instance = %s" % node.get("support_instance"))
        print("  local_purlin_part = %s" % node.get("local_purlin_part"))
        print("  local_purlin_instance = %s" % node.get("local_purlin_instance"))
        print("  support_anchor = %s" % (tuple(node.get("support_anchor_xyz") or ()),))
        print("  support_local_anchor = %s" % (tuple(node.get("support_local_anchor") or ()),))
        print("  local_anchor = %s" % (tuple(node.get("local_purlin_local_anchor") or ()),))
        print("  support_rotation = %s" % (node.get("support_rotation_matrix_columns"),))
        print("  local_purlin_rotation_matrix = %s" % (node.get("local_purlin_rotation_matrix_columns"),))
        print("  support_translation = %s" % (tuple(node.get("support_translation") or ()),))
        print("  local_purlin_translation = %s" % (tuple(node.get("local_purlin_translation") or ()),))
        print("  local_purlin_center = %s" % (tuple(node.get("local_purlin_center") or ()),))
        print("  beam_section_center = %s" % (tuple(node.get("beam_section_center") or ()),))
        print("  support_length_midpoint = %s" % (tuple(node.get("support_length_midpoint") or ()),))
        print("  local_purlin_length_midpoint = %s" % (tuple(node.get("local_purlin_length_midpoint") or ()),))
        print("  Y_offset_support = %s m" % node.get("y_offset_support_m"))
        print("  Y_offset_local = %s m" % node.get("y_offset_local_m"))
        print("  alignment_error = %s m" % node.get("alignment_error_m"))
        print("  web contact side = %s" % node.get("web_contact_side"))
        print("  gap = 0.010 m")

    if PHASE in ("step02_beam", "step03_main_frame", "full_main_frame"):
        report["partition"] = _partition_beam(model, data)

    for member in phase_members:
        report["instances"].append(_instance(model, member))
        report["validation"][member["name"]] = _validate_member(member, data)

    if PHASE in ("step02_beam", "step03_main_frame", "full_main_frame"):
        report["beam_station_validation"] = _validate_beam(data)

    assembly.regenerate()

    _ensure_parent(REPORT_PATH)
    with codecs.open(REPORT_PATH, "w", "utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    if SAVE_AS_PATH:
        mdb.saveAs(pathName=SAVE_AS_PATH)

    print("Assembly phase %s completed." % PHASE)
    print("Report: %s" % REPORT_PATH)
    print("Suggested save path, if needed: %s" % SUGGESTED_SAVE_AS_PATH)


main()
'''


def export_main_frame_assembly(
    excel_path: str | Path,
    components_path: str | Path,
    output_json: str | Path | None,
    output_dir: str | Path,
    reports_dir: str | Path | None = None,
    project_code: str = DEFAULT_PROJECT_CODE,
    model_name: str | None = None,
) -> tuple[Path | None, list[Path], dict[str, Any]]:
    payload = build_payload(excel_path, components_path, project_code=project_code, model_name=model_name)
    json_file = write_json(payload, output_json) if output_json is not None else None
    scripts = generate_abaqus_scripts(payload, output_dir, json_file, reports_dir=reports_dir)
    return json_file, scripts, payload


def _prefix_from_latest(outputs_root: str | Path) -> str | None:
    latest = Path(outputs_root) / "latest_run_manifest.json"
    if not latest.exists():
        return None
    payload = json.loads(latest.read_text(encoding="utf-8"))
    return payload.get("project_prefix") or payload.get("project_code")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export main-frame Assembly JSON and Abaqus stage scripts.")
    parser.add_argument("--excel", default=None)
    parser.add_argument("--components", default=None)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-dir", default=None, help="Abaqus script output directory. Defaults to run_dir/abaqus_scripts.")
    parser.add_argument("--reports-dir", default=None, help="Report output directory. Defaults to run_dir/reports.")
    parser.add_argument("--run-dir", default=None, help="Existing run directory. If omitted, a timestamped run directory is created.")
    parser.add_argument("--outputs-root", default="outputs", help="Root directory for timestamped runs.")
    parser.add_argument("--project-code", "--project-prefix", dest="project_code", default=None)
    parser.add_argument("--model-name", default=None, help="Abaqus model name. Defaults to <project_prefix>.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project_code or _prefix_from_latest(args.outputs_root) or DEFAULT_PROJECT_CODE
    use_run_dir = args.run_dir is not None or args.out_json is None or args.out_dir is None
    run_paths = None
    if use_run_dir:
        run_paths = create_run_paths(project, outputs_root=args.outputs_root, run_dir=args.run_dir)
        out_json = Path(args.out_json) if args.out_json else run_paths.json / "assembly_inputs.json"
        out_dir = Path(args.out_dir) if args.out_dir else run_paths.abaqus_scripts
        reports_dir = Path(args.reports_dir) if args.reports_dir else run_paths.reports
        excel = Path(args.excel) if args.excel else run_paths.workbooks / ("%s_coordinate_formula_simple_fixed.xlsx" % project)
        components = Path(args.components) if args.components else run_paths.json / "components.json"
    else:
        out_json = Path(args.out_json)
        out_dir = Path(args.out_dir)
        reports_dir = Path(args.reports_dir) if args.reports_dir else None
        if not args.excel or not args.components:
            raise ValueError("--excel and --components are required when not using a run directory.")
        excel = Path(args.excel)
        components = Path(args.components)

    model_name = args.model_name or project
    json_file, scripts, payload = export_main_frame_assembly(
        excel,
        components,
        out_json,
        out_dir,
        reports_dir=reports_dir,
        project_code=project,
        model_name=model_name,
    )
    if run_paths:
        report_outputs = {
            "assembly_frame_report": str((reports_dir / ("%s_full_main_frame_report.json" % project)).resolve())
        }
        update_manifest(
            run_paths,
            project,
            "assembly_scripts",
            inputs={
                "coordinate_excel": str(excel.resolve()),
                "components_json": str(components.resolve()),
            },
            outputs={
                "json": {"assembly_inputs": str(json_file.resolve())},
                "abaqus_scripts": {script.stem: str(script.resolve()) for script in scripts},
                "reports": report_outputs,
            },
            warnings=list(payload.get("warnings", [])),
            errors=list(payload.get("errors", [])),
            metadata={"model_name": model_name},
        )
    print("Wrote Assembly JSON: %s" % json_file.resolve())
    for script in scripts:
        print("Wrote Abaqus script: %s" % script.resolve())
    if run_paths:
        print("Run manifest: %s" % run_paths.manifest.resolve())
    if payload.get("warnings"):
        print("Warnings: %d" % len(payload["warnings"]))
    if payload.get("errors"):
        print("Errors: %d" % len(payload["errors"]))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
