from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STANDARDS_PATH = PROJECT_ROOT / "config" / "standards.json"
MM_TO_M = 0.001
HOOP_COMPONENT_CODE_RE = re.compile(r"^(?:HOOP(?:_\d+)?|HOOP_ASSEMBLY(?:_\d+)?|BRACE_HOOP)$", re.IGNORECASE)
CLAMP_COMPONENT_CODES = {"MID_CLAMP", "EDGE_CLAMP"}
FORCED_SOLID_COMPONENT_CODES = {"PURLIN_SUPPORT", "HOOP", "PURLIN_SPLICE", "MID_CLAMP", "EDGE_CLAMP"}


@dataclass(frozen=True)
class ParsedSpec:
    section_type: str
    section_params: dict[str, float | str]
    thickness_mm: float | None
    section_code: str
    status: str
    message: str = ""

    def params_text(self) -> str:
        if not self.section_params:
            return ""
        return "; ".join(f"{key}={value}" for key, value in self.section_params.items())


def load_standards(path: str | Path | None = None) -> dict[str, Any]:
    standards_path = Path(path) if path else DEFAULT_STANDARDS_PATH
    if not standards_path.exists() and path is None:
        candidates = []
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            candidates.append(Path(frozen_root) / "config" / "standards.json")
        if getattr(sys, "executable", None):
            candidates.append(Path(sys.executable).resolve().parent / "config" / "standards.json")
        candidates.append(Path.cwd() / "config" / "standards.json")
        for candidate in candidates:
            if candidate.exists():
                standards_path = candidate
                break
    with standards_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ensure_standards(standards: dict[str, Any] | str | Path | None = None) -> dict[str, Any]:
    if standards is None or isinstance(standards, (str, Path)):
        return load_standards(standards)
    return standards


def normalize_spec(spec: Any) -> str:
    if spec is None:
        return ""
    text = str(spec).strip()
    if not text:
        return ""
    replacements = {
        "φ": "Φ",
        "Ø": "Φ",
        "∅": "Φ",
        "×": "X",
        "x": "X",
        "＊": "X",
        "*": "X",
        "（": "(",
        "）": ")",
        " ": "",
        "\u3000": ""
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.upper()


def _number(value: str) -> float:
    value = value.strip()
    number = float(value)
    return int(number) if number.is_integer() else number


def _code_number(value: float | int | str) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", "P")


def _section_code(prefix: str, *values: float | int | str) -> str:
    return prefix + "".join("X" + _code_number(value) for value in values)


def is_hoop_component_code(component_code: Any) -> bool:
    return bool(HOOP_COMPONENT_CODE_RE.fullmatch(str(component_code or "").strip()))


def parse_hoop_spec(spec: Any) -> ParsedSpec:
    normalized = normalize_spec(spec)
    if not normalized:
        return ParsedSpec("未识别", {}, None, "UNSPEC", "需人工确认", "规格为空")

    match = re.fullmatch(
        r"HOOP\(D=(?P<diameter>\d+(?:\.\d+)?),W=(?P<width>\d+(?:\.\d+)?),"
        r"T=(?P<t>\d+(?:\.\d+)?),L=(?P<left>\d+(?:\.\d+)?),R=(?P<right>\d+(?:\.\d+)?)"
        r"(?:,RF=(?P<fillet>\d+(?:\.\d+)?))?\)",
        normalized,
    )
    if match:
        diameter, width, t, left, right = (
            _number(match.group(key)) for key in ("diameter", "width", "t", "left", "right")
        )
        fillet = _number(match.group("fillet")) if match.group("fillet") is not None else 0
        return ParsedSpec(
            "抱箍带",
            {
                "内径_mm": diameter,
                "带宽_mm": width,
                "厚度_mm": t,
                "左直段_mm": left,
                "右直段_mm": right,
                "内半径_mm": diameter / 2.0,
                "外半径_mm": diameter / 2.0 + t,
                "过渡圆角_mm": fillet,
            },
            t,
            "HOOP_D%s_W%s_T%s_L%s_R%s_RF%s"
            % tuple(_code_number(value) for value in (diameter, width, t, left, right, fillet)),
            "已解析",
        )

    return ParsedSpec("未识别", {"原始规格": normalized}, None, "UNKNOWN", "需人工确认", "抱箍规格格式未纳入规则")


def parse_simple_c_spec(spec: Any) -> ParsedSpec:
    normalized = normalize_spec(spec)
    match = re.fullmatch(r"C(?P<h>\d+(?:\.\d+)?)X(?P<b>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)", normalized)
    if not match:
        return ParsedSpec("未识别", {"原始规格": normalized}, None, "UNKNOWN", "需人工确认", "无回折C型钢规格格式未纳入规则")
    h, b, t = (_number(match.group(key)) for key in ("h", "b", "t"))
    return ParsedSpec(
        "无回折C型钢",
        {"高度_mm": h, "翼缘宽_mm": b, "厚度_mm": t},
        t,
        _section_code("CS", h, b, t),
        "已解析",
    )


def parse_clamp_spec(spec: Any, component_code: str) -> ParsedSpec:
    normalized = normalize_spec(spec)
    template = "MIDCLAMP_V1" if component_code == "MID_CLAMP" else "EDGECLAMP_V1"
    match = re.fullmatch(
        template + r"\(L=(?P<length>\d+(?:\.\d+)?),SLOT=(?P<slot_w>\d+(?:\.\d+)?)X"
        r"(?P<slot_l>\d+(?:\.\d+)?),E=(?P<end>\d+(?:\.\d+)?),P=(?P<pitch>\d+(?:\.\d+)?)\)",
        normalized,
    )
    if not match:
        return ParsedSpec("未识别", {"原始规格": normalized}, None, "UNKNOWN", "需人工确认", "%s规格格式未纳入规则" % template)
    length, slot_w, slot_l, end, pitch = (
        _number(match.group(key)) for key in ("length", "slot_w", "slot_l", "end", "pitch")
    )
    section_type = "中压块V1" if component_code == "MID_CLAMP" else "边压块V1"
    return ParsedSpec(
        section_type,
        {
            "长度_mm": length,
            "长圆孔宽_mm": slot_w,
            "长圆孔长_mm": slot_l,
            "端距_mm": end,
            "孔距_mm": pitch,
            "孔1中心_mm": end,
            "孔2中心_mm": end + pitch,
        },
        None,
        "%s_L%s_SLOT%sX%s_E%s_P%s" % tuple(
            [template] + [_code_number(value) for value in (length, slot_w, slot_l, end, pitch)]
        ),
        "已解析",
        "tooth geometry requires drawing detail",
    )


def parse_rectangular_washer_spec(spec: Any) -> ParsedSpec:
    normalized = normalize_spec(spec)
    match = re.fullmatch(
        r"RECT_WASHER\(L=(?P<length>\d+(?:\.\d+)?),W=(?P<width>\d+(?:\.\d+)?),"
        r"T=(?P<t>\d+(?:\.\d+)?),HOLE=(?P<hole>\d+(?:\.\d+)?)\)",
        normalized,
    )
    if not match:
        return ParsedSpec("未识别", {"原始规格": normalized}, None, "UNKNOWN", "需人工确认", "矩形垫片尺寸尚未完整定义")
    length, width, t, hole = (_number(match.group(key)) for key in ("length", "width", "t", "hole"))
    return ParsedSpec(
        "矩形垫片",
        {"长度_mm": length, "宽度_mm": width, "厚度_mm": t, "孔径_mm": hole},
        t,
        "RECT_WASHER_L%s_W%s_T%s_HOLE%s" % tuple(_code_number(value) for value in (length, width, t, hole)),
        "已解析",
        "geometry remains MANUAL_TEMPLATE",
    )
def parse_spec(spec: Any) -> ParsedSpec:
    normalized = normalize_spec(spec)
    if not normalized:
        return ParsedSpec("未识别", {}, None, "UNSPEC", "需人工确认", "规格为空")

    match = re.fullmatch(
        r"C(?P<h>\d+(?:\.\d+)?)X(?P<b>\d+(?:\.\d+)?)X(?P<lip>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)",
        normalized,
    )
    if match:
        h, b, lip, t = (_number(match.group(key)) for key in ("h", "b", "lip", "t"))
        return ParsedSpec(
            "C型钢",
            {"高度_mm": h, "翼缘宽_mm": b, "卷边_mm": lip, "厚度_mm": t},
            t,
            _section_code("C", h, b, lip, t),
            "已解析",
        )

    match = re.fullmatch(
        r"L(?P<a>\d+(?:\.\d+)?)X(?P<b>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)",
        normalized,
    )
    if match:
        a, b, t = (_number(match.group(key)) for key in ("a", "b", "t"))
        return ParsedSpec(
            "角钢",
            {"边长A_mm": a, "边长B_mm": b, "厚度_mm": t},
            t,
            _section_code("L", a, b, t),
            "已解析",
        )

    match = re.fullmatch(r"Φ(?P<od>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)", normalized)
    if match:
        od, t = (_number(match.group(key)) for key in ("od", "t"))
        return ParsedSpec(
            "圆管",
            {"外径_mm": od, "厚度_mm": t},
            t,
            _section_code("PIPE", od, t),
            "已解析",
        )

    match = re.fullmatch(
        r"D(?P<od>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)\(Φ(?P<rod>\d+(?:\.\d+)?)\)",
        normalized,
    )
    if match:
        od, t, rod = (_number(match.group(key)) for key in ("od", "t", "rod"))
        return ParsedSpec(
            "套管撑杆",
            {"外径_mm": od, "厚度_mm": t, "内拉杆直径_mm": rod},
            t,
            f"D{_code_number(od)}X{_code_number(t)}_ROD{_code_number(rod)}",
            "已解析",
        )

    match = re.fullmatch(r"Φ(?P<diameter>\d+(?:\.\d+)?)", normalized)
    if match:
        diameter = _number(match.group("diameter"))
        return ParsedSpec(
            "圆钢/圆杆",
            {"直径_mm": diameter},
            None,
            _section_code("ROD", diameter),
            "已解析",
        )

    match = re.fullmatch(r"M(?P<diameter>\d+(?:\.\d+)?)", normalized)
    if match:
        diameter = _number(match.group("diameter"))
        return ParsedSpec(
            "螺纹件",
            {"公称直径_mm": diameter},
            None,
            f"M{_code_number(diameter)}",
            "已解析",
        )

    return ParsedSpec("未识别", {"原始规格": normalized}, None, "UNKNOWN", "需人工确认", "规格格式未纳入规则")


def support_type_code(support_type: str, standards: dict[str, Any] | None = None) -> str:
    standards = _ensure_standards(standards)
    if support_type in standards["support_types"]:
        return standards["support_types"][support_type]["code"]

    normalized = support_type.strip().upper()
    known_codes = {item["code"] for item in standards["support_types"].values()}
    if normalized in known_codes:
        return normalized

    for canonical, item in standards["support_types"].items():
        aliases = [canonical, *(item.get("aliases") or [])]
        if any(str(alias).strip().upper() == normalized for alias in aliases):
            return item["code"]

    raise ValueError(f"未知支架类型: {support_type}")


def angle_code(angle: Any) -> str:
    text = str(angle).strip().upper()
    if not text:
        raise ValueError("角度不能为空")
    if text.startswith("ANG"):
        return text.replace(".", "P")
    text = text.replace("°", "").replace("度", "").replace("DEG", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"无法解析角度: {angle}")
    return f"ANG{match.group(0).replace('.', 'P')}"


def project_prefix(support_type: str, angle: Any, standards: dict[str, Any] | None = None) -> str:
    standards = _ensure_standards(standards)
    return "%s_%s" % (support_type_code(support_type, standards), angle_code(angle))


def component_role_entries(standards: dict[str, Any] | None = None) -> list[tuple[str, str, dict[str, Any]]]:
    standards = _ensure_standards(standards)
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for canonical_name, role in standards["component_roles"].items():
        entries.append((str(canonical_name).strip(), str(canonical_name).strip(), role))
        for alias in role.get("aliases") or []:
            alias_text = str(alias).strip()
            if alias_text:
                entries.append((alias_text, str(canonical_name).strip(), role))
    return entries


def _component_role_exact(component_name: str, standards: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    name = str(component_name).strip()
    for entry_name, canonical_name, role in component_role_entries(standards):
        if name == entry_name:
            return canonical_name, role
    return None


def _role_with_code(role: dict[str, Any], code: str) -> dict[str, Any]:
    copied = dict(role)
    copied["code"] = code
    return copied


def _component_role_numbered(component_name: str, standards: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    match = re.fullmatch(r"(?P<base>.+?)(?P<index>\d+)", str(component_name).strip())
    if not match:
        return None
    base = match.group("base").strip()
    index = match.group("index")
    resolved = _component_role_exact(base, standards)
    if not resolved:
        return None
    canonical_name, role = resolved
    code = str(role.get("code", "")).strip().upper()
    if not code or code == "UNKNOWN_COMPONENT":
        return None
    return "%s%s" % (canonical_name, index), _role_with_code(role, "%s_%s" % (code, index))


def component_role_key(component_name: Any, standards: dict[str, Any] | None = None) -> str | None:
    standards = _ensure_standards(standards)
    name = str(component_name or "").strip()
    resolved = _component_role_exact(name, standards) or _component_role_numbered(name, standards)
    if not resolved:
        return None
    return resolved[0]


def _unknown_component_role(component_name: Any) -> dict[str, Any]:
    name = str(component_name or "").strip()
    if re.search(r"[\u4e00-\u9fff]", name):
        sanitized = "UNKNOWN_COMPONENT"
    else:
        sanitized = re.sub(r"[^A-Za-z0-9]+", "_", name.upper()).strip("_") or "UNKNOWN_COMPONENT"
        if not re.match(r"[A-Z_]", sanitized):
            sanitized = "UNKNOWN_COMPONENT"
    return {
        "code": sanitized,
        "model_policy": "MANUAL_TEMPLATE",
        "element_type": "C3D8R",
        "focus_analysis": False,
        "requires_length": False,
    }


def component_role(component_name: str, standards: dict[str, Any] | None = None) -> dict[str, Any]:
    standards = _ensure_standards(standards)
    name = str(component_name).strip()
    resolved = _component_role_exact(name, standards) or _component_role_numbered(name, standards)
    if resolved:
        return resolved[1]
    return _unknown_component_role(name)


def part_name(support_type: str, angle: Any, component_name: str, standards: dict[str, Any] | None = None) -> str:
    standards = _ensure_standards(standards)
    template = standards["part_name"]["format"]
    role = component_role(component_name, standards)
    return template.format(
        support_type_code=support_type_code(support_type, standards),
        angle_code=angle_code(angle),
        component_code=role["code"],
    )


def part_name_from_prefix(project_prefix_value: str, component_name: str, standards: dict[str, Any] | None = None) -> str:
    standards = _ensure_standards(standards)
    role = component_role(component_name, standards)
    return "P_%s_%s" % (project_prefix_value, role["code"])


def component_code_from_part_name(part_name_value: Any) -> str | None:
    text = str(part_name_value or "").strip()
    match = re.fullmatch(r"P_(?:SP_SC|SP_DC|DP)_ANG\d+(?:P\d+)?_(?P<code>[A-Za-z0-9_]+)", text, re.IGNORECASE)
    if match:
        return match.group("code").upper()
    match = re.fullmatch(r"P_(?P<code>[A-Za-z0-9_]+)", text, re.IGNORECASE)
    if match:
        return match.group("code").upper()
    return None


def component_code_from_row(component_row: dict[str, Any]) -> str | None:
    component_code = component_row.get("构件代码")
    component_name = str(component_row.get("构件名称") or "").strip()
    if not component_code and component_name:
        role_code = component_role(component_name).get("code")
        if role_code and role_code != "UNKNOWN_COMPONENT":
            component_code = role_code
    if not component_code:
        component_code = component_code_from_part_name(component_row.get("abaqus_part_name"))
    return str(component_code).strip().upper() if component_code else None


def parse_component_spec(component_row: dict[str, Any]) -> ParsedSpec:
    component_code = component_code_from_row(component_row)
    if is_hoop_component_code(component_code):
        hoop_spec = parse_hoop_spec(component_row.get("规格", ""))
        if hoop_spec.status == "已解析":
            return hoop_spec
    if component_code == "PURLIN_SPLICE":
        return parse_simple_c_spec(component_row.get("规格", ""))
    if component_code in CLAMP_COMPONENT_CODES:
        return parse_clamp_spec(component_row.get("规格", ""), component_code)
    if component_code == "RECTANGULAR_WASHER":
        return parse_rectangular_washer_spec(component_row.get("规格", ""))
    if component_code == "PURLIN_SUPPORT":
        parsed = parse_spec(component_row.get("规格", ""))
        if parsed.section_type == "角钢" and parsed.status == "已解析":
            params = dict(parsed.section_params)
            params["内根圆角_mm"] = params["厚度_mm"]
            return ParsedSpec(parsed.section_type, params, parsed.thickness_mm, parsed.section_code, parsed.status, parsed.message)
    return parse_spec(component_row.get("规格", ""))


def is_valid_abaqus_name(name_value: Any) -> bool:
    text = str(name_value or "").strip()
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text))


def normalize_material_grade(grade: Any) -> str:
    if grade is None:
        return ""
    raw_text = str(grade).strip()
    text = re.sub(r"\s+", "", raw_text.upper())
    text = text.replace("_", "-")
    if not text:
        return ""

    match = re.search(r"(?:AL)?6063-?T5", text)
    if match:
        return "6063-T5"

    match = re.search(r"Q(?P<num>235|345|355|420|450|550)(?P<suffix>[A-Z]?)", text)
    if match:
        suffix = match.group("suffix") or ""
        return "Q%s%s" % (match.group("num"), suffix)

    match = re.search(r"S(?P<num>250|350|420|550)GD", text)
    if match:
        return "S%sGD" % match.group("num")

    return raw_text


def _float_value(value: Any) -> float | None:
    if _is_blank(value):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    return float(match.group(0))


def _rounded_mass(value: float | None) -> float | str:
    if value is None:
        return ""
    return round(value + 0.0, 2)


def _mass_within_tolerance(actual: float, expected: float) -> bool:
    tolerance = max(0.05, abs(expected) * 0.01)
    return abs(actual - expected) <= tolerance


def _mass_check_status(
    theoretical_single_kg: float | None,
    theoretical_total_kg: float | None,
    raw_single_kg: Any,
    raw_total_kg: Any,
) -> str:
    checks: list[bool] = []
    actual_single = _float_value(raw_single_kg)
    actual_total = _float_value(raw_total_kg)
    if theoretical_single_kg is not None and actual_single is not None:
        checks.append(_mass_within_tolerance(actual_single, theoretical_single_kg))
    if theoretical_total_kg is not None and actual_total is not None:
        checks.append(_mass_within_tolerance(actual_total, theoretical_total_kg))
    if not checks:
        return ""
    return "OK" if all(checks) else "CHECK"


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def mm_to_m(value: Any) -> float | None:
    if _is_blank(value):
        return None
    return float(value) * MM_TO_M


def derive_component_row(
    raw_row: dict[str, Any],
    support_type: str,
    angle: Any,
    array_layout: str = "",
    standards: dict[str, Any] | None = None,
) -> dict[str, Any]:
    standards = standards or load_standards()
    name = str(raw_row.get("名称", "")).strip()
    role = component_role(name, standards)
    parsed = parse_spec(raw_row.get("规格", ""))
    policy = role["model_policy"]
    policy_label = standards["model_policy_labels"].get(policy, policy)
    material_grade = normalize_material_grade(raw_row.get("备注", ""))
    material = material_properties(material_grade, standards)
    length_m = mm_to_m(raw_row.get("长度_mm")) or ""
    meter_weight = raw_row.get("构件米重 kg/m", "")
    single_mass = raw_row.get("单位重量 kg", "")
    total_mass = raw_row.get("总重量 kg", "")
    meter_weight_value = _float_value(meter_weight)
    quantity_value = _float_value(raw_row.get("数量", ""))
    theoretical_single_raw = None
    theoretical_total_raw = None
    if meter_weight_value is not None and length_m != "":
        theoretical_single_raw = meter_weight_value * float(length_m)
    if theoretical_single_raw is not None and quantity_value is not None:
        theoretical_total_raw = theoretical_single_raw * quantity_value
    mass_check_status = _mass_check_status(
        theoretical_single_raw,
        theoretical_total_raw,
        single_mass,
        total_mass,
    )

    issues: list[str] = []
    if parsed.status != "已解析":
        issues.append(parsed.message or "规格需人工确认")
    if role.get("requires_length") and _is_blank(raw_row.get("长度_mm")):
        issues.append("长度缺失")
    if _is_blank(raw_row.get("数量")):
        issues.append("数量缺失")
    if _is_blank(material_grade):
        issues.append("材料牌号缺失")

    review_status = "需人工确认" if issues else "待校核"
    return {
        "支架类型": support_type,
        "角度": str(angle),
        "阵列布置": array_layout,
        "构件名称": name,
        "构件代码": role["code"],
        "规格": raw_row.get("规格", ""),
        "长度_mm": raw_row.get("长度_mm", ""),
        "长度_m": length_m,
        "数量": raw_row.get("数量", ""),
        "材料牌号": material_grade,
        "建模方式": policy_label,
        "单元类型": role["element_type"],
        "截面类型": parsed.section_type,
        "截面参数": parsed.params_text(),
        "厚度_mm": parsed.thickness_mm if parsed.thickness_mm is not None else "",
        "厚度_m": mm_to_m(parsed.thickness_mm) or "",
        "材料密度 kg/m³": material.get("density_kg_per_m3") or "",
        "构件米重 kg/m": meter_weight,
        "单件质量 kg": single_mass,
        "总质量 kg": total_mass,
        "理论单件质量 kg": _rounded_mass(theoretical_single_raw),
        "理论总质量 kg": _rounded_mass(theoretical_total_raw),
        "质量校核状态": mass_check_status,
        "是否重点分析": "是" if role.get("focus_analysis") else "否",
        "校核状态": review_status,
        "abaqus_part_name": part_name(support_type, angle, name, standards),
        "section_code": parsed.section_code,
        "解析状态": parsed.status,
        "待确认项": "；".join(issues),
    }


def material_properties(grade: str, standards: dict[str, Any] | None = None) -> dict[str, Any]:
    standards = _ensure_standards(standards)
    normalized = normalize_material_grade(grade)
    material = standards["materials"].get(normalized)
    if not material:
        return {
            "material_grade": normalized,
            "abaqus_name": "MAT_MANUAL_CHECK",
            "elastic_modulus_pa": None,
            "poisson_ratio": None,
            "density_kg_per_m3": None,
        }
    converted = {"material_grade": normalized, **material}
    if "elastic_modulus_pa" not in converted and converted.get("elastic_modulus_mpa") is not None:
        converted["elastic_modulus_pa"] = float(converted["elastic_modulus_mpa"]) * 1_000_000.0
    if "density_kg_per_m3" not in converted and converted.get("density_tonne_per_mm3") is not None:
        converted["density_kg_per_m3"] = float(converted["density_tonne_per_mm3"]) * 1_000_000_000_000.0
    converted.pop("elastic_modulus_mpa", None)
    converted.pop("density_tonne_per_mm3", None)
    return converted


def has_complete_model_dimensions(component_row: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return whether a component has enough dimensions for first-stage Part generation."""
    spec = parse_component_spec(component_row)
    issues: list[str] = []
    if spec.status != "已解析":
        issues.append(spec.message or "规格未解析")

    section_type = spec.section_type
    length = component_row.get("长度_mm")
    material = normalize_material_grade(component_row.get("材料牌号", component_row.get("备注", "")))
    model_policy = str(component_row.get("建模方式", ""))
    part_name_value = component_row.get("abaqus_part_name")
    component_code = component_code_from_row(component_row)

    if _is_blank(component_row.get("构件名称")):
        issues.append("构件名称缺失")
    if _is_blank(part_name_value):
        issues.append("abaqus_part_name缺失")
    elif not is_valid_abaqus_name(part_name_value):
        issues.append("abaqus_part_name只能使用英文、数字和下划线，且不能以数字开头")
    if _is_blank(component_row.get("数量")) and component_code not in CLAMP_COMPONENT_CODES:
        issues.append("数量缺失")
    if not material and component_code not in CLAMP_COMPONENT_CODES:
        issues.append("材料牌号缺失")
    normalized_policy, _element_type = effective_model_policy(component_row)
    if _is_blank(model_policy) and component_code not in FORCED_SOLID_COMPONENT_CODES:
        issues.append("建模方式缺失")
    elif normalized_policy == "MANUAL_TEMPLATE":
        issues.append("人工模板构件暂不自动建模")
    elif normalized_policy == "CONNECTOR_ONLY":
        issues.append("连接器简化构件暂不自动建 Part")
    elif normalized_policy not in {"SHELL", "SOLID"}:
        issues.append("建模方式暂不支持自动建 Part")

    requires_length = section_type in {"C型钢", "无回折C型钢", "圆管", "角钢", "套管撑杆", "圆钢/圆杆"}
    if requires_length and _is_blank(length):
        issues.append("长度缺失")

    params = spec.section_params
    required_by_section = {
        "C型钢": ["高度_mm", "翼缘宽_mm", "卷边_mm", "厚度_mm"],
        "圆管": ["外径_mm", "厚度_mm"],
        "角钢": ["边长A_mm", "边长B_mm", "厚度_mm"],
        "无回折C型钢": ["高度_mm", "翼缘宽_mm", "厚度_mm"],
        "套管撑杆": ["外径_mm", "厚度_mm", "内拉杆直径_mm"],
        "抱箍带": ["内径_mm", "带宽_mm", "厚度_mm", "左直段_mm", "右直段_mm"],
        "中压块V1": ["长度_mm", "长圆孔宽_mm", "长圆孔长_mm", "端距_mm", "孔距_mm"],
        "边压块V1": ["长度_mm", "长圆孔宽_mm", "长圆孔长_mm", "端距_mm", "孔距_mm"],
        "矩形垫片": ["长度_mm", "宽度_mm", "厚度_mm", "孔径_mm"],
        "圆钢/圆杆": ["直径_mm"],
        "螺纹件": ["公称直径_mm"],
    }
    for key in required_by_section.get(section_type, []):
        if key not in params or _is_blank(params.get(key)):
            issues.append(f"{key}缺失")

    if section_type == "螺纹件" and _is_blank(length):
        issues.append("螺栓类构件长度/弯折尺寸缺失")

    return not issues, issues


def effective_model_policy(component_row: dict[str, Any]) -> tuple[str, str]:
    """Normalize model policy for section types that cannot be represented as shells."""
    spec = parse_component_spec(component_row)
    section_type = spec.section_type
    policy = str(component_row.get("建模方式", "")).strip()
    element = str(component_row.get("单元类型", "")).strip()
    label_to_code = {
        "壳单元": "SHELL",
        "实体单元": "SOLID",
        "连接器简化": "CONNECTOR_ONLY",
        "人工模板": "MANUAL_TEMPLATE",
    }
    if component_code_from_row(component_row) in FORCED_SOLID_COMPONENT_CODES and spec.status == "已解析":
        return "SOLID", "C3D8R"
    code = label_to_code.get(policy, policy or "MANUAL_TEMPLATE")
    if code in {"MANUAL_TEMPLATE", "CONNECTOR_ONLY"}:
        return code, element or "C3D8R"
    if section_type == "圆钢/圆杆":
        return "SOLID", "C3D8R"
    if code == "SHELL":
        return "SHELL", element or "S4R"
    if code == "SOLID":
        return "SOLID", element or "C3D8R"
    return code, element or "C3D8R"


def section_kind_and_ascii_params(spec: ParsedSpec) -> tuple[str, dict[str, float | str]]:
    params = spec.section_params
    if spec.section_type == "C型钢":
        return (
            "C_CHANNEL",
            {
                "h_mm": params["高度_mm"],
                "b_mm": params["翼缘宽_mm"],
                "lip_mm": params["卷边_mm"],
                "t_mm": params["厚度_mm"],
            },
        )
    if spec.section_type == "圆管":
        return (
            "PIPE",
            {
                "od_mm": params["外径_mm"],
                "t_mm": params["厚度_mm"],
            },
        )
    if spec.section_type == "角钢":
        return (
            "ANGLE",
            {
                "leg_a_mm": params["边长A_mm"],
                "leg_b_mm": params["边长B_mm"],
                "t_mm": params["厚度_mm"],
                "inner_root_radius_mm": params.get("内根圆角_mm", 0.0),
            },
        )
    if spec.section_type == "无回折C型钢":
        return (
            "C_CHANNEL_SIMPLE",
            {
                "h_mm": params["高度_mm"],
                "b_mm": params["翼缘宽_mm"],
                "t_mm": params["厚度_mm"],
            },
        )
    if spec.section_type == "套管撑杆":
        return (
            "STRUT_PIPE",
            {
                "od_mm": params["外径_mm"],
                "t_mm": params["厚度_mm"],
                "inner_rod_diameter_mm": params["内拉杆直径_mm"],
            },
        )
    if spec.section_type == "抱箍带":
        return (
            "HOOP_BAND",
            {
                "diameter_mm": params["内径_mm"],
                "width_mm": params["带宽_mm"],
                "t_mm": params["厚度_mm"],
                "left_extension_mm": params["左直段_mm"],
                "right_extension_mm": params["右直段_mm"],
                "inner_radius_mm": params["内半径_mm"],
                "outer_radius_mm": params["外半径_mm"],
                "transition_fillet_mm": params.get("过渡圆角_mm", 0.0),
            },
        )
    if spec.section_type in {"中压块V1", "边压块V1"}:
        kind = "MID_CLAMP_PROFILE" if spec.section_type == "中压块V1" else "EDGE_CLAMP_PROFILE"
        return (
            kind,
            {
                "length_mm": params["长度_mm"],
                "slot_width_mm": params["长圆孔宽_mm"],
                "slot_length_mm": params["长圆孔长_mm"],
                "end_distance_mm": params["端距_mm"],
                "pitch_mm": params["孔距_mm"],
                "hole_1_center_mm": params["孔1中心_mm"],
                "hole_2_center_mm": params["孔2中心_mm"],
            },
        )
    if spec.section_type == "圆钢/圆杆":
        return (
            "ROD",
            {
                "diameter_mm": params["直径_mm"],
            },
        )
    if spec.section_type == "螺纹件":
        return (
            "THREADED",
            {
                "nominal_diameter_mm": params["公称直径_mm"],
            },
        )
    return "UNKNOWN", {"raw": params.get("原始规格", "")}


def section_kind_and_model_params(spec: ParsedSpec) -> tuple[str, dict[str, float | str]]:
    """Return Abaqus-ready section parameters in m."""
    kind, params_mm = section_kind_and_ascii_params(spec)
    converted: dict[str, float | str] = {}
    for key, value in params_mm.items():
        if key == "raw":
            converted[key] = value
        elif key.endswith("_mm"):
            converted[key[:-3] + "_m"] = mm_to_m(value)
        else:
            converted[key] = value
    return kind, converted
