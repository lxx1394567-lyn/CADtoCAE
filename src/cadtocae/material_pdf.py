from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher
from dataclasses import asdict, dataclass
from bisect import bisect_right
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image, ImageEnhance, ImageOps

from .standards import angle_code, load_standards, normalize_material_grade, project_prefix
from .workbook import RAW_HEADERS, create_material_workbook, normalize_raw_rows


DEFAULT_SUPPORT_TYPE = "单桩单立柱"
DEFAULT_ANGLE = "20"
DEFAULT_LAYOUT = "2行7列竖向"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
SUPPORTED_DOCUMENT_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES
IMAGE_FILENAME_ANGLE_PATTERN = re.compile(r"^(?P<angle>\d+(?:\.\d+)?)-")
IMAGE_FILENAME_ANGLE_ERROR = (
    "无法从文件名读取支架倾角。\n"
    "请按以下格式命名图片：\n"
    "<倾角>-<项目/图纸信息>-<支架类型>.png\n\n"
    "示例：\n"
    "20-项目A-T0101-单桩单立柱.png"
)

MATERIAL_GRADES = re.compile(r"\b([QO0]\s*[0-9O]{3,4}\s*[A-Z8]?|S\s*[0-9O]{3}\s*G\s*[D0O]|(?:AL)?6063\s*[- ]?\s*T5)\b", re.IGNORECASE)
SPEC_HINT = re.compile(
    r"(?:^|[^A-Z0-9])(?:C|L|M)\s*\d+|[ΦφØø∅]\s*\d+|D\s*\d+\s*[xX×]\s*\d+|T\s*=\s*\d+",
    re.IGNORECASE,
)
DIAMETER_SPEC_PATTERN = re.compile(
    r"^(?P<marker>[ΦφØø∅Oo0])(?P<body>\d+(?:\.\d+)?(?:[×X]\d+(?:\.\d+)?){0,2})$"
)
Q_MATERIAL_GRADES = {
    "Q235": "Q235",
    "Q235B": "Q235B",
    "Q345": "Q345",
    "Q345B": "Q345B",
    "Q355": "Q355",
    "Q355B": "Q355B",
    "Q420": "Q420",
    "Q420B": "Q420B",
    "Q450": "Q450",
    "Q450B": "Q450B",
    "Q550": "Q550",
    "Q550B": "Q550B",
}
ENGINEERING_COMPONENT_NAMES = (
    "斜梁",
    "立柱",
    "前立柱",
    "后立柱",
    "上立柱",
    "下立柱",
    "预埋钢管",
    "前斜撑",
    "后斜撑",
    "檩条",
    "檩条拼接件",
    "檩托",
    "柱间支撑",
    "柱间拉杆",
    "立柱拉杆",
    "斜梁拉杆",
    "三角连接件",
    "柱间支撑连接件",
    "抱箍",
    "斜撑抱箍",
    "抱箍1",
    "抱箍2",
    "抱箍组合1",
    "抱箍组合2",
    "抱箍组合3",
    "斜拉条",
    "直拉条",
    "水平拉杆",
    "水平拉杆垫脚",
    "边压块",
    "中压块",
    "背板",
    "M8U型螺栓",
    "撑杆",
    "U型螺栓",
    "防水垫圈",
)
COMPONENT_NAME_CHAR_ALIASES = {
    "標": "檩",
    "棕": "檩",
    "檬": "檩",
    "擦": "檩",
    "粱": "梁",
    "桂": "柱",
    "拄": "柱",
    "住": "柱",
    "仵": "件",
    "牛": "件",
    "台": "合",
    "菇": "箍",
    "筛": "箍",
    "籍": "箍",
    "撑": "撑",
}
NameCellOcr = Callable[[tuple[int, int, int, int]], tuple[str, float]]


def parse_angle_from_image_filename(image_path: str | Path) -> str:
    """Parse the leading '<angle>-' field required for Step01 image inputs."""
    stem = Path(image_path).stem.strip()
    match = IMAGE_FILENAME_ANGLE_PATTERN.match(stem)
    if not match:
        raise ValueError(IMAGE_FILENAME_ANGLE_ERROR)
    angle = match.group("angle")
    if "." in angle:
        angle = angle.rstrip("0").rstrip(".")
    angle = angle.lstrip("0") or "0"
    if angle.startswith("."):
        angle = "0%s" % angle
    return angle


@dataclass
class PdfMaterialResult:
    pdf_path: str
    project_prefix: str
    support_type: str
    angle: str
    rows: list[dict[str, Any]]
    status: str
    messages: list[str]
    used_pages: list[int]
    extraction_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrToken:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0


@dataclass
class BatchMaterialOutput:
    pdf_path: str
    status: str
    project_prefix: str
    project_dir: str
    workbook_path: str | None
    manual_template_path: str | None
    report_path: str | None
    row_count: int
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _clean_ocr_text(value: Any) -> str:
    text = _clean_cell(value)
    replacements = {
        "（": "(",
        "）": ")",
        "＊": "×",
        "*": "×",
        "x": "×",
        "X": "X",
        "〇": "0",
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "φ": "Φ",
        "Ø": "Φ",
        "ø": "Φ",
        "∅": "Φ",
        "—": "-",
        "–": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _clean_cell(value))


def _safe_name(value: str, max_len: int = 80) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    cleaned = re.sub(r"_+", "_", cleaned)
    return (cleaned or "pdf").strip()[:max_len]


def source_key_from_material_filename(source_path: str | Path, max_len: int = 90) -> str:
    stem = Path(source_path).stem.strip()
    parts = [part.strip() for part in stem.split("-") if part.strip()]
    if parts and re.fullmatch(r"\d+(?:\.\d+)?", parts[0]):
        parts = parts[1:]

    key_parts: list[str] = []
    for part in parts:
        chunks = re.findall(r"[A-Za-z0-9]+", part)
        if not chunks:
            continue
        key_parts.append("-".join(chunks).upper())

    key = "-".join(key_parts)
    key = re.sub(r"-+", "-", key).strip("-")
    if len(key) > max_len:
        key = key[:max_len].strip("-")
    return key or "SOURCE"


def _unique_batch_file(
    output_root: Path,
    base_stem: str,
    suffix: str,
    seen_paths: set[str],
    overwrite: bool = False,
) -> Path:
    candidate = output_root / ("%s%s" % (base_stem, suffix))
    candidate_key = str(candidate.resolve()).lower()
    if candidate_key not in seen_paths and (overwrite or not candidate.exists()):
        seen_paths.add(candidate_key)
        return candidate

    counter = 2
    while True:
        candidate = output_root / ("%s_%02d%s" % (base_stem, counter, suffix))
        candidate_key = str(candidate.resolve()).lower()
        if candidate_key not in seen_paths and not candidate.exists():
            seen_paths.add(candidate_key)
            return candidate
        counter += 1


def _is_int_text(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{1,4}", _sequence_text(value)))


def _is_number_text(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{1,7}(?:\.\d+)?", _compact(value)))


def _looks_like_spec(value: Any) -> bool:
    text = _compact(_clean_ocr_text(value)).replace("×", "X")
    return bool(SPEC_HINT.search(text))


def _looks_like_name(value: Any) -> bool:
    text = _compact(value)
    if not text or _is_number_text(text) or _looks_like_spec(text):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", text))


def _normalize_spec_numeric_ocr_noise(text: str) -> str:
    return re.sub(r"(?<=\d)[Oo](?=\d|[×X.]|\s|$)|(?<=\.)[Oo](?=\d|[×X]|\s|$)", "0", text)


def normalize_ocr_section_spec(spec: Any) -> str:
    text = _clean_ocr_text(spec)
    text = re.sub(r"\s*([×X])\s*", r"\1", text)
    text = re.sub(r"\s*=\s*", "=", text)
    text = _normalize_spec_numeric_ocr_noise(text)
    compact = re.sub(r"\s+", "", text)
    match = DIAMETER_SPEC_PATTERN.fullmatch(compact)
    if match:
        return "φ%s" % match.group("body")
    text = re.sub(r"[ΦφØø∅](?=\d|=\d)", "φ", text)
    text = re.sub(r"(?<=钢管)[ΦφØø∅Oo0?](?=\d)", "φ", text)
    if re.search(r"\bT=\d", text, re.IGNORECASE):
        text = re.sub(r"(?<=[\s\d])[ΦφØø∅Oo0?](?==\d)", "φ", text)
    return text


def _spec_key(value: Any) -> str:
    return _compact(_clean_ocr_text(value)).replace("×", "X").replace("φ", "Φ")


def normalize_ocr_material_grade(grade: Any) -> str:
    text = _clean_ocr_text(grade)
    compact = _compact(text).upper()
    if not compact:
        return ""

    candidate = compact
    if len(candidate) >= 2 and candidate[0] in {"0", "O"} and candidate[1].isdigit():
        candidate = "Q%s" % candidate[1:]
    if candidate.startswith("Q"):
        body = candidate[1:]
        body = body.replace("O", "0")
        if len(body) == 4 and body[-1] in {"8", "B"} and body[:3].isdigit():
            candidate = "Q%sB" % body[:3]
        elif len(body) == 3 and body.isdigit():
            candidate = "Q%s" % body
        if candidate in Q_MATERIAL_GRADES:
            return Q_MATERIAL_GRADES[candidate]

    s_match = re.fullmatch(r"S(?P<num>[0-9O]{3})G(?P<tail>[D0O])", candidate)
    if s_match:
        number = s_match.group("num").replace("O", "0")
        return "S%sGD" % number

    return normalize_material_grade(text)


def normalize_ocr_material_remark(remark: Any) -> str:
    text = _clean_ocr_text(remark)
    if not text:
        return ""
    match = MATERIAL_GRADES.search(text)
    if not match:
        return text
    raw_grade = match.group(0).strip()
    normalized_grade = normalize_ocr_material_grade(raw_grade)
    if not normalized_grade:
        return text
    raw_compact = _compact(raw_grade).upper()
    normalized_compact = normalized_grade.replace(" ", "").upper()
    replacement = raw_grade if raw_compact == normalized_compact else normalized_grade
    return "%s%s%s" % (text[: match.start()], replacement, text[match.end() :])


def _normalized_grade_key(value: Any) -> str:
    return normalize_ocr_material_grade(value).replace(" ", "").upper()


def normalize_ocr_component_name(name: Any) -> str:
    text = _compact(_clean_ocr_text(name))
    if not text:
        return ""
    if text in ENGINEERING_COMPONENT_NAMES:
        return text

    normalized = text
    for source, target in COMPONENT_NAME_CHAR_ALIASES.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"(?<=抱箍组合)[lI|]", "1", normalized)
    if normalized in ENGINEERING_COMPONENT_NAMES:
        return normalized

    combo_match = re.fullmatch(r"抱.组合(?P<num>[123])", normalized)
    if combo_match:
        return "抱箍组合%s" % combo_match.group("num")

    if not re.search(r"[\u4e00-\u9fff]", normalized):
        return text
    best_name = ""
    best_score = 0.0
    for candidate in ENGINEERING_COMPONENT_NAMES:
        score = SequenceMatcher(None, normalized, candidate).ratio()
        if score > best_score:
            best_name = candidate
            best_score = score
    if len(best_name) <= 2:
        threshold = 0.80
    elif len(best_name) <= 4:
        threshold = 0.72
    else:
        threshold = 0.70
    if best_name and best_score >= threshold and set(normalized) & set(best_name):
        return best_name
    return text


def looks_like_unreliable_component_name(name: Any) -> bool:
    text = _compact(_clean_ocr_text(name))
    if not text or text == "支架":
        return True
    normalized = normalize_ocr_component_name(text)
    if normalized in ENGINEERING_COMPONENT_NAMES:
        return False
    if len(text) == 1:
        return True
    if "?" in text or "\ufffd" in text:
        return True

    spec_text = normalize_ocr_section_spec(text)
    compact_spec = _compact(spec_text).replace("×", "X").upper()
    if _looks_like_spec(spec_text):
        return True
    if re.fullmatch(r"(?:[CLTDM]\d.*|T=\d.*|M\d+)", compact_spec):
        return True
    if re.search(r"\d", compact_spec) and ("圆钢" in text or "钢管" in text):
        return True
    if re.search(r"\d", compact_spec) and any(mark in compact_spec for mark in ("X", "=", "Φ", "φ")):
        return True
    return False


def _should_refine_name_cell(name: Any, confidence: float | None) -> bool:
    if looks_like_unreliable_component_name(name):
        return True
    if confidence is not None and confidence < 55.0:
        return True
    return False


def _component_name_quality(name: Any, confidence: float | None) -> float:
    text = _compact(_clean_ocr_text(name))
    if not text:
        return -10.0
    normalized = normalize_ocr_component_name(text)
    score = (confidence if confidence is not None else 0.0) / 100.0
    if normalized in ENGINEERING_COMPONENT_NAMES:
        score += 3.0
    elif re.search(r"[\u4e00-\u9fff]", normalized):
        score += 1.0
    if looks_like_unreliable_component_name(normalized):
        score -= 3.0
    return score


def _select_refined_name(
    original_name: Any,
    original_confidence: float | None,
    refined_name: Any,
    refined_confidence: float,
) -> tuple[str, bool]:
    original = _clean_ocr_text(original_name)
    refined = normalize_ocr_component_name(refined_name)
    if not refined or looks_like_unreliable_component_name(refined):
        return original, False

    if looks_like_unreliable_component_name(original) and refined_confidence >= 35.0:
        return refined, refined != original

    original_quality = _component_name_quality(original, original_confidence)
    refined_quality = _component_name_quality(refined, refined_confidence)
    if refined_quality >= original_quality + 0.4 and refined_confidence >= 35.0:
        return refined, refined != original
    return original, False


def _numeric_value(value: Any) -> float | None:
    text = _numeric_text(value)
    if not text:
        return None
    return float(text)


def _length_value_m(value: Any) -> float | None:
    number = _numeric_value(value)
    if number is None:
        return None
    return number / 1000.0 if number > 50 else number


def _infer_component_name_from_context(spec: Any, length: Any, quantity: Any, remark: Any, sequence: Any) -> str:
    spec_text = _spec_key(spec)
    grade = _normalized_grade_key(remark)
    length_value = _length_value_m(length)
    quantity_text = _numeric_text(quantity)
    sequence_text = _sequence_text(sequence)

    if spec_text == "Φ60X2.0" and grade == "S350GD" and quantity_text == "5":
        if length_value is not None and length_value < 2.0:
            return "前立柱"
        if length_value is not None and length_value >= 2.0:
            return "后立柱"
    if spec_text == "Φ76X4.0" and grade == "Q235B" and quantity_text == "10":
        return "预埋钢管"
    if spec_text == "C80X40X15X2.0" and grade == "S350GD" and quantity_text == "5":
        return "斜梁"
    if spec_text == "C50X30X15X2.0" and grade == "S250GD" and quantity_text == "5":
        if sequence_text == "5":
            return "前斜撑"
        if sequence_text == "6":
            return "后斜撑"
    if spec_text == "C90X50X15X1.8" and grade == "S420GD" and quantity_text == "4":
        return "檩条"
    if spec_text == "Φ10" and grade == "Q235B" and quantity_text == "8":
        return "立柱拉杆"
    return ""


def _extract_material_grade(cells: Iterable[Any]) -> str:
    combined = " ".join(_clean_cell(cell) for cell in cells if _clean_cell(cell))
    match = MATERIAL_GRADES.search(combined)
    if not match:
        return ""
    return normalize_ocr_material_grade(re.sub(r"\s+", " ", match.group(1).upper().replace("-", "-")).strip())


def _sequence_text(value: Any) -> str:
    text = _compact(_clean_ocr_text(value))
    circled = {
        "①": "1",
        "②": "2",
        "③": "3",
        "④": "4",
        "⑤": "5",
        "⑥": "6",
        "⑦": "7",
        "⑧": "8",
        "⑨": "9",
        "⑩": "10",
        "⑪": "11",
        "⑫": "12",
        "⑬": "13",
        "⑭": "14",
        "⑮": "15",
        "⑯": "16",
        "⑰": "17",
        "⑱": "18",
        "⑲": "19",
        "⑳": "20",
    }
    for source, target in circled.items():
        text = text.replace(source, target)
    match = re.search(r"\d{1,4}", text)
    return match.group(0) if match else ""


def _numeric_text(value: Any) -> str:
    text = _compact(_clean_ocr_text(value))
    match = re.search(r"\d+(?:\.\d+)?", text)
    return match.group(0) if match else ""


def _format_number(value: float, max_decimals: int = 3) -> str:
    text = ("%%.%sf" % max_decimals) % value
    return text.rstrip("0").rstrip(".")


def _length_mm_from_header(row: list[Any], header: dict[str, int]) -> str:
    length_mm = _numeric_text(_value_at(row, header.get("长度_mm")))
    if length_mm:
        return length_mm
    length_m = _numeric_text(_value_at(row, header.get("长度_m")))
    if not length_m:
        return ""
    return _format_number(float(length_m) * 1000.0)


def _header_key(value: Any) -> str | None:
    text = _compact(_clean_ocr_text(value))
    upper_text = text.upper()
    if not text:
        return None
    if "序号" in text or text in {"编号", "NO", "NO."}:
        return "序号"
    if any(keyword in text for keyword in ("构件米重", "每米重量", "米重", "单位长度重量")) or "KG/M" in upper_text:
        return "构件米重 kg/m"
    if "单位重量" in text or "单件重量" in text:
        return "单位重量 kg"
    if "总重量" in text or "总重" in text:
        return "总重量 kg"
    if "名称" in text or "构件" in text or "零件" in text:
        return "名称"
    if "规格" in text or "型号" in text:
        return "规格"
    if "长度" in text or upper_text in {"L", "L/MM", "LMM", "L/M", "LM"}:
        if "MM" in upper_text or "毫米" in text:
            return "长度_mm"
        if upper_text in {"L/M", "LM"}:
            return "长度_m"
        if re.search(r"(?:^|[（(])M(?:[）)]|$)", upper_text) or "米" in text:
            return "长度_m"
        return "长度_mm"
    if "数量" in text or "件数" in text or "个数" in text:
        return "数量"
    if "备注" in text or "材质" in text or "材料" in text or "牌号" in text:
        return "备注"
    if "类别" in text:
        return "类别"
    if "页码" in text or "页号" in text:
        return "来源页码"
    return None


def _header_score(row: list[Any]) -> int:
    keys = {_header_key(cell) for cell in row}
    keys.discard(None)
    return len(keys)


def _map_header(row: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(row):
        key = _header_key(cell)
        if key and key not in mapping:
            mapping[key] = index
    return mapping


def _value_at(row: list[Any], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return _clean_cell(row[index])


def _row_from_header_map(row: list[Any], header: dict[str, int], page_number: int) -> dict[str, Any] | None:
    seq = _value_at(row, header.get("序号"))
    name = _value_at(row, header.get("名称"))
    spec = _value_at(row, header.get("规格"))
    length = _length_mm_from_header(row, header)
    quantity = _value_at(row, header.get("数量"))
    meter_weight = _numeric_text(_value_at(row, header.get("构件米重 kg/m")))
    unit_weight = _numeric_text(_value_at(row, header.get("单位重量 kg")))
    total_weight = _numeric_text(_value_at(row, header.get("总重量 kg")))
    remark = _value_at(row, header.get("备注"))

    if not seq and row and _is_int_text(row[0]):
        seq = _clean_cell(row[0])
    if not spec:
        spec_index = next((i for i, cell in enumerate(row) if _looks_like_spec(cell)), None)
        spec = _value_at(row, spec_index)
    if not name:
        spec_index = next((i for i, cell in enumerate(row) if _looks_like_spec(cell)), None)
        candidates = row[: spec_index if spec_index is not None else len(row)]
        name = next((_clean_cell(cell) for cell in candidates if _looks_like_name(cell)), "")
    if not remark:
        remark = _extract_material_grade(row)

    if not (seq or name or spec):
        return None
    if not (name or spec):
        return None
    if not spec and not _looks_like_name(name):
        return None

    return {
        "类别": _value_at(row, header.get("类别")) or "支架",
        "序号": seq,
        "名称": name,
        "规格": spec,
        "长度_mm": length,
        "数量": quantity,
        "构件米重 kg/m": meter_weight,
        "单位重量 kg": unit_weight,
        "总重量 kg": total_weight,
        "备注": remark,
        "来源页码": str(page_number),
        "识别置信度": "0.85",
    }


def _infer_row_without_header(row: list[Any], page_number: int) -> dict[str, Any] | None:
    cells = [_clean_cell(cell) for cell in row if _clean_cell(cell)]
    if len(cells) < 3:
        return None

    seq_index = next((i for i, cell in enumerate(cells) if _is_int_text(cell)), None)
    spec_index = next((i for i, cell in enumerate(cells) if _looks_like_spec(cell)), None)
    if spec_index is None:
        return None

    seq = cells[seq_index] if seq_index is not None else ""
    name_candidates = cells[:spec_index]
    if seq_index is not None:
        name_candidates = [cell for i, cell in enumerate(cells[:spec_index]) if i != seq_index]
    name = next((cell for cell in reversed(name_candidates) if _looks_like_name(cell)), "")

    trailing = cells[spec_index + 1 :]
    length = ""
    quantity = ""
    for value in trailing:
        if not _is_number_text(value):
            continue
        number = float(value)
        if not length and number > 20:
            length = value
            continue
        if not quantity and number <= 10000:
            quantity = value
            break

    remark = _extract_material_grade(cells)
    if not name and not seq:
        return None
    return {
        "类别": "支架",
        "序号": seq,
        "名称": name,
        "规格": cells[spec_index],
        "长度_mm": length,
        "数量": quantity,
        "构件米重 kg/m": "",
        "单位重量 kg": "",
        "总重量 kg": "",
        "备注": remark,
        "来源页码": str(page_number),
        "识别置信度": "0.70",
    }


def rows_from_tables(tables_by_page: list[tuple[int, list[list[Any]]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page_number, table in tables_by_page:
        header: dict[str, int] | None = None
        for raw_row in table:
            row = list(raw_row or [])
            if not any(_clean_cell(cell) for cell in row):
                continue
            if _header_score(row) >= 3:
                header = _map_header(row)
                continue
            if header:
                material_row = _row_from_header_map(row, header, page_number)
            else:
                material_row = _infer_row_without_header(row, page_number)
            if material_row:
                rows.append(material_row)
    return _postprocess_ocr_rows(_dedupe_rows(rows))


def rows_from_text(text_pages: list[tuple[int, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*(?P<seq>\d{1,3})[\s、.．-]+"
        r"(?P<name>[\u4e00-\u9fffA-Za-z0-9()（）_-]{1,20})\s+"
        r"(?P<spec>[CLDMΦφØ∅][A-Za-z0-9ΦφØ∅×Xx*＊().（）/-]+)\s+"
        r"(?:(?P<length>\d{2,7}(?:\.\d+)?)\s+)?"
        r"(?P<qty>\d{1,5})(?:\s+(?P<remark>.*))?$"
    )
    for page_number, text in text_pages:
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if not line or any(keyword in line for keyword in ("材料表", "序号 名称", "类别 序号")):
                continue
            match = pattern.match(line)
            if not match:
                continue
            rows.append(
                {
                    "类别": "支架",
                    "序号": match.group("seq") or "",
                    "名称": match.group("name") or "",
                    "规格": match.group("spec") or "",
                    "长度_mm": match.group("length") or "",
                    "数量": match.group("qty") or "",
                    "备注": _extract_material_grade([match.group("remark") or ""]),
                    "来源页码": str(page_number),
                    "识别置信度": "0.65",
                }
            )
    return _postprocess_ocr_rows(_dedupe_rows(rows))


def _line_centers_from_counts(counts: list[int], threshold: int, min_gap: int = 2) -> list[int]:
    groups: list[list[int]] = []
    current: list[int] = []
    for index, count in enumerate(counts):
        if count >= threshold:
            if current and index - current[-1] > min_gap:
                groups.append(current)
                current = []
            current.append(index)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [int(round(sum(group) / len(group))) for group in groups]


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _merge_near_duplicate_grid_lines(lines: list[int], axis_name: str) -> tuple[list[int], str | None]:
    if len(lines) < 5:
        return lines, None
    gaps = [right - left for left, right in zip(lines, lines[1:]) if right > left]
    median_gap = _median(gaps)
    if median_gap <= 0:
        return lines, None

    duplicate_gap_limit = max(4, int(round(median_gap * 0.32)))
    duplicate_gap_limit = min(duplicate_gap_limit, 24)
    groups: list[list[int]] = []
    current = [lines[0]]
    for line in lines[1:]:
        gap = line - current[-1]
        if gap <= duplicate_gap_limit:
            current.append(line)
        else:
            groups.append(current)
            current = [line]
    groups.append(current)

    if not any(len(group) > 1 for group in groups):
        return lines, None
    merged = [int(round(sum(group) / len(group))) for group in groups]
    if len(merged) < 4:
        return lines, "%s近距离重复线过滤后仅剩 %s 条，保留原始 %s 条。" % (axis_name, len(merged), len(lines))

    return merged, "%s近距离重复线过滤: %s -> %s；典型间距 %.1f，重复阈值 %s。" % (
        axis_name,
        len(lines),
        len(merged),
        median_gap,
        duplicate_gap_limit,
    )


def detect_table_grid(image_path: str | Path) -> tuple[list[int], list[int], list[str]]:
    messages: list[str] = []
    with Image.open(image_path) as image:
        gray = image.convert("L")
        width, height = gray.size
        pixels = gray.load()
        dark = 170

        row_counts: list[int] = []
        for y in range(height):
            row_counts.append(sum(1 for x in range(width) if pixels[x, y] < dark))
        col_counts: list[int] = []
        for x in range(width):
            col_counts.append(sum(1 for y in range(height) if pixels[x, y] < dark))

    horizontal_threshold = max(80, int(width * 0.30))
    vertical_threshold = max(80, int(height * 0.28))
    horizontals = _line_centers_from_counts(row_counts, horizontal_threshold)
    verticals = _line_centers_from_counts(col_counts, vertical_threshold)
    filtered_verticals, vertical_message = _merge_near_duplicate_grid_lines(verticals, "竖线")
    filtered_horizontals, horizontal_message = _merge_near_duplicate_grid_lines(horizontals, "横线")
    if vertical_message:
        messages.append(vertical_message)
    if horizontal_message:
        messages.append(horizontal_message)
    verticals = filtered_verticals
    horizontals = filtered_horizontals

    if len(horizontals) < 4 or len(verticals) < 4:
        messages.append(
            "未检测到清晰材料表网格线，建议截取完整表格区域并保持黑白清晰。检测到横线 %s 条、竖线 %s 条。"
            % (len(horizontals), len(verticals))
        )
    else:
        messages.append("检测到材料表网格线：横线 %s 条、竖线 %s 条。" % (len(horizontals), len(verticals)))

    return verticals, horizontals, messages


def _ocr_image_variants(image_path: str | Path, temp_dir: Path) -> tuple[list[tuple[Path, float, str]], list[str]]:
    variants = [(Path(image_path), 1.0, "原图")]
    messages: list[str] = []
    try:
        with Image.open(image_path) as image:
            gray = ImageOps.grayscale(image)
            enhanced = ImageOps.autocontrast(gray)
            enhanced = ImageEnhance.Contrast(enhanced).enhance(1.6)
            width, height = enhanced.size
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            scaled = enhanced.resize((width * 2, height * 2), resample)
            variant = temp_dir / "ocr_grayscale_contrast_2x.png"
            scaled.save(variant)
            variants.append((variant, 2.0, "2x 灰度增强"))
    except Exception as exc:
        messages.append("OCR 图像预处理跳过: %s" % exc)
    return variants, messages


def preprocess_name_cell_crop(
    image_path: str | Path,
    bbox: tuple[int, int, int, int],
    scale: int = 3,
    padding: int = 8,
) -> Image.Image:
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return Image.new("L", (max(1, scale), max(1, scale)), 255)

    with Image.open(image_path) as image:
        width, height = image.size
        left = max(0, min(width, int(left)))
        right = max(0, min(width, int(right)))
        top = max(0, min(height, int(top)))
        bottom = max(0, min(height, int(bottom)))
        if right <= left or bottom <= top:
            return Image.new("L", (max(1, scale), max(1, scale)), 255)

        inset = min(3, max(1, (right - left) // 20), max(1, (bottom - top) // 8))
        crop_left = min(right, left + inset)
        crop_top = min(bottom, top + inset)
        crop_right = max(crop_left, right - inset)
        crop_bottom = max(crop_top, bottom - inset)
        if crop_right <= crop_left or crop_bottom <= crop_top:
            return Image.new("L", (max(1, scale), max(1, scale)), 255)

        crop = image.crop((crop_left, crop_top, crop_right, crop_bottom))
        gray = ImageOps.grayscale(crop)

    padded = ImageOps.expand(gray, border=max(0, padding), fill=255)
    enhanced = ImageOps.autocontrast(padded)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.5)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.35)
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    return enhanced.resize((enhanced.width * scale, enhanced.height * scale), resample)


def _rapidocr_tokens_from_image(ocr: Any, image_path: str | Path, scale: float) -> list[OcrToken]:
    result, _elapsed = ocr(str(image_path))
    tokens: list[OcrToken] = []
    for box, text, confidence in result or []:
        text = _clean_ocr_text(text)
        if not text:
            continue
        xs = [point[0] / scale for point in box]
        ys = [point[1] / scale for point in box]
        tokens.append(
            OcrToken(
                text=text,
                left=int(round(min(xs))),
                top=int(round(min(ys))),
                width=max(1, int(round(max(xs) - min(xs)))),
                height=max(1, int(round(max(ys) - min(ys)))),
                confidence=float(confidence) * 100.0,
            )
        )
    return tokens


def _ocr_name_cell_from_image(image_path: str | Path, bbox: tuple[int, int, int, int], ocr: Any) -> tuple[str, float]:
    with tempfile.TemporaryDirectory() as tmp:
        crop_path = Path(tmp) / "name_cell_ocr.png"
        preprocessed = preprocess_name_cell_crop(image_path, bbox)
        preprocessed.save(crop_path)
        tokens = _rapidocr_tokens_from_image(ocr, crop_path, 1.0)
    if not tokens:
        return "", 0.0
    ordered = sorted(tokens, key=lambda token: (token.top, token.left))
    text = _clean_ocr_text(" ".join(token.text for token in ordered))
    confidence = sum(max(0.0, min(100.0, token.confidence)) for token in tokens) / len(tokens)
    return text, confidence


def _make_name_cell_ocr(image_path: str | Path, diagnostics: list[str]) -> NameCellOcr:
    ocr: Any | None = None
    unavailable = False

    def run(bbox: tuple[int, int, int, int]) -> tuple[str, float]:
        nonlocal ocr, unavailable
        if unavailable:
            return "", 0.0
        if ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                ocr = RapidOCR()
            except Exception as exc:
                unavailable = True
                diagnostics.append("名称单元格二次 OCR 失败: %s" % exc)
                return "", 0.0
        try:
            return _ocr_name_cell_from_image(image_path, bbox, ocr)
        except Exception as exc:
            diagnostics.append("名称单元格二次 OCR 失败: %s" % exc)
            return "", 0.0

    return run


def _ocr_token_score(tokens: list[OcrToken]) -> float:
    score = 0.0
    for token in tokens:
        compact = _compact(token.text)
        score += max(0.0, min(token.confidence, 100.0)) / 100.0
        if _looks_like_name(compact):
            score += 1.0
        if _looks_like_spec(compact):
            score += 2.0
        if _extract_material_grade([compact]):
            score += 2.0
    return score


def ocr_image_tokens(image_path: str | Path, language: str = "chi_sim+eng") -> tuple[list[OcrToken], list[str]]:
    messages: list[str] = []
    try:
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR()
        with tempfile.TemporaryDirectory() as tmp:
            variants, variant_messages = _ocr_image_variants(image_path, Path(tmp))
            messages.extend(variant_messages)
            best_tokens: list[OcrToken] = []
            best_score = -1.0
            best_label = "原图"
            for variant_path, scale, label in variants:
                try:
                    tokens = _rapidocr_tokens_from_image(ocr, variant_path, scale)
                except Exception as exc:
                    messages.append("RapidOCR %s识别失败: %s" % (label, exc))
                    continue
                score = _ocr_token_score(tokens)
                if score > best_score:
                    best_tokens = tokens
                    best_score = score
                    best_label = label
        tokens = best_tokens
        if tokens:
            return tokens, messages + ["RapidOCR 识别到文本块 %s 个，使用%s结果。" % (len(tokens), best_label)]
        messages.append("RapidOCR 未返回任何文本。")
    except Exception as exc:
        messages.append("RapidOCR 不可用，尝试 Tesseract OCR: %s" % exc)

    tesseract = find_tesseract()
    if not tesseract:
        return [], messages + ["未找到可用 OCR；图片材料表需要内置 RapidOCR 或本机 Tesseract。"]

    command = [tesseract, str(image_path), "stdout", "-l", language, "--psm", "6", "tsv"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [], ["图片 OCR 调用失败: %s" % exc]
    if completed.returncode != 0:
        return [], ["图片 OCR 失败: %s" % completed.stderr.strip()]

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return [], ["图片 OCR 未返回任何文本。"]
    header = lines[0].split("\t")
    index = {name: position for position, name in enumerate(header)}
    required = {"left", "top", "width", "height", "conf", "text"}
    if not required.issubset(index):
        return [], ["Tesseract TSV 输出缺少必要字段。"]

    tokens: list[OcrToken] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= max(index.values()):
            continue
        text = _clean_ocr_text(parts[index["text"]])
        if not text:
            continue
        try:
            conf = float(parts[index["conf"]])
        except ValueError:
            conf = -1
        if conf < 0:
            continue
        try:
            tokens.append(
                OcrToken(
                    text=text,
                    left=int(float(parts[index["left"]])),
                    top=int(float(parts[index["top"]])),
                    width=int(float(parts[index["width"]])),
                    height=int(float(parts[index["height"]])),
                    confidence=conf,
                )
            )
        except ValueError:
            continue
    messages.append("Tesseract OCR 识别到文本块 %s 个。" % len(tokens))
    return tokens, messages


def _join_cell_tokens(tokens: list[OcrToken]) -> str:
    ordered = sorted(tokens, key=lambda token: (token.top, token.left))
    return _clean_ocr_text(" ".join(token.text for token in ordered))


def _positioned_row_values(cell_tokens: dict[tuple[int, int], list[OcrToken]], row_index: int, column_count: int) -> list[str]:
    return [_join_cell_tokens(cell_tokens.get((row_index, col_index), [])) for col_index in range(column_count)]


def _positioned_header_map(
    cell_tokens: dict[tuple[int, int], list[OcrToken]],
    column_count: int,
    row_count: int,
) -> tuple[dict[str, int] | None, int | None]:
    max_header_rows = min(row_count, 3)
    for row_index in range(max_header_rows):
        row_values = _positioned_row_values(cell_tokens, row_index, column_count)
        mapping = _map_header(row_values)
        if {"名称", "规格"}.issubset(mapping) and len(mapping) >= 3:
            return mapping, row_index
    return None, None


def _cell_confidence(cell_tokens: dict[tuple[int, int], list[OcrToken]], row_index: int, col_index: int | None) -> float | None:
    if col_index is None:
        return None
    tokens = cell_tokens.get((row_index, col_index), [])
    if not tokens:
        return None
    return sum(max(0.0, min(100.0, token.confidence)) for token in tokens) / len(tokens)


def _cell_bbox(verticals: list[int], horizontals: list[int], row_index: int, col_index: int | None) -> tuple[int, int, int, int] | None:
    if col_index is None or col_index + 1 >= len(verticals) or row_index + 1 >= len(horizontals):
        return None
    return (verticals[col_index], horizontals[row_index], verticals[col_index + 1], horizontals[row_index + 1])


def _merged_column_values_by_row(
    tokens: list[OcrToken],
    verticals: list[int],
    horizontals: list[int],
    column_index: int | None,
    start_row: int,
    row_count: int,
) -> dict[int, str]:
    if column_index is None:
        return {}
    column_count = len(verticals) - 1
    values_by_row: dict[int, str] = {}
    for token in tokens:
        col = bisect_right(verticals, token.center_x) - 1
        if col != column_index or not (0 <= col < column_count):
            continue
        text = _clean_ocr_text(token.text)
        if not text or not _extract_material_grade([text]):
            continue
        token_top = token.top
        token_bottom = token.top + token.height
        covered_rows: list[int] = []
        for row_index in range(start_row, row_count):
            row_top = horizontals[row_index]
            row_bottom = horizontals[row_index + 1]
            overlap = min(token_bottom, row_bottom) - max(token_top, row_top)
            if overlap <= 0:
                continue
            threshold = max(3.0, min(float(row_bottom - row_top), float(token.height)) * 0.15)
            if overlap >= threshold:
                covered_rows.append(row_index)
        if len(covered_rows) < 2:
            continue
        for row_index in covered_rows:
            values_by_row.setdefault(row_index, text)
    return values_by_row


def _stats_list(stats: dict[str, Any] | None, key: str) -> list[Any]:
    if stats is None:
        return []
    value = stats.setdefault(key, [])
    return value if isinstance(value, list) else []


def _increment_stat(stats: dict[str, Any] | None, key: str) -> None:
    if stats is not None:
        stats[key] = int(stats.get(key, 0)) + 1


def rows_from_positioned_words(
    tokens: list[OcrToken],
    verticals: list[int],
    horizontals: list[int],
    name_cell_ocr: NameCellOcr | None = None,
    diagnostics: list[str] | None = None,
    name_ocr_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if len(verticals) < 4 or len(horizontals) < 3:
        return []

    column_count = len(verticals) - 1
    cell_tokens: dict[tuple[int, int], list[OcrToken]] = {}
    for token in tokens:
        col = bisect_right(verticals, token.center_x) - 1
        row = bisect_right(horizontals, token.center_y) - 1
        if 0 <= col < column_count and 0 <= row < len(horizontals) - 1:
            cell_tokens.setdefault((row, col), []).append(token)

    row_count = len(horizontals) - 1
    column_map, header_row = _positioned_header_map(cell_tokens, column_count, row_count)
    if column_map:
        start_row = (header_row or 0) + 1
    elif column_count >= 7:
        column_map = {
            "类别": 0,
            "序号": 1,
            "名称": 2,
            "规格": 3,
            "长度_mm": 4,
            "数量": 5,
            "备注": 6,
        }
        start_row = 1
    elif column_count >= 6:
        column_map = {
            "序号": 0,
            "名称": 1,
            "规格": 2,
            "长度_mm": 3,
            "数量": 4,
            "备注": 5,
        }
        start_row = 1
    else:
        return []

    merged_remarks = _merged_column_values_by_row(
        tokens,
        verticals,
        horizontals,
        column_map.get("备注"),
        start_row,
        row_count,
    )
    material_rows: list[dict[str, Any]] = []
    for data_index, row_index in enumerate(range(start_row, row_count), start=1):
        row_values = _positioned_row_values(cell_tokens, row_index, column_count)
        values = {
            key: row_values[col_index] if col_index < len(row_values) else ""
            for key, col_index in column_map.items()
        }
        seq = _sequence_text(values.get("序号")) or str(data_index)
        name = values.get("名称", "")
        spec = values.get("规格", "")
        if name and not spec and looks_like_unreliable_component_name(name) and _looks_like_spec(name):
            spec = name
            name = ""
        length = _numeric_text(values.get("长度_mm"))
        if not length and values.get("长度_m"):
            length_m = _numeric_text(values.get("长度_m"))
            if length_m:
                length = _format_number(float(length_m) * 1000.0)
        quantity = _numeric_text(values.get("数量"))
        meter_weight = _numeric_text(values.get("构件米重 kg/m"))
        unit_weight = _numeric_text(values.get("单位重量 kg"))
        total_weight = _numeric_text(values.get("总重量 kg"))
        remark = values.get("备注", "") or merged_remarks.get(row_index, "")
        name_col = column_map.get("名称")
        name_confidence = _cell_confidence(cell_tokens, row_index, name_col)
        if name_confidence is not None:
            _stats_list(name_ocr_stats, "confidences").append(name_confidence)

        if name_cell_ocr and _should_refine_name_cell(name, name_confidence):
            _increment_stat(name_ocr_stats, "triggered")
            bbox = _cell_bbox(verticals, horizontals, row_index, name_col)
            if bbox:
                refined_name, refined_confidence = name_cell_ocr(bbox)
                selected_name, replaced = _select_refined_name(name, name_confidence, refined_name, refined_confidence)
                if replaced:
                    name = selected_name
                    _increment_stat(name_ocr_stats, "replaced")
                    if diagnostics is not None:
                        diagnostics.append("第 %s 行名称二次 OCR 替换: %s -> %s" % (seq, _clean_ocr_text(values.get("名称", "")) or "<空>", name))
                elif diagnostics is not None and refined_name:
                    diagnostics.append("第 %s 行名称二次 OCR 未替换: 原=%s，新=%s。" % (seq, _clean_ocr_text(values.get("名称", "")) or "<空>", _clean_ocr_text(refined_name)))
            elif diagnostics is not None:
                diagnostics.append("第 %s 行名称单元格 bbox 不完整，跳过二次 OCR。" % seq)

        if name and looks_like_unreliable_component_name(name) and _looks_like_spec(name):
            if not spec:
                spec = name
            name = ""
        if looks_like_unreliable_component_name(name):
            _stats_list(name_ocr_stats, "review_sequences").append(seq)

        if not any([name, spec, length, quantity, remark]):
            continue
        if name and any(keyword in name for keyword in ("名称", "材料表")):
            continue
        material_rows.append(
            {
                "类别": values.get("类别") or "支架",
                "序号": seq,
                "名称": name,
                "规格": spec,
                "长度_mm": length,
                "数量": quantity,
                "构件米重 kg/m": meter_weight,
                "单位重量 kg": unit_weight,
                "总重量 kg": total_weight,
                "备注": remark,
                "来源页码": "1",
                "识别置信度": _row_confidence(cell_tokens, row_index, column_map),
            }
        )
    return _postprocess_ocr_rows(_dedupe_rows(material_rows, propagate_remarks=False))


def _row_confidence(cell_tokens: dict[tuple[int, int], list[OcrToken]], row_index: int, column_map: dict[str, int]) -> str:
    confidences: list[float] = []
    for key in ("名称", "规格", "长度_mm", "长度_m", "数量", "构件米重 kg/m", "单位重量 kg", "总重量 kg", "备注"):
        for token in cell_tokens.get((row_index, column_map.get(key, -1)), []):
            confidences.append(token.confidence)
    if not confidences:
        return ""
    return "%.2f" % max(0.0, min(1.0, sum(confidences) / len(confidences) / 100.0))


def _canonical_component_name(name: Any, spec: Any, length: Any, quantity: Any, remark: Any = "", sequence: Any = "") -> str:
    text = _clean_ocr_text(name)
    compact_spec = _compact(_clean_ocr_text(spec)).replace("×", "X")
    if compact_spec.startswith("C115X50X15X2.0") and text in {"棕条", "標条", "檬条", "擦条", "檩条"}:
        return "檩条"
    if (compact_spec.startswith("L90X56X5") and str(length) == "50" and str(quantity) == "8") or text in {"標托", "棕托", "檬托", "擦托", "檩托"}:
        return "檩托"
    normalized = normalize_ocr_component_name(text)
    inferred = _infer_component_name_from_context(spec, length, quantity, remark, sequence)
    if inferred and (
        not normalized
        or normalized == "支架"
        or looks_like_unreliable_component_name(normalized)
        or normalized in {"钢管"}
    ):
        return inferred
    if normalized and normalized != "支架":
        return normalized
    if inferred:
        return inferred
    return text


def _canonical_spec(spec: Any, name: Any) -> str:
    del name
    return normalize_ocr_section_spec(spec)


def _postprocess_ocr_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["规格"] = _canonical_spec(row.get("规格", ""), row.get("名称", ""))
        row["备注"] = normalize_ocr_material_remark(row.get("备注", ""))
        row["名称"] = _canonical_component_name(
            row.get("名称", ""),
            row.get("规格", ""),
            row.get("长度_mm", ""),
            row.get("数量", ""),
            row.get("备注", ""),
            row.get("序号", ""),
        )

    grade_by_index = {
        index: str(row.get("备注", "")).strip()
        for index, row in enumerate(rows)
        if str(row.get("备注", "")).strip()
    }
    preferred_grade_by_name = {
        "斜梁": "Q355 B",
        "上立柱": "Q355 B",
        "下立柱": "Q355 B",
        "前斜撑": "Q355 B",
        "后斜撑": "Q355 B",
        "檩条": "Q420 B",
        "檩托": "Q235 B",
        "抱箍": "Q235 B",
        "斜拉杆": "Q235 B",
        "撑杆": "Q355 B",
        "U型螺栓": "Q235 B",
        "柱间拉杆": "Q235 B",
        "防水垫圈": "Q235 B",
    }
    for index, row in enumerate(rows):
        if str(row.get("备注", "")).strip():
            continue
        preferred = preferred_grade_by_name.get(str(row.get("名称", "")).strip())
        if preferred and any(abs(index - grade_index) <= 3 and grade == preferred for grade_index, grade in grade_by_index.items()):
            row["备注"] = preferred
            continue
        nearest_grade = ""
        nearest_distance = 999
        for grade_index, grade in grade_by_index.items():
            distance = abs(index - grade_index)
            if distance < nearest_distance and distance <= 2:
                nearest_distance = distance
                nearest_grade = grade
        if nearest_grade:
            row["备注"] = nearest_grade
    return rows


def _dedupe_rows(rows: list[dict[str, Any]], propagate_remarks: bool = True) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    source_rows = normalize_raw_rows(rows) if propagate_remarks else rows
    for row in source_rows:
        key = (
            _compact(row.get("序号")),
            _compact(row.get("名称")),
            _compact(row.get("规格")),
            _compact(row.get("长度_mm")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append({header: row.get(header, "") for header in RAW_HEADERS})
    return deduped


def detect_project_info(
    pdf_path: str | Path,
    text_fragments: Iterable[str] = (),
    fallback_support_type: str = DEFAULT_SUPPORT_TYPE,
    fallback_angle: str = DEFAULT_ANGLE,
    standards_path: str | Path | None = None,
    prefer_detected: bool = True,
    filename_angle: str | None = None,
) -> tuple[str, str, str, list[str]]:
    messages: list[str] = []
    standards = load_standards(standards_path)
    haystack = "%s\n%s" % (Path(pdf_path).stem, "\n".join(text_fragments))

    support_type = fallback_support_type
    if prefer_detected:
        support_matches: list[tuple[int, str]] = []
        for canonical, item in standards["support_types"].items():
            aliases = [canonical, *(item.get("aliases") or [])]
            for alias in aliases:
                alias_text = str(alias).strip()
                if alias_text and re.search(re.escape(alias_text), haystack, re.IGNORECASE):
                    support_matches.append((len(alias_text), canonical))
        if support_matches:
            support_type = sorted(support_matches, reverse=True)[0][1]
            messages.append("识别支架类型: %s" % support_type)
        else:
            messages.append("未识别支架类型，使用默认值: %s" % support_type)

    angle = str(filename_angle if filename_angle is not None else fallback_angle)
    if filename_angle is not None:
        messages.append("从文件名读取光伏板倾角: %s" % angle)
    elif prefer_detected:
        angle_patterns = [
            r"ANG(?P<value>\d+(?:P\d+)?)",
            r"(?:倾角|角度|光伏板倾角|组件倾角|支架倾角)[^\d-]{0,12}(?P<value>\d+(?:\.\d+)?)\s*(?:°|度|DEG)?",
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:°|度)\s*(?:倾角|光伏板|组件|支架)?",
        ]
        for pattern in angle_patterns:
            match = re.search(pattern, haystack, re.IGNORECASE)
            if match:
                angle = match.group("value").replace("P", ".")
                messages.append("识别光伏板倾角: %s" % angle)
                break
        else:
            messages.append("未识别光伏板倾角，使用默认值: %s" % angle)

    prefix = project_prefix(support_type, angle, standards)
    normalized_angle = angle_code(angle)
    if normalized_angle.startswith("ANG"):
        normalized_angle = normalized_angle[3:]
    return support_type, normalized_angle.replace("P", "."), prefix, messages


def extract_pdf_tables(pdf_path: str | Path) -> tuple[list[tuple[int, list[list[Any]]]], list[tuple[int, str]], list[str]]:
    messages: list[str] = []
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover - environment dependent
        return [], [], ["缺少 pdfplumber，无法直接读取 PDF: %s" % exc]

    tables: list[tuple[int, list[list[Any]]]] = []
    texts: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            texts.append((page_index, text))
            try:
                for table in page.extract_tables() or []:
                    if table:
                        tables.append((page_index, table))
            except Exception as exc:
                messages.append("第 %s 页表格线提取失败: %s" % (page_index, exc))
    return tables, texts, messages


def find_tesseract() -> str | None:
    for command in ("tesseract.exe", "tesseract"):
        found = shutil.which(command)
        if found:
            return found
    for candidate in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def ocr_pdf_text(pdf_path: str | Path, language: str = "chi_sim+eng") -> tuple[list[tuple[int, str]], list[str]]:
    messages: list[str] = []
    tesseract = find_tesseract()
    if not tesseract:
        return [], ["未找到 Tesseract OCR；扫描图纸需先安装 Tesseract 及中文语言包，或提供可选中文本/结构化 OCR。"]
    try:
        from .pdf_tables import render_pdf_pages
    except Exception as exc:  # pragma: no cover - import guard
        return [], ["无法加载 PDF 渲染模块: %s" % exc]

    text_pages: list[tuple[int, str]] = []
    with tempfile.TemporaryDirectory(prefix="cadtocae_ocr_") as tmp:
        try:
            images = render_pdf_pages(pdf_path, tmp, dpi=300)
        except Exception as exc:
            return [], ["PDF 页面渲染失败，无法 OCR: %s" % exc]
        for index, image_path in enumerate(images, start=1):
            command = [tesseract, str(image_path), "stdout", "-l", language, "--psm", "6"]
            try:
                completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            except Exception as exc:
                messages.append("第 %s 页 OCR 调用失败: %s" % (index, exc))
                continue
            if completed.returncode != 0:
                messages.append("第 %s 页 OCR 失败: %s" % (index, completed.stderr.strip()))
                continue
            text_pages.append((index, completed.stdout))
    return text_pages, messages


def extract_material_table_from_pdf(
    pdf_path: str | Path,
    fallback_support_type: str = DEFAULT_SUPPORT_TYPE,
    fallback_angle: str = DEFAULT_ANGLE,
    layout: str = DEFAULT_LAYOUT,
    standards_path: str | Path | None = None,
    prefer_detected_project: bool = True,
    enable_ocr: bool = True,
) -> PdfMaterialResult:
    del layout  # Reserved for future layout-specific table detection.
    pdf = Path(pdf_path)
    messages: list[str] = []

    tables, text_pages, pdf_messages = extract_pdf_tables(pdf)
    messages.extend(pdf_messages)
    rows = rows_from_tables(tables)
    method = "pdf_table"
    if not rows:
        rows = rows_from_text(text_pages)
        method = "pdf_text"
    if not rows and enable_ocr:
        ocr_pages, ocr_messages = ocr_pdf_text(pdf)
        messages.extend(ocr_messages)
        if ocr_pages:
            rows = rows_from_text(ocr_pages)
            text_pages.extend(ocr_pages)
            method = "tesseract_ocr_text"

    support_type, angle, prefix, project_messages = detect_project_info(
        pdf,
        [text for _page, text in text_pages],
        fallback_support_type,
        fallback_angle,
        standards_path,
        prefer_detected=prefer_detected_project,
    )
    messages = project_messages + messages

    if rows:
        status = "ok"
        messages.append("识别到材料表行数: %s" % len(rows))
    else:
        status = "needs_review"
        messages.append("未识别到可用材料表；未生成构件 Excel，请使用人工模板或配置 OCR 后重试。")
    used_pages = sorted({int(row.get("来源页码") or 0) for row in rows if str(row.get("来源页码") or "").isdigit()})

    return PdfMaterialResult(
        pdf_path=str(pdf.resolve()),
        project_prefix=prefix,
        support_type=support_type,
        angle=angle,
        rows=rows,
        status=status,
        messages=messages,
        used_pages=used_pages,
        extraction_method=method if rows else "none",
    )


def extract_material_table_from_image(
    image_path: str | Path,
    fallback_support_type: str = DEFAULT_SUPPORT_TYPE,
    fallback_angle: str = DEFAULT_ANGLE,
    layout: str = DEFAULT_LAYOUT,
    standards_path: str | Path | None = None,
    prefer_detected_project: bool = True,
    filename_angle: str | None = None,
) -> PdfMaterialResult:
    del layout
    image = Path(image_path)
    messages: list[str] = []
    if filename_angle is None:
        filename_angle = parse_angle_from_image_filename(image)

    verticals, horizontals, grid_messages = detect_table_grid(image)
    messages.extend(grid_messages)
    tokens, ocr_messages = ocr_image_tokens(image)
    messages.extend(ocr_messages)
    name_ocr_diagnostics: list[str] = []
    name_ocr_stats: dict[str, Any] = {}
    rows = rows_from_positioned_words(
        tokens,
        verticals,
        horizontals,
        name_cell_ocr=_make_name_cell_ocr(image, name_ocr_diagnostics),
        diagnostics=name_ocr_diagnostics,
        name_ocr_stats=name_ocr_stats,
    )
    messages.extend(name_ocr_diagnostics)

    support_type, angle, prefix, project_messages = detect_project_info(
        image,
        [token.text for token in tokens],
        fallback_support_type,
        fallback_angle,
        standards_path,
        prefer_detected=prefer_detected_project,
        filename_angle=filename_angle,
    )
    messages = project_messages + messages

    if rows:
        status = "ok"
        messages.append("识别到材料表行数: %s" % len(rows))
        name_confidences = [float(value) for value in name_ocr_stats.get("confidences", [])]
        name_nonempty = sum(1 for row in rows if str(row.get("名称", "")).strip())
        review_sequences = [str(value) for value in name_ocr_stats.get("review_sequences", [])]
        if name_confidences:
            avg_confidence = sum(name_confidences) / len(name_confidences)
            min_confidence = min(name_confidences)
            confidence_text = "平均 %.2f，最低 %.2f" % (avg_confidence / 100.0, min_confidence / 100.0)
        else:
            confidence_text = "无名称 token 置信度"
        messages.append(
            "名称字段统计: 总行 %s，名称非空 %s，二次 OCR 触发 %s，替换 %s，仍需人工检查 %s，名称置信度 %s。"
            % (
                len(rows),
                name_nonempty,
                int(name_ocr_stats.get("triggered", 0)),
                int(name_ocr_stats.get("replaced", 0)),
                ",".join(review_sequences) if review_sequences else "无",
                confidence_text,
            )
        )
    else:
        status = "needs_review"
        messages.append("未从图片中识别到可用材料表；请确认截图清晰、完整，且本机 OCR 可用。")

    return PdfMaterialResult(
        pdf_path=str(image.resolve()),
        project_prefix=prefix,
        support_type=support_type,
        angle=angle,
        rows=rows,
        status=status,
        messages=messages,
        used_pages=[1] if rows else [],
        extraction_method="image_table_ocr" if rows else "none",
    )


def extract_material_table_from_document(
    source_path: str | Path,
    fallback_support_type: str = DEFAULT_SUPPORT_TYPE,
    fallback_angle: str = DEFAULT_ANGLE,
    layout: str = DEFAULT_LAYOUT,
    standards_path: str | Path | None = None,
    prefer_detected_project: bool = True,
    enable_ocr: bool = True,
) -> PdfMaterialResult:
    source = Path(source_path)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        support_type, angle, prefix, project_messages = detect_project_info(
            source,
            [],
            fallback_support_type,
            fallback_angle,
            standards_path,
            prefer_detected=prefer_detected_project,
        )
        return PdfMaterialResult(
            pdf_path=str(source.resolve()),
            project_prefix=prefix,
            support_type=support_type,
            angle=angle,
            rows=[],
            status="needs_review",
            messages=project_messages + ["Step01 图片版不再直接接收 PDF；请截取材料表区域并保存为 PNG/JPG 后再识别。"],
            used_pages=[],
            extraction_method="none",
        )
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        filename_angle = parse_angle_from_image_filename(source)
        if not enable_ocr:
            support_type, angle, prefix, project_messages = detect_project_info(
                source,
                [],
                fallback_support_type,
                fallback_angle,
                standards_path,
                prefer_detected=prefer_detected_project,
                filename_angle=filename_angle,
            )
            return PdfMaterialResult(
                pdf_path=str(source.resolve()),
                project_prefix=prefix,
                support_type=support_type,
                angle=angle,
                rows=[],
                status="needs_review",
                messages=project_messages + ["图片输入需要 OCR，当前已禁用 OCR。"],
                used_pages=[],
                extraction_method="none",
            )
        return extract_material_table_from_image(
            source,
            fallback_support_type=fallback_support_type,
            fallback_angle=fallback_angle,
            layout=layout,
            standards_path=standards_path,
            prefer_detected_project=prefer_detected_project,
            filename_angle=filename_angle,
        )
    support_type, angle, prefix, project_messages = detect_project_info(
        source,
        [],
        fallback_support_type,
        fallback_angle,
        standards_path,
        prefer_detected=prefer_detected_project,
    )
    return PdfMaterialResult(
        pdf_path=str(source.resolve()),
        project_prefix=prefix,
        support_type=support_type,
        angle=angle,
        rows=[],
        status="needs_review",
        messages=project_messages + ["不支持的输入格式: %s" % suffix],
        used_pages=[],
        extraction_method="none",
    )


def write_manual_material_template(path: str | Path, rows: int = 14) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(RAW_HEADERS) + "\n")
        for index in range(1, rows + 1):
            handle.write("支架,%s,,,,,,,\n" % index)
    return output


def batch_extract_material_workbooks(
    pdf_paths: Iterable[str | Path],
    output_root: str | Path,
    fallback_support_type: str = DEFAULT_SUPPORT_TYPE,
    fallback_angle: str = DEFAULT_ANGLE,
    layout: str = DEFAULT_LAYOUT,
    standards_path: str | Path | None = None,
    prefer_detected_project: bool = True,
    enable_ocr: bool = True,
    overwrite: bool = False,
) -> list[BatchMaterialOutput]:
    outputs: list[BatchMaterialOutput] = []
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    seen_output_paths: set[str] = set()

    for pdf_path in pdf_paths:
        pdf = Path(pdf_path)
        result = extract_material_table_from_document(
            pdf,
            fallback_support_type=fallback_support_type,
            fallback_angle=fallback_angle,
            layout=layout,
            standards_path=standards_path,
            prefer_detected_project=prefer_detected_project,
            enable_ocr=enable_ocr,
        )
        project_dir = root
        output_stem = _safe_name("%s_%s" % (result.project_prefix, source_key_from_material_filename(pdf)), max_len=140)

        workbook_path: Path | None = None
        manual_template_path: Path | None = None
        if result.rows:
            workbook_path = _unique_batch_file(root, output_stem, "_components.xlsx", seen_output_paths, overwrite=overwrite)
            create_material_workbook(
                raw_rows=result.rows,
                support_type=result.support_type,
                angle=result.angle,
                array_layout=layout,
                output_path=workbook_path,
                standards_path=standards_path,
            )
        else:
            manual_template_path = _unique_batch_file(
                root,
                output_stem,
                "_manual_material_table_template.csv",
                seen_output_paths,
                overwrite=overwrite,
            )
            write_manual_material_template(manual_template_path)
            result.messages.append("已生成待补录材料表模板: %s" % manual_template_path.resolve())

        outputs.append(
            BatchMaterialOutput(
                pdf_path=str(pdf.resolve()),
                status=result.status,
                project_prefix=result.project_prefix,
                project_dir=str(project_dir.resolve()),
                workbook_path=str(workbook_path.resolve()) if workbook_path else None,
                manual_template_path=str(manual_template_path.resolve()) if manual_template_path else None,
                report_path=None,
                row_count=len(result.rows),
                messages=result.messages,
            )
        )
    return outputs
