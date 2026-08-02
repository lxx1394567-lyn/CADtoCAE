from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from bisect import bisect_right
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .standards import angle_code, load_standards, normalize_material_grade, project_prefix
from .workbook import RAW_HEADERS, create_material_workbook, normalize_raw_rows


DEFAULT_SUPPORT_TYPE = "单桩单立柱"
DEFAULT_ANGLE = "20"
DEFAULT_LAYOUT = "2行7列竖向"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
SUPPORTED_DOCUMENT_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES

MATERIAL_GRADES = re.compile(r"\b(Q\s*\d{3,4}\s*[A-Z]?|6063\s*[- ]?\s*T5)\b", re.IGNORECASE)
SPEC_HINT = re.compile(
    r"(?:^|[^A-Z0-9])(?:C|L|M)\s*\d+|[ΦφØ∅]\s*\d+|D\s*\d+\s*[xX×]\s*\d+",
    re.IGNORECASE,
)


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


def _extract_material_grade(cells: Iterable[Any]) -> str:
    combined = " ".join(_clean_cell(cell) for cell in cells if _clean_cell(cell))
    match = MATERIAL_GRADES.search(combined)
    if not match:
        return ""
    return normalize_material_grade(re.sub(r"\s+", " ", match.group(1).upper().replace("-", "-")).strip())


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


def _header_key(value: Any) -> str | None:
    text = _compact(value)
    if not text:
        return None
    if "序号" in text or text in {"编号", "NO", "NO."}:
        return "序号"
    if "名称" in text or "构件" in text or "零件" in text:
        return "名称"
    if "规格" in text or "型号" in text:
        return "规格"
    if "长度" in text or text.upper() in {"L", "L/MM", "LMM"}:
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
    length = _value_at(row, header.get("长度_mm"))
    quantity = _value_at(row, header.get("数量"))
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
    return _dedupe_rows(rows)


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
    return _dedupe_rows(rows)


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

    if len(horizontals) < 4 or len(verticals) < 4:
        messages.append(
            "未检测到清晰材料表网格线，建议截取完整表格区域并保持黑白清晰。检测到横线 %s 条、竖线 %s 条。"
            % (len(horizontals), len(verticals))
        )
    else:
        messages.append("检测到材料表网格线：横线 %s 条、竖线 %s 条。" % (len(horizontals), len(verticals)))

    return verticals, horizontals, messages


def ocr_image_tokens(image_path: str | Path, language: str = "chi_sim+eng") -> tuple[list[OcrToken], list[str]]:
    messages: list[str] = []
    try:
        from rapidocr_onnxruntime import RapidOCR

        result, _elapsed = RapidOCR()(str(image_path))
        tokens: list[OcrToken] = []
        for box, text, confidence in result or []:
            text = _clean_ocr_text(text)
            if not text:
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            tokens.append(
                OcrToken(
                    text=text,
                    left=int(min(xs)),
                    top=int(min(ys)),
                    width=int(max(xs) - min(xs)),
                    height=int(max(ys) - min(ys)),
                    confidence=float(confidence) * 100.0,
                )
            )
        if tokens:
            return tokens, ["RapidOCR 识别到文本块 %s 个。" % len(tokens)]
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


def rows_from_positioned_words(tokens: list[OcrToken], verticals: list[int], horizontals: list[int]) -> list[dict[str, Any]]:
    if len(verticals) < 4 or len(horizontals) < 3:
        return []

    column_count = len(verticals) - 1
    if column_count >= 7:
        column_map = {
            "类别": 0,
            "序号": 1,
            "名称": 2,
            "规格": 3,
            "长度_mm": 4,
            "数量": 5,
            "备注": 6,
        }
    elif column_count >= 6:
        column_map = {
            "序号": 0,
            "名称": 1,
            "规格": 2,
            "长度_mm": 3,
            "数量": 4,
            "备注": 5,
        }
    else:
        return []

    cell_tokens: dict[tuple[int, int], list[OcrToken]] = {}
    for token in tokens:
        col = bisect_right(verticals, token.center_x) - 1
        row = bisect_right(horizontals, token.center_y) - 1
        if 0 <= col < column_count and 0 <= row < len(horizontals) - 1:
            cell_tokens.setdefault((row, col), []).append(token)

    material_rows: list[dict[str, Any]] = []
    for row_index in range(1, len(horizontals) - 1):
        values = {
            key: _join_cell_tokens(cell_tokens.get((row_index, col_index), []))
            for key, col_index in column_map.items()
        }
        seq = _sequence_text(values.get("序号")) or str(row_index)
        name = values.get("名称", "")
        spec = values.get("规格", "")
        length = _numeric_text(values.get("长度_mm"))
        quantity = _numeric_text(values.get("数量"))
        remark = _extract_material_grade([values.get("备注", "")]) or values.get("备注", "")

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
                "备注": remark,
                "来源页码": "1",
                "识别置信度": _row_confidence(cell_tokens, row_index, column_map),
            }
        )
    return _postprocess_ocr_rows(_dedupe_rows(material_rows, propagate_remarks=False))


def _row_confidence(cell_tokens: dict[tuple[int, int], list[OcrToken]], row_index: int, column_map: dict[str, int]) -> str:
    confidences: list[float] = []
    for key in ("名称", "规格", "长度_mm", "数量", "备注"):
        for token in cell_tokens.get((row_index, column_map.get(key, -1)), []):
            confidences.append(token.confidence)
    if not confidences:
        return ""
    return "%.2f" % max(0.0, min(1.0, sum(confidences) / len(confidences) / 100.0))


def _canonical_component_name(name: Any, spec: Any, length: Any, quantity: Any) -> str:
    text = _clean_ocr_text(name)
    compact_spec = _compact(_clean_ocr_text(spec)).replace("×", "X")
    if compact_spec.startswith("C115X50X15X2.0") and text in {"棕条", "標条", "檬条", "擦条", "檩条"}:
        return "檩条"
    if (compact_spec.startswith("L90X56X5") and str(length) == "50" and str(quantity) == "8") or text in {"標托", "棕托", "檬托", "擦托", "檩托"}:
        return "檩托"
    return text


def _canonical_spec(spec: Any, name: Any) -> str:
    text = _clean_ocr_text(spec)
    if _clean_ocr_text(name) == "抱箍" and re.match(r"^[0O]\d+", text):
        return "Φ" + text[1:]
    return text


def _postprocess_ocr_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["规格"] = _canonical_spec(row.get("规格", ""), row.get("名称", ""))
        row["名称"] = _canonical_component_name(row.get("名称", ""), row.get("规格", ""), row.get("长度_mm", ""), row.get("数量", ""))
        row["备注"] = normalize_material_grade(row.get("备注", ""))

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

    angle = str(fallback_angle)
    if prefer_detected:
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
) -> PdfMaterialResult:
    del layout
    image = Path(image_path)
    messages: list[str] = []

    verticals, horizontals, grid_messages = detect_table_grid(image)
    messages.extend(grid_messages)
    tokens, ocr_messages = ocr_image_tokens(image)
    messages.extend(ocr_messages)
    rows = rows_from_positioned_words(tokens, verticals, horizontals)

    support_type, angle, prefix, project_messages = detect_project_info(
        image,
        [token.text for token in tokens],
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
        if not enable_ocr:
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
        project_folder_base = root / ("%s_%s" % (result.project_prefix, _safe_name(pdf.stem)))
        project_folder = project_folder_base
        if project_folder.exists() and not overwrite:
            counter = 2
            while True:
                candidate = root / ("%s_%02d" % (project_folder_base.name, counter))
                if not candidate.exists():
                    project_folder = candidate
                    break
                counter += 1
        project_folder.mkdir(parents=True, exist_ok=True)

        workbook_path: Path | None = None
        manual_template_path: Path | None = None
        if result.rows:
            workbook_path = project_folder / ("%s_components.xlsx" % result.project_prefix)
            create_material_workbook(
                raw_rows=result.rows,
                support_type=result.support_type,
                angle=result.angle,
                array_layout=layout,
                output_path=workbook_path,
                standards_path=standards_path,
            )
        else:
            manual_template_path = write_manual_material_template(project_folder / "manual_material_table_template.csv")
            result.messages.append("已生成待补录材料表模板: %s" % manual_template_path.resolve())

        outputs.append(
            BatchMaterialOutput(
                pdf_path=str(pdf.resolve()),
                status=result.status,
                project_prefix=result.project_prefix,
                project_dir=str(project_folder.resolve()),
                workbook_path=str(workbook_path.resolve()) if workbook_path else None,
                manual_template_path=str(manual_template_path.resolve()) if manual_template_path else None,
                report_path=None,
                row_count=len(result.rows),
                messages=result.messages,
            )
        )
    return outputs
