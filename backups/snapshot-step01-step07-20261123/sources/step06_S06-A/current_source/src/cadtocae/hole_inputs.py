"""Step06 engineering input: one row per SUPPORT driving hole, never XYZ pairs."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
import re

from openpyxl import load_workbook
from .hole_profiles import hole_dimensions

SHEET_NAME = "Bolt Hole Location Table"
FIELDS = (
    "project_id", "connection_group", "component_role", "hole_id",
    "connection_target", "leg", "distance_from_angle_corner_mm",
    "distance_from_end_mm", "end_reference", "hole_diameter_mm", "enabled", "note",
)
HEADERS = (
    "Project ID", "Connection Group", "Component", "Hole ID", "Connection Target",
    "Angle Leg", "Distance from Angle Corner (mm)", "Distance from End (mm)",
    "End Reference", "Hole Diameter (mm)", "Enabled", "Remarks",
)
TARGETS = {"PS_TO_PURLIN": "PURLIN_LOCAL", "PS_TO_BEAM": "INCLINED_BEAM"}
LEGS = {"PS_TO_PURLIN": "LONG_LEG", "PS_TO_BEAM": "SHORT_LEG"}
SHAPE_FIELDS = ("hole_type", "slot_total_length_mm", "slot_major_axis")
CHINESE_HEADERS = (
    "项目编号", "连接组", "构件", "孔位编号", "连接目标", "所在角钢肢",
    "距角钢直角根部 (mm)", "距端部 (mm)", "端部基准", "孔型",
    "孔宽/直径 (mm)", "槽孔总长 (mm)", "槽孔长轴方向", "启用", "备注",
)
FULL_FIELDS = FIELDS[:9] + ("hole_type", "hole_diameter_mm", "slot_total_length_mm", "slot_major_axis") + FIELDS[10:]
FULL_HEADERS = HEADERS[:9] + ("Hole Type", "Hole Width / Diameter (mm)", "Slot Total Length (mm)", "Slot Major Axis") + HEADERS[10:]
ALIASES = dict(zip(CHINESE_HEADERS, FULL_FIELDS))
ALIASES.update(zip(FULL_HEADERS, FULL_FIELDS))
ALIASES.update(zip(HEADERS, FIELDS))
ALIASES["孔径 (mm)"] = "hole_diameter_mm"
VALUES = {"檩托": "PURLIN_SUPPORT", "局部檩条": "PURLIN_LOCAL", "檩条（局部）": "PURLIN_LOCAL",
          "斜梁": "INCLINED_BEAM", "长肢": "LONG_LEG", "短肢": "SHORT_LEG",
          "起始端": "START", "末端": "END", "圆孔": "ROUND", "长圆孔": "SLOT",
          "沿长肢方向": "LEG_DIRECTION", "沿短肢方向": "LEG_DIRECTION", "沿肢方向": "LEG_DIRECTION",
          "沿檩托长度方向": "PART_LENGTH", "是": "TRUE", "否": "FALSE"}


def positive_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a numeric value")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(label + " must be finite and > 0")
    return float(value)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " requires text")
    return value.strip()


def _enabled(value):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().upper() in ("TRUE", "FALSE", "ON", "OFF"):
        return value.strip().upper() in ("TRUE", "ON")
    raise ValueError("enabled must be TRUE/FALSE or ON/OFF")


@dataclass(frozen=True)
class HoleLocationRow:
    project_id: str
    connection_group: str
    component_role: str
    hole_id: str
    connection_target: str
    leg: str
    distance_from_angle_corner_mm: float
    distance_from_end_mm: float
    end_reference: str
    hole_diameter_mm: float
    enabled: bool
    note: str
    source_row: int
    hole_type: str = "ROUND"
    slot_total_length_mm: float | None = None
    slot_major_axis: str | None = None
    source_file: str = ""
    source_sheet: str = ""


def normalize_hole_rows(rows, first_row=2, allow_multiple_projects=False):
    """Normalize the one engineering schema; disabled rows still require valid data."""
    result, keys, projects = [], set(), set()
    for row_number, raw in enumerate(rows, first_row):
        try:
            if set(raw) not in (set(FIELDS), set(FULL_FIELDS)):
                raise ValueError("Expected exactly Bolt Hole Location Table fields; XYZ/side rows are unsupported")
            raw = {k: VALUES.get(v.strip(), v.strip()) if isinstance(v, str) and k not in ("project_id", "note") else v
                   for k, v in raw.items()}
            data = {key: _text(raw[key], key) for key in FIELDS[:6]}
            data["end_reference"] = _text(raw["end_reference"], "end_reference")
            if data["component_role"] != "PURLIN_SUPPORT":
                raise ValueError("component_role must be PURLIN_SUPPORT")
            if data["hole_id"] not in TARGETS:
                raise ValueError("Invalid hole_id")
            if data["connection_target"] != TARGETS[data["hole_id"]]:
                raise ValueError("connection_target does not match hole_id")
            if data["leg"] not in ("LONG_LEG", "SHORT_LEG"):
                raise ValueError("Invalid leg")
            if data["leg"] != LEGS[data["hole_id"]]:
                raise ValueError("Hole ID requires " + LEGS[data["hole_id"]])
            if data["end_reference"] not in ("START", "END"):
                raise ValueError("Invalid end_reference")
            if data["connection_group"] not in ("P01", "P02", "P03", "P04"):
                raise ValueError("connection_group must be P01/P02/P03/P04")
            for key in ("distance_from_angle_corner_mm", "distance_from_end_mm", "hole_diameter_mm"):
                data[key] = positive_number(raw[key], key)
            data["enabled"] = _enabled(raw["enabled"])
            data["hole_type"] = raw.get("hole_type", "ROUND")
            if data["hole_type"] not in ("ROUND", "SLOT"):
                raise ValueError("Unsupported hole_type")
            if data["hole_type"] == "SLOT":
                data["slot_total_length_mm"] = positive_number(raw.get("slot_total_length_mm"), "slot total length")
                try:
                    width,length = hole_dimensions(dict(hole_type='SLOT',width_m=data['hole_diameter_mm']/1000.,
                                                         total_length_m=data['slot_total_length_mm']/1000.))
                except ValueError as exc:
                    raise ValueError('Slot total length must be >= slot width: '+str(exc))
                data['slot_total_length_mm'] = length*1000.
                data["slot_major_axis"] = raw.get("slot_major_axis")
                if data["slot_major_axis"] not in ("LEG_DIRECTION", "PART_LENGTH"):
                    raise ValueError("Slot major axis must be LEG_DIRECTION or PART_LENGTH")
            else:
                supplied_length = raw.get('slot_total_length_mm')
                if supplied_length not in (None,''):
                    hole_dimensions(dict(hole_type='ROUND',width_m=data['hole_diameter_mm']/1000.,
                                         total_length_m=positive_number(supplied_length,'ROUND total length')/1000.))
                if raw.get('slot_major_axis') not in (None,'','LEG_DIRECTION','PART_LENGTH'):
                    raise ValueError('Invalid ROUND direction')
                data['slot_total_length_mm'] = None
                data['slot_major_axis'] = None
            data["note"] = "" if raw["note"] is None else _text(raw["note"], "note") if raw["note"] != "" else ""
            key = (data["project_id"], data["connection_group"], data["hole_id"])
            if key in keys:
                raise ValueError("Duplicate hole_id in connection_group")
            keys.add(key)
            projects.add(data["project_id"])
            result.append(HoleLocationRow(**data, source_row=row_number))
        except (ValueError, TypeError) as exc:
            raise ValueError("Bolt Hole Location Table row %d: %s" % (row_number, exc)) from exc
    if not result or (len(projects) != 1 and not allow_multiple_projects):
        raise ValueError("Exactly one project and at least one hole row required")
    return result


def read_hole_table(path: str | Path):
    """Schema discovery, independent of filename/sheet title. Return raw rows with provenance.

    Notes sheets are allowed. A partial/duplicate recognized header is an error,
    not a reason to silently ignore a malformed hole table.
    """
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Expected Bolt Hole Location Table .xlsx")
    with path.open("rb") as stream:
        workbook = load_workbook(stream, read_only=True, data_only=False)
        try:
            found = []
            for sheet in workbook:
                iterator = iter(sheet.values)
                header = None
                for number, row in enumerate(iterator, 1):
                    if number > 20:
                        break
                    names = [ALIASES.get(v.strip()) if isinstance(v, str) else None for v in row]
                    if {"hole_id", "connection_group"}.issubset(names):
                        nonempty = [i for i, v in enumerate(row) if v is not None]
                        mapped = [names[i] for i in nonempty]
                        if len(set(mapped)) != len(mapped) or set(mapped) not in (set(FIELDS), set(FULL_FIELDS)):
                            raise ValueError("Invalid/missing/duplicate hole table headers: " + sheet.title)
                        header = [(i, names[i]) for i in nonempty]
                        header_number = number
                        break
                if header is None:
                    continue
                for number, row in enumerate(iterator, header_number + 1):
                    if not any(v is not None for v in row):
                        continue
                    record = {key: row[i] if i < len(row) else None for i, key in header}
                    if any(isinstance(v, str) and v.startswith("=") for v in record.values()):
                        raise ValueError("Formulas are unsupported at %s:%d" % (sheet.title, number))
                    found.append(dict(values=record, source_file=str(path.resolve()), source_sheet=sheet.title, source_row=number))
                if not found:
                    raise ValueError("Recognized hole table is empty: " + sheet.title)
            return found
        finally:
            workbook.close()


def normalize_records(records, project_id=None):
    result = []
    for record in records:
        raw = dict(record["values"])
        if project_id is not None and raw.get("project_id") in (None, ""):
            raw["project_id"] = project_id
        try:
            row = normalize_hole_rows([raw], record["source_row"])[0]
        except ValueError as exc:
            raise ValueError("%s / %s: %s" % (record["source_file"], record["source_sheet"], exc)) from exc
        result.append(replace(row, source_file=record["source_file"], source_sheet=record["source_sheet"]))
    keys = [(r.project_id, r.connection_group, r.hole_id) for r in result]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate hole_id in project/connection_group (possibly multiple hole tables)")
    return result


def read_hole_inputs(path: str | Path):
    records = read_hole_table(path)
    if not records:
        raise ValueError("No recognized hole table headers")
    return normalize_records(records)
