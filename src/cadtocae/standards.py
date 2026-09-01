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

    match = re.fullmatch(
        r"Φ(?P<diameter>\d+(?:\.\d+)?)X(?P<width>\d+(?:\.\d+)?)X(?P<t>\d+(?:\.\d+)?)",
        normalized,
    )
    if match:
        diameter, width, t = (_number(match.group(key)) for key in ("diameter", "width", "t"))
        return ParsedSpec(
            "抱箍带",
            {"内径或适配直径_mm": diameter, "宽度_mm": width, "厚度_mm": t},
            t,
            _section_code("HOOP", diameter, width, t),
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
    spec = parse_spec(component_row.get("规格", ""))
    issues: list[str] = []
    if spec.status != "已解析":
        issues.append(spec.message or "规格未解析")

    section_type = spec.section_type
    length = component_row.get("长度_mm")
    material = normalize_material_grade(component_row.get("材料牌号", component_row.get("备注", "")))
    model_policy = str(component_row.get("建模方式", ""))
    part_name_value = component_row.get("abaqus_part_name")

    if _is_blank(component_row.get("构件名称")):
        issues.append("构件名称缺失")
    if _is_blank(part_name_value):
        issues.append("abaqus_part_name缺失")
    elif not is_valid_abaqus_name(part_name_value):
        issues.append("abaqus_part_name只能使用英文、数字和下划线，且不能以数字开头")
    if _is_blank(component_row.get("数量")):
        issues.append("数量缺失")
    if not material:
        issues.append("材料牌号缺失")
    normalized_policy, _element_type = effective_model_policy(component_row)
    if _is_blank(model_policy):
        issues.append("建模方式缺失")
    elif normalized_policy == "MANUAL_TEMPLATE":
        issues.append("人工模板构件暂不自动建模")
    elif normalized_policy == "CONNECTOR_ONLY":
        issues.append("连接器简化构件暂不自动建 Part")
    elif normalized_policy not in {"SHELL", "SOLID"}:
        issues.append("建模方式暂不支持自动建 Part")

    requires_length = section_type in {"C型钢", "圆管", "角钢", "套管撑杆", "圆钢/圆杆"}
    if requires_length and _is_blank(length):
        issues.append("长度缺失")

    params = spec.section_params
    required_by_section = {
        "C型钢": ["高度_mm", "翼缘宽_mm", "卷边_mm", "厚度_mm"],
        "圆管": ["外径_mm", "厚度_mm"],
        "角钢": ["边长A_mm", "边长B_mm", "厚度_mm"],
        "套管撑杆": ["外径_mm", "厚度_mm", "内拉杆直径_mm"],
        "抱箍带": ["内径或适配直径_mm", "宽度_mm", "厚度_mm"],
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
    section_type = parse_spec(component_row.get("规格", "")).section_type
    policy = str(component_row.get("建模方式", "")).strip()
    element = str(component_row.get("单元类型", "")).strip()
    label_to_code = {
        "壳单元": "SHELL",
        "实体单元": "SOLID",
        "连接器简化": "CONNECTOR_ONLY",
        "人工模板": "MANUAL_TEMPLATE",
    }
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
                "inner_or_fit_diameter_mm": params["内径或适配直径_mm"],
                "width_mm": params["宽度_mm"],
                "t_mm": params["厚度_mm"],
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
