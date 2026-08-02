# -*- coding: utf-8 -*-
"""Abaqus Assembly stage script generated from coordinate Excel.

Run inside Abaqus/CAE after the five main Parts already exist in the model.
For example:
    abaqus cae noGUI=full_main_frame.py
"""
from __future__ import print_function

import codecs
import json
import math
import os

from abaqus import mdb
from abaqusConstants import *


PHASE = "full_main_frame"
ASSEMBLY_DATA = json.loads(r"""{
  "meta": {
    "project_code": "SP_SC_ANG33",
    "model_name": "SP_SC_ANG33",
    "source_excel": "F:/Codex/CADtoCAE/real_tests/SP_SC_ANG33_coordinate_formula_simple_fixed.xlsx",
    "source_components": "F:/Codex/CADtoCAE/real_tests/SP_SC_ANG33_create_parts_in_cae.py",
    "coordinate_system": "X right, Y out of elevation plane, Z up; units m-kg-N-Pa"
  },
  "units": {
    "length": "m",
    "mass": "kg",
    "force": "N",
    "stress": "Pa",
    "density": "kg/m^3"
  },
  "inputs": {
    "theta_deg": 33.0,
    "theta_rad": 0.5759586531581288,
    "GC_m": 0.4,
    "GF_m": 1.988,
    "GE_m": 3.6,
    "control_tolerance_m": 0.01,
    "angle_tolerance_deg": 0.05,
    "beam_length_m": 4.0
  },
  "input_rows": {
    "theta_deg": {
      "meaning": "斜梁倾角",
      "value": 33,
      "unit": "deg",
      "status": "已确认",
      "note": "斜梁局部轴线相对全局水平 X 轴的夹角。",
      "excel_row": 4
    },
    "Z_A_mm": {
      "meaning": "A 点高度",
      "value": 3506,
      "unit": "mm",
      "status": "需人工确认",
      "note": "A 为上立柱上顶点。A 与 F 不再假定同高。",
      "excel_row": 5
    },
    "X_F_mm": {
      "meaning": "F 点 X 坐标",
      "value": -50,
      "unit": "mm",
      "status": "需人工确认",
      "note": "F 为斜梁与上立柱/三角连接件参考交点。第一版由人工填写。",
      "excel_row": 6
    },
    "Z_F_mm": {
      "meaning": "F 点高度",
      "value": 3750,
      "unit": "mm",
      "status": "需人工确认",
      "note": "F 高度需由三角连接件/斜梁截面位置校核。",
      "excel_row": 7
    },
    "Z_BD_mm": {
      "meaning": "B/D 点共同高度",
      "value": 2100,
      "unit": "mm",
      "status": "已确认",
      "note": "B、D 为前后斜撑与抱箍交点，第一版假定同高。",
      "excel_row": 8
    },
    "R_hoop_mm": {
      "meaning": "抱箍连接点水平偏移",
      "value": 100,
      "unit": "mm",
      "status": "需人工确认",
      "note": "B=(-R,0,Z_BD)，D=(+R,0,Z_BD)。该值会显著影响 BC/DE 校核。",
      "excel_row": 9
    },
    "GC_mm": {
      "meaning": "G 到 C 的斜梁局部里程",
      "value": 400,
      "unit": "mm",
      "status": "需人工确认",
      "note": "G 为斜梁左端局部起点；C 为斜梁与前斜撑交点截面。",
      "excel_row": 10
    },
    "GF_mm": {
      "meaning": "G 到 F 的斜梁局部里程",
      "value": 1988,
      "unit": "mm",
      "status": "需人工确认",
      "note": "F 为斜梁与上立柱/三角连接件参考截面。",
      "excel_row": 11
    },
    "GE_mm": {
      "meaning": "G 到 E 的斜梁局部里程",
      "value": 3600,
      "unit": "mm",
      "status": "需人工确认",
      "note": "E 为斜梁与后斜撑交点截面；需按图纸斜梁尺寸链复核。",
      "excel_row": 12
    },
    "L_BC_draw_mm": {
      "meaning": "图纸标注 BC 长度",
      "value": 1500,
      "unit": "mm",
      "status": "已确认",
      "note": "用于 BC 段 ±1mm 校核。",
      "excel_row": 13
    },
    "L_DE_draw_mm": {
      "meaning": "图纸标注 DE 长度",
      "value": 2762,
      "unit": "mm",
      "status": "已确认",
      "note": "用于 DE 段 ±1mm 校核。",
      "excel_row": 14
    },
    "origin_px_x": {
      "meaning": "图纸标注原点像素 X",
      "value": 523,
      "unit": "px",
      "status": "已确认",
      "note": "仅影响图纸标注记录中的像素位置，不影响 Abaqus 坐标。",
      "excel_row": 15
    },
    "origin_px_y": {
      "meaning": "图纸标注原点像素 Y",
      "value": 770,
      "unit": "px",
      "status": "已确认",
      "note": "仅影响图纸标注记录中的像素位置，不影响 Abaqus 坐标。",
      "excel_row": 16
    },
    "scale_px_per_m": {
      "meaning": "图纸标注比例",
      "value": 170,
      "unit": "px/m",
      "status": "已确认",
      "note": "仅影响图纸标注记录中的像素位置，不影响 Abaqus 坐标。",
      "excel_row": 17
    },
    "control_tolerance_m": {
      "meaning": "BC/DE 长度允许误差",
      "value": 0.01,
      "unit": "m",
      "status": "已确认",
      "note": "默认 ±1mm。",
      "excel_row": 18
    },
    "angle_tolerance_deg": {
      "meaning": "CE 角度允许误差",
      "value": 0.05,
      "unit": "deg",
      "status": "已确认",
      "note": "默认 0.05°。",
      "excel_row": 19
    }
  },
  "points": {
    "O": {
      "coords": [
        0.0,
        0.0,
        0.0
      ],
      "x_m": 0.0,
      "y_m": 0.0,
      "z_m": 0.0,
      "status": "已确认",
      "note": "Origin"
    },
    "A": {
      "coords": [
        0.0,
        0.0,
        3.506
      ],
      "x_m": 0.0,
      "y_m": 0.0,
      "z_m": 3.506,
      "status": "需人工确认",
      "note": "Upper column top"
    },
    "F": {
      "coords": [
        -0.05,
        0.0,
        3.75
      ],
      "x_m": -0.05,
      "y_m": 0.0,
      "z_m": 3.75,
      "status": "需人工确认",
      "note": "Beam-column reference section"
    },
    "B": {
      "coords": [
        -0.1,
        0.0,
        2.1
      ],
      "x_m": -0.1,
      "y_m": 0.0,
      "z_m": 2.1,
      "status": "需人工确认",
      "note": "Front brace hoop point"
    },
    "D": {
      "coords": [
        0.1,
        0.0,
        2.1
      ],
      "x_m": 0.1,
      "y_m": 0.0,
      "z_m": 2.1,
      "status": "需人工确认",
      "note": "Rear brace hoop point"
    },
    "C": {
      "coords": [
        -1.3818088618973334,
        0.0,
        2.8851132123961367
      ],
      "x_m": -1.3818088618973334,
      "y_m": 0.0,
      "z_m": 2.8851132123961367,
      "status": "需人工确认",
      "note": "Beam-front brace section"
    },
    "E": {
      "coords": [
        1.3019369555280236,
        0.0,
        4.627958124444223
      ],
      "x_m": 1.3019369555280236,
      "y_m": 0.0,
      "z_m": 4.627958124444223,
      "status": "需人工确认",
      "note": "Beam-rear brace section"
    },
    "G_global": {
      "coords": [
        -1.7172770890755031,
        0.0,
        2.667257598390126
      ],
      "x_m": -1.7172770890755031,
      "y_m": 0.0,
      "z_m": 2.667257598390126,
      "status": "需人工确认",
      "note": "Derived global position of beam local origin G"
    }
  },
  "beam_anchor": {
    "part_name": "P_SP_SC_ANG33_INCLINED_BEAM",
    "local_point_name": "F",
    "local_point": [
      0.0,
      0.04,
      1.988
    ],
    "axis_local_point": [
      0.0,
      0.0,
      1.988
    ],
    "reference_local_origin": [
      0.0,
      0.04,
      0.0
    ],
    "global_point_name": "F",
    "global_point": [
      -0.05,
      0.0,
      3.75
    ],
    "stations": {
      "C": 0.4,
      "F": 1.988,
      "E": 3.6
    },
    "direction_u": [
      0.838670567945424,
      0.0,
      0.5446390350150271
    ],
    "rotate_y_deg": 57.0,
    "roll_about_axis_deg": 90.0,
    "translation": [
      -1.7172770890755031,
      -0.04,
      2.667257598390126
    ],
    "section_reference": {
      "x_m": 0.0,
      "y_m": 0.04,
      "rule": "C_CHANNEL_WEB_MIDPOINT",
      "open_side_local": "+X",
      "open_side_target_global": "-Y"
    },
    "section_sets": {
      "C": "SET_BEAM_SEC_C",
      "F": "SET_BEAM_SEC_F",
      "E": "SET_BEAM_SEC_E"
    }
  },
  "members": [
    {
      "name": "COLUMN",
      "phase": "step01_columns",
      "part_name": "P_SP_SC_ANG33_COLUMN",
      "component_code": "COLUMN",
      "instance_name": "I_SP_SC_ANG33_COLUMN",
      "local_anchor": [
        0.0,
        0.0,
        1.8
      ],
      "global_anchor_name": "A",
      "global_anchor": [
        0.0,
        0.0,
        3.506
      ],
      "rotate_y_deg": 0.0,
      "roll_about_axis_deg": 0.0,
      "translation": [
        0.0,
        0.0,
        1.7059999999999997
      ],
      "part_length_m": 1.8,
      "section_kind": "PIPE",
      "section_params_m": {
        "od_m": 0.159,
        "t_m": 0.003
      },
      "section_reference": {
        "x_m": 0.0,
        "y_m": 0.0,
        "rule": "SECTION_ORIGIN",
        "open_side_local": "",
        "open_side_target_global": ""
      },
      "open_side_global": [
        0.0,
        0.0,
        0.0
      ],
      "model_policy": "SHELL"
    },
    {
      "name": "INCLINED_BEAM",
      "phase": "step02_beam",
      "part_name": "P_SP_SC_ANG33_INCLINED_BEAM",
      "component_code": "INCLINED_BEAM",
      "instance_name": "I_SP_SC_ANG33_INCLINED_BEAM",
      "local_anchor": [
        0.0,
        0.04,
        1.988
      ],
      "global_anchor_name": "F",
      "global_anchor": [
        -0.05,
        0.0,
        3.75
      ],
      "rotate_y_deg": 57.0,
      "roll_about_axis_deg": 90.0,
      "translation": [
        -1.7172770890755031,
        -0.04,
        2.667257598390126
      ],
      "part_length_m": 4.0,
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.04,
        "h_m": 0.08,
        "lip_m": 0.01,
        "t_m": 0.002
      },
      "section_reference": {
        "x_m": 0.0,
        "y_m": 0.04,
        "rule": "C_CHANNEL_WEB_MIDPOINT",
        "open_side_local": "+X",
        "open_side_target_global": "-Y"
      },
      "open_side_global": [
        0.0,
        1.0,
        0.0
      ],
      "model_policy": "SHELL",
      "target_point_name": "E",
      "target_point": [
        1.3019369555280236,
        0.0,
        4.627958124444223
      ]
    },
    {
      "name": "BRACE_FRONT",
      "phase": "step03_main_frame",
      "part_name": "P_SP_SC_ANG33_BRACE_FRONT",
      "component_code": "BRACE_FRONT",
      "instance_name": "I_SP_SC_ANG33_BRACE_FRONT",
      "local_anchor": [
        0.0,
        0.0275,
        0.0
      ],
      "global_anchor_name": "B",
      "global_anchor": [
        -0.1,
        0.0,
        2.1
      ],
      "rotate_y_deg": -58.51235886507747,
      "roll_about_axis_deg": -90.0,
      "translation": [
        -0.1,
        -0.0275,
        2.1
      ],
      "part_length_m": 1.5,
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.04,
        "h_m": 0.055,
        "lip_m": 0.01,
        "t_m": 0.002
      },
      "section_reference": {
        "x_m": 0.0,
        "y_m": 0.0275,
        "rule": "C_CHANNEL_WEB_MIDPOINT",
        "open_side_local": "+X",
        "open_side_target_global": "-Y"
      },
      "open_side_global": [
        0.0,
        -1.0,
        0.0
      ],
      "model_policy": "SHELL",
      "target_point_name": "C",
      "target_point": [
        -1.3818088618973334,
        0.0,
        2.8851132123961367
      ]
    },
    {
      "name": "BRACE_REAR",
      "phase": "step03_main_frame",
      "part_name": "P_SP_SC_ANG33_BRACE_REAR",
      "component_code": "BRACE_REAR",
      "instance_name": "I_SP_SC_ANG33_BRACE_REAR",
      "local_anchor": [
        0.0,
        0.03,
        0.0
      ],
      "global_anchor_name": "D",
      "global_anchor": [
        0.1,
        0.0,
        2.1
      ],
      "rotate_y_deg": 25.429107273138463,
      "roll_about_axis_deg": -90.0,
      "translation": [
        0.1,
        -0.03,
        2.1
      ],
      "part_length_m": 2.762,
      "section_kind": "C_CHANNEL",
      "section_params_m": {
        "b_m": 0.045,
        "h_m": 0.06,
        "lip_m": 0.015,
        "t_m": 0.002
      },
      "section_reference": {
        "x_m": 0.0,
        "y_m": 0.03,
        "rule": "C_CHANNEL_WEB_MIDPOINT",
        "open_side_local": "+X",
        "open_side_target_global": "-Y"
      },
      "open_side_global": [
        0.0,
        -1.0,
        0.0
      ],
      "model_policy": "SHELL",
      "target_point_name": "E",
      "target_point": [
        1.3019369555280236,
        0.0,
        4.627958124444223
      ]
    }
  ],
  "required_part_names": [
    "P_SP_SC_ANG33_COLUMN",
    "P_SP_SC_ANG33_INCLINED_BEAM",
    "P_SP_SC_ANG33_BRACE_FRONT",
    "P_SP_SC_ANG33_BRACE_REAR"
  ],
  "checks": {
    "GC_GF_GE_ORDER": {
      "calc_value": "GC=0.400000, GF=1.988000, GE=3.600000",
      "reference_value": "0 < GC < GF < GE < beam_length",
      "error": null,
      "tolerance": null,
      "passed": "通过",
      "status": "需人工确认"
    },
    "CF_LOCAL": {
      "calc_value": 1.588,
      "reference_value": "GF-GC",
      "error": null,
      "tolerance": null,
      "passed": "通过",
      "status": "需人工确认"
    },
    "FE_LOCAL": {
      "calc_value": 1.612,
      "reference_value": "GE-GF",
      "error": null,
      "tolerance": null,
      "passed": "通过",
      "status": "需人工确认"
    },
    "CE_ANGLE": {
      "calc_value": 33.0,
      "reference_value": 33.0,
      "error": 0.0,
      "tolerance": 0.05,
      "passed": "通过",
      "status": "需人工确认"
    },
    "BC": {
      "calc_value": 1.5031422802640866,
      "reference_value": 1.5,
      "error": 0.0031422802640865832,
      "tolerance": 0.01,
      "passed": "通过",
      "status": "需人工确认"
    },
    "DE": {
      "calc_value": 2.799147142257357,
      "reference_value": 2.762,
      "error": 0.037147142257357046,
      "tolerance": 0.01,
      "passed": "不通过",
      "status": "需人工确认"
    }
  },
  "member_checks": {
    "COLUMN_PLACEMENT": {
      "anchor": "A",
      "part_length_m": 1.8,
      "derived_bottom": [
        0.0,
        0.0,
        1.7059999999999997
      ],
      "passed": "通过",
      "note": "Single COLUMN component is controlled by its top point A."
    },
    "INCLINED_BEAM_CE": {
      "start": "C",
      "end": "E",
      "axis_length_m": 3.2,
      "part_length_m": 4.0,
      "error_m": null,
      "tolerance_m": 0.01,
      "passed": "通过"
    },
    "BRACE_FRONT_BC": {
      "start": "B",
      "end": "C",
      "axis_length_m": 1.5031422802640866,
      "part_length_m": 1.5,
      "error_m": 0.0031422802640865832,
      "tolerance_m": 0.01,
      "passed": "通过",
      "drawing_length_check": {
        "calc_value": 1.5031422802640866,
        "reference_value": 1.5,
        "error": 0.0031422802640865832,
        "tolerance": 0.01,
        "passed": "通过",
        "status": "需人工确认"
      },
      "note": "Abaqus placement uses B-C axis; material length can include connection offsets."
    },
    "BRACE_REAR_DE": {
      "start": "D",
      "end": "E",
      "axis_length_m": 2.799147142257357,
      "part_length_m": 2.762,
      "error_m": 0.037147142257357046,
      "tolerance_m": 0.01,
      "passed": "不通过",
      "drawing_length_check": {
        "calc_value": 2.799147142257357,
        "reference_value": 2.762,
        "error": 0.037147142257357046,
        "tolerance": 0.01,
        "passed": "不通过",
        "status": "需人工确认"
      },
      "note": "Abaqus placement uses D-E axis; material length can include connection offsets."
    }
  },
  "warnings": [
    "Input Z_A_mm status is 需人工确认.",
    "Input X_F_mm status is 需人工确认.",
    "Input Z_F_mm status is 需人工确认.",
    "Input R_hoop_mm status is 需人工确认.",
    "Input GC_mm status is 需人工确认.",
    "Input GF_mm status is 需人工确认.",
    "Input GE_mm status is 需人工确认.",
    "control_tolerance_m is 0.010000 m; this is wider than +/-1 mm."
  ],
  "errors": []
}""")


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


REPORT_PATH = _resolve_report_path("SP_SC_ANG33_full_main_frame_report.json")
SAVE_AS_PATH = r""
SUGGESTED_SAVE_AS_PATH = _resolve_report_path("SP_SC_ANG33_full_main_frame.cae")
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
    return _unit(_rotate_y((0.0, 0.0, 1.0), float(member.get("rotate_y_deg") or 0.0)))


def _transform_member(local_point, member):
    rotated = _rotate_y(tuple(float(v) for v in local_point), float(member.get("rotate_y_deg") or 0.0))
    translated = _add3(rotated, tuple(float(v) for v in member.get("translation", (0.0, 0.0, 0.0))))
    roll_about_axis_deg = float(member.get("roll_about_axis_deg") or 0.0)
    if abs(roll_about_axis_deg) <= 1.0e-12:
        return translated
    axis_point = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
    return _rotate_about_axis(translated, axis_point, _member_axis_direction(member), roll_about_axis_deg)


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
    part = _part(model, member["part_name"])
    assembly.Instance(name=inst_name, part=part, dependent=ON)
    rotate_y_deg = float(member.get("rotate_y_deg") or 0.0)
    if abs(rotate_y_deg) > 1.0e-12:
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
    if abs(roll_about_axis_deg) > 1.0e-12:
        axis_point = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
        assembly.rotate(
            instanceList=(inst_name,),
            axisPoint=axis_point,
            axisDirection=_member_axis_direction(member),
            angle=roll_about_axis_deg,
        )
    return {
        "instance_name": member["instance_name"],
        "part_name": member["part_name"],
        "rotate_y_deg": rotate_y_deg,
        "roll_about_axis_deg": roll_about_axis_deg,
        "translation": list(translation),
        "section_reference": member.get("section_reference"),
        "open_side_global": member.get("open_side_global"),
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
    if PHASE == "step01_columns":
        names = set(["COLUMN_DOWN", "COLUMN_UP", "COLUMN"])
    elif PHASE == "step02_beam":
        names = set(["INCLINED_BEAM"])
    elif PHASE == "step03_main_frame":
        names = set(["COLUMN_DOWN", "COLUMN_UP", "COLUMN", "INCLINED_BEAM", "BRACE_FRONT", "BRACE_REAR"])
    else:
        names = set(["COLUMN_DOWN", "COLUMN_UP", "COLUMN", "INCLINED_BEAM", "BRACE_FRONT", "BRACE_REAR"])
    return [member for member in data.get("members", []) if member.get("name") in names]


def _validate_member(member, data):
    errors = []
    anchor = _transform_member(member.get("local_anchor", (0.0, 0.0, 0.0)), member)
    target_anchor = tuple(float(v) for v in member.get("global_anchor", (0.0, 0.0, 0.0)))
    anchor_error = _distance(anchor, target_anchor)
    if anchor_error > 1.0e-6:
        errors.append("%s anchor error %.9g m" % (member["name"], anchor_error))

    if member.get("target_point_name"):
        part_length = float(member.get("part_length_m") or 0.0)
        local_anchor = member.get("local_anchor", (0.0, 0.0, 0.0))
        local_end = (float(local_anchor[0]), float(local_anchor[1]), part_length)
        transformed_end = _transform_member(local_end, member)
        target = tuple(float(v) for v in member.get("target_point", (0.0, 0.0, 0.0)))
        # Braces may include connection offsets, so report this value rather than failing hard.
        end_error = _distance(transformed_end, target)
        return {"anchor_error_m": anchor_error, "end_error_m": end_error, "errors": errors}
    return {"anchor_error_m": anchor_error, "errors": errors}


def _validate_beam(data):
    beam_member = None
    for member in data.get("members", []):
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
    model = _model(data)
    assembly = model.rootAssembly
    report = {"phase": PHASE, "warnings": list(data.get("warnings", [])), "instances": [], "partition": None, "validation": {}}
    phase_members = _members_for_phase(data)

    missing = []
    for name in sorted(set(member["part_name"] for member in phase_members)):
        if _ascii(name) not in model.parts:
            missing.append(name)
    if missing:
        project = data.get("meta", {}).get("project_code") or "project"
        raise RuntimeError("Missing required Parts for %s: %s. Run %s_create_parts_in_cae.py first." % (PHASE, ", ".join(missing), project))

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
